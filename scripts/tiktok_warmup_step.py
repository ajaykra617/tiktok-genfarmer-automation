#!/usr/bin/env python3
"""Run one resilient TikTok warm-up browse step.

This is the pragmatic runtime primitive for the warm-up MVP.  It keeps strong
checks when they are healthy without making a harmless feed swipe depend on one
flaky subsystem:

1. prove TikTok foreground/no-interrupt, recovering foreground in apply mode;
2. use the qualified feed selector when a hierarchy source is available;
3. prefer the verified GenFarmer browse-one app as action executor;
4. if GenFarmer fails *before* any execute request can be ambiguous, perform one
   bounded device-relative ADB swipe instead;
5. prove TikTok remains foreground/no-interrupt after the action and use the
   selector again when hierarchy is available.

If hierarchy is unavailable, success is explicitly reported as degraded
``foreground_continuity`` evidence, never as selector-proven success.  If the
hierarchy is readable and the selector is absent, execution fails closed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_actions import AdbActions  # noqa: E402
from genfarmer_automation.adb_observer import AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.browse_one import (  # noqa: E402
    BrowseOneError,
    created_run_binding,
    exact_bound_device_id,
    validate_browse_one_flow,
)
from genfarmer_automation.feed_anchor_qualification import candidates_from_payload  # noqa: E402
from genfarmer_automation.flow import FlowDocument  # noqa: E402
from genfarmer_automation.genfarm_file import GenFarmDocument, GenFarmFileError  # noqa: E402
from genfarmer_automation.genfarmer_client import GenFarmerClient, GenFarmerError  # noqa: E402
from genfarmer_automation.hierarchy_runtime import (  # noqa: E402
    HierarchyRuntimeError,
    capture_hierarchy_batch,
)
from genfarmer_automation.run_binding import extract_run_bindings, newest_for_app  # noqa: E402
from genfarmer_automation.run_bootstrap import (  # noqa: E402
    RunBootstrapError,
    create_run_with_task_refresh,
)
from genfarmer_automation.selector_gate import assess_selector_gate  # noqa: E402
from genfarmer_automation.tiktok_runtime import TikTokRuntime  # noqa: E402
from genfarmer_automation.warmup_step import (  # noqa: E402
    ActionBackend,
    ExecutionPhase,
    VerificationLevel,
    adb_fallback_allowed,
    choose_verification_level,
)

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def discover_user_id(value: Any) -> int | None:
    if isinstance(value, Mapping):
        for key in ("id", "userId", "user_id"):
            candidate = value.get(key)
            if isinstance(candidate, int) and not isinstance(candidate, bool):
                return candidate
            if isinstance(candidate, str) and candidate.isdigit():
                return int(candidate)
        for key in ("user", "data", "result"):
            found = discover_user_id(value.get(key))
            if found is not None:
                return found
    return None


def ready(obs) -> bool:
    return (
        obs.adb_state == "device"
        and obs.tiktok_foreground
        and obs.interrupt is InterruptKind.NONE
    )


def best_effort_selector(device: str, candidate, *, preferred_port: int | None):
    """Return (passed|None, provider, counts, error).

    None means hierarchy unavailable. False means hierarchy was readable and the
    qualified selector was absent/non-unique, which is a hard failure.
    """
    try:
        batch = capture_hierarchy_batch(
            device,
            count=1,
            interval=0.0,
            preferred_port=preferred_port,
            helper_timeout=4.0,
            max_ports=8,
        )
    except HierarchyRuntimeError as exc:
        return None, None, None, str(exc)
    gate = assess_selector_gate(candidate, batch.snapshots, package=TIKTOK_PACKAGE)
    return gate.passed, batch.provider, gate.counts, None


def attempt_genfarmer_action(
    *,
    base_url: str,
    app_id: str,
    compiled_flow,
    device: str,
    pages: int,
    private: Path,
):
    """Try one GenFarmer execution.

    Returns (backend, phase, detail).  Exceptions before run creation are safe
    for ADB fallback. Exceptions after a run id exists are deliberately surfaced
    as ambiguous and must not cause a second swipe.
    """
    phase = ExecutionPhase.BEFORE_RUN_CREATE
    read = GenFarmerClient(base_url, timeout=12.0, allow_mutations=False)
    user_id = discover_user_id(read.get_current_user())
    if user_id is None:
        raise GenFarmerError("could not resolve numeric GenFarmer user id")

    live_flow = FlowDocument.from_app_payload(read.get_app(app_id))
    validate_browse_one_flow(live_flow)

    bindings = []
    for page in range(1, pages + 1):
        bindings.extend(extract_run_bindings(read.list_runs(user_id=user_id, page=page, limit=100)))
    selected = newest_for_app(bindings, app_id)
    if selected is None:
        raise GenFarmerError("no persisted run/task binding found for browse-one app")
    target_device_id = exact_bound_device_id(selected, device)
    if target_device_id is None:
        raise GenFarmerError("persisted GenFarmer binding does not contain the requested ADB device")

    mutation = GenFarmerClient(base_url, timeout=20.0, allow_mutations=True)
    task_name = "Python Warmup Recovery"
    try:
        boot = create_run_with_task_refresh(
            mutation,
            user_id=user_id,
            app_id=app_id,
            task_id=selected.task_id,
            recovery_task_name=task_name,
        )
    except Exception:
        phase = ExecutionPhase.RUN_CREATE_FAILED
        raise

    created = boot.created_run
    (private / "genfarmer-create-run.private.json").write_text(
        json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    binding = created_run_binding(created, app_id=app_id, task_id=boot.task_id)
    if binding is None:
        phase = ExecutionPhase.RUN_CREATE_FAILED
        raise RuntimeError("fresh GenFarmer run id was not proven")

    phase = ExecutionPhase.RUN_CREATED
    try:
        executed = mutation.execute_run(binding.run_id, device_ids=[target_device_id])
    except Exception as exc:
        # A request may have reached GenFarmer even when the response fails.
        phase = ExecutionPhase.EXECUTE_REQUEST_SENT
        raise RuntimeError(f"GenFarmer execute response was ambiguous: {exc}") from exc

    phase = ExecutionPhase.EXECUTE_REQUEST_SENT
    (private / "genfarmer-execute-run.private.json").write_text(
        json.dumps(executed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ActionBackend.GENFARMER, phase, {
        "task_refreshed": boot.task_refreshed,
        "target_device_proven": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Adaptive one-command TikTok warm-up browse step")
    ap.add_argument("compiled", type=Path, help="compiled Browse One READY .genfarm")
    ap.add_argument("candidates", type=Path, help="private ranked-candidates.private.json")
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB")
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--post-settle", type=float, default=2.0)
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--strict-selector", action="store_true", help="block instead of degrading when hierarchy is unavailable")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.candidate < 1 or not 1 <= args.pages <= 20 or args.post_settle < 0:
        print("ERROR: invalid arguments", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL", "").strip()
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not device:
        print("ERROR: pass --device or configure DEFAULT_DEVICE_ADB", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
    out = ROOT / "evidence" / f"tiktok-warmup-step-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-warmup-step.shareable.json"
    result: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "candidate_index": args.candidate,
        "selector_value_private": True,
    }

    try:
        raw_candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
        candidates = candidates_from_payload(raw_candidates)
        if not 1 <= args.candidate <= len(candidates):
            raise RuntimeError("ranked candidate file does not contain requested candidate")
        candidate = candidates[args.candidate - 1]

        doc = GenFarmDocument.load(args.compiled)
        route = validate_browse_one_flow(doc.flow)
        payload = doc.to_dict()
        raw_app_id = payload.get("id")
        if not isinstance(raw_app_id, (str, int)) or isinstance(raw_app_id, bool) or not str(raw_app_id):
            raise BrowseOneError("compiled browse-one export must preserve live app id")
        app_id = str(raw_app_id)

        observer = AdbObserver(device)
        initial = observer.observe()
        if not ready(initial):
            if not args.apply:
                raise RuntimeError("TikTok not ready; use --apply for bounded foreground recovery")
            recovered = TikTokRuntime(device, observer=observer).ensure_foreground()
            result["foreground_recovery_attempts"] = recovered.attempts
            if not recovered.success:
                raise RuntimeError(f"foreground recovery failed: {recovered.reason}")

        pre_obs = observer.observe()
        if not ready(pre_obs):
            raise RuntimeError("TikTok foreground/no-interrupt precondition not proven")
        observer.capture_screenshot(private / "before.png")

        pre_selector, pre_provider, pre_counts, pre_hierarchy_error = best_effort_selector(
            device, candidate, preferred_port=args.preferred_hierarchy_port
        )
        if pre_selector is False:
            raise RuntimeError(f"feed selector readable but precondition failed with counts {pre_counts}")
        if pre_selector is None and args.strict_selector:
            raise RuntimeError(f"strict selector mode: {pre_hierarchy_error}")

        result.update({
            "route_valid": True,
            "runtime_action_count": len(route),
            "pre_foreground_pass": True,
            "pre_selector_pass": pre_selector,
            "pre_hierarchy_provider": pre_provider,
            "pre_hierarchy_available": pre_selector is not None,
        })

        if not args.apply:
            result["status"] = "DRY_RUN_READY"
            result["verification_level"] = (
                VerificationLevel.FULL_SELECTOR.value if pre_selector is True
                else VerificationLevel.FOREGROUND_CONTINUITY.value
            )
            shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print("=" * 78)
            print("TIKTOK WARM-UP STEP")
            print("=" * 78)
            print("Mode:                       DRY-RUN")
            print("Status:                     DRY_RUN_READY")
            print(f"Pre selector:               {'PASS' if pre_selector is True else 'UNAVAILABLE / DEGRADED'}")
            print("Mutation:                   NONE")
            print(f"Shareable result:           {shareable.relative_to(ROOT)}")
            print("=" * 78)
            return 0

        backend = None
        backend_detail: dict[str, Any] = {}
        fallback_reason = None
        phase = ExecutionPhase.BEFORE_RUN_CREATE

        if base_url:
            try:
                backend, phase, backend_detail = attempt_genfarmer_action(
                    base_url=base_url,
                    app_id=app_id,
                    compiled_flow=doc.flow,
                    device=device,
                    pages=args.pages,
                    private=private,
                )
            except (GenFarmerError, RunBootstrapError, RuntimeError) as exc:
                # If run creation never became ambiguous, one direct swipe is safe.
                text = str(exc)
                if "execute response was ambiguous" in text:
                    phase = ExecutionPhase.EXECUTE_REQUEST_SENT
                else:
                    phase = ExecutionPhase.RUN_CREATE_FAILED
                if not adb_fallback_allowed(phase):
                    raise
                fallback_reason = text

        if backend is None:
            frame = observer.capture_raw_frame()
            AdbActions(device).swipe_up_relative(width=frame.width, height=frame.height)
            backend = ActionBackend.ADB_FALLBACK
            backend_detail = {"measured_width": frame.width, "measured_height": frame.height}

        if args.post_settle:
            time.sleep(args.post_settle)

        post_obs = observer.observe()
        if not ready(post_obs):
            raise RuntimeError("TikTok foreground/no-interrupt postcondition not proven")
        observer.capture_screenshot(private / "after.png")

        post_selector, post_provider, post_counts, post_hierarchy_error = best_effort_selector(
            device, candidate, preferred_port=args.preferred_hierarchy_port
        )
        if post_selector is False:
            raise RuntimeError(f"feed selector readable but postcondition failed with counts {post_counts}")
        if post_selector is None and args.strict_selector:
            raise RuntimeError(f"strict selector mode postcheck: {post_hierarchy_error}")

        decision = choose_verification_level(
            selector_pre=pre_selector,
            selector_post=post_selector,
            foreground_pre=True,
            foreground_post=True,
        )

        result.update({
            "status": "PASS",
            "verification_level": decision.level.value,
            "action_backend": backend.value,
            "genfarmer_fallback_reason_present": fallback_reason is not None,
            "backend_detail": backend_detail,
            "post_foreground_pass": True,
            "post_selector_pass": post_selector,
            "post_hierarchy_provider": post_provider,
            "post_hierarchy_available": post_selector is not None,
        })
        shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print("=" * 78)
        print("TIKTOK WARM-UP STEP")
        print("=" * 78)
        print("Mode:                       APPLY")
        print("Status:                     PASS")
        print(f"Verification level:         {decision.level.value}")
        print(f"Action backend:             {backend.value}")
        print(f"Pre selector:               {'PASS' if pre_selector is True else 'UNAVAILABLE / CONTINUITY'}")
        print(f"Post selector:              {'PASS' if post_selector is True else 'UNAVAILABLE / CONTINUITY'}")
        print(f"GenFarmer fallback used:    {'YES' if backend is ActionBackend.ADB_FALLBACK else 'NO'}")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except (
        OSError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
        BrowseOneError,
        GenFarmFileError,
        GenFarmerError,
        HierarchyRuntimeError,
        RunBootstrapError,
    ) as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
