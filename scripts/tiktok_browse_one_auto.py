#!/usr/bin/env python3
"""One-command resilient TikTok browse-one supervisor.

This command keeps GenFarmer as the action executor but removes two brittle
operator steps:
- foreground recovery is performed automatically in apply mode using the already
  qualified TikTok launcher component;
- hierarchy capture treats the GenFarmer helper port as a hint, auto-discovers a
  healthy helper endpoint, and falls back to bounded ADB uiautomator XML if the
  helper is stale or wedged.

Success still requires independent application-level evidence: the qualified
feed selector must be unique before and after the GenFarmer browse-one run.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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
    HierarchyBatch,
    HierarchyRuntimeError,
    capture_hierarchy_batch,
)
from genfarmer_automation.run_binding import extract_run_bindings, newest_for_app  # noqa: E402
from genfarmer_automation.selector_gate import assess_selector_gate  # noqa: E402
from genfarmer_automation.tiktok_runtime import TikTokRuntime  # noqa: E402

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


def semantic_node(node: Mapping[str, Any]) -> dict[str, Any]:
    data = node.get("data") if isinstance(node.get("data"), Mapping) else {}
    return {
        "id": str(node.get("id")),
        "type": node.get("type"),
        "action": data.get("action"),
        "options": data.get("options"),
        "successNode": data.get("successNode"),
        "failNode": data.get("failNode"),
        "startLoopNode": data.get("startLoopNode"),
    }


def semantic_edge(edge: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": str(edge.get("source")),
        "target": str(edge.get("target")),
        "sourceHandle": edge.get("sourceHandle"),
        "targetHandle": edge.get("targetHandle"),
    }


def semantic_flow(flow: FlowDocument) -> dict[str, Any]:
    nodes = sorted(
        [semantic_node(node) for node in flow.nodes if isinstance(node, Mapping)],
        key=lambda item: item["id"],
    )
    edges = sorted(
        [semantic_edge(edge) for edge in flow.edges if isinstance(edge, Mapping)],
        key=lambda item: (
            item["source"],
            item["target"],
            str(item["sourceHandle"]),
            str(item["targetHandle"]),
        ),
    )
    return {"nodes": nodes, "edges": edges}


def canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def ready(observation) -> bool:
    return (
        observation.adb_state == "device"
        and observation.tiktok_foreground
        and observation.interrupt is InterruptKind.NONE
    )


def write_batch(private: Path, prefix: str, batch: HierarchyBatch) -> None:
    for index, xml in enumerate(batch.snapshots, 1):
        (private / f"{prefix}-{index:02d}.xml").write_text(xml, encoding="utf-8")
    (private / f"{prefix}-hierarchy-source.private.json").write_text(
        json.dumps(
            {
                "provider": batch.provider,
                "remote_port": batch.remote_port,
                "attempts": list(batch.attempts),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def capture_gate(
    device: str,
    candidate,
    *,
    samples: int,
    interval: float,
    preferred_port: int | None,
):
    batch = capture_hierarchy_batch(
        device,
        count=samples,
        interval=interval,
        preferred_port=preferred_port,
    )
    gate = assess_selector_gate(candidate, batch.snapshots, package=TIKTOK_PACKAGE)
    return batch, gate


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Resilient one-command GenFarmer TikTok browse with selector guards"
    )
    ap.add_argument("compiled", type=Path, help="compiled Browse One READY .genfarm")
    ap.add_argument("candidates", type=Path, help="private ranked-candidates.private.json")
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB")
    ap.add_argument(
        "--preferred-hierarchy-port",
        type=int,
        default=8912,
        help="helper port hint only; auto-discovery/fallback is automatic",
    )
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--sample-interval", type=float, default=0.25)
    ap.add_argument("--post-settle", type=float, default=2.0)
    ap.add_argument("--post-attempts", type=int, default=4)
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.candidate < 1 or not 2 <= args.samples <= 6:
        print("ERROR: invalid candidate/sample arguments", file=sys.stderr)
        return 2
    if not 1 <= args.preferred_hierarchy_port <= 65535:
        print("ERROR: --preferred-hierarchy-port must be 1..65535", file=sys.stderr)
        return 2
    if not 1 <= args.pages <= 20 or not 1 <= args.post_attempts <= 8:
        print("ERROR: invalid page/post-attempt arguments", file=sys.stderr)
        return 2
    if min(args.sample_interval, args.post_settle) < 0:
        print("ERROR: timing values must be non-negative", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not base_url or not device:
        print(
            "ERROR: configure GENFARMER_BASE_URL and pass --device or configure DEFAULT_DEVICE_ADB",
            file=sys.stderr,
        )
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
    out = ROOT / "evidence" / f"tiktok-browse-one-auto-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable_path = out / "tiktok-browse-one-auto.shareable.json"

    result: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "candidate_index": args.candidate,
        "selector_value_private": True,
        "action_executor": "genfarmer",
        "hierarchy_source_policy": "auto-helper-then-uiautomator",
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

        read_client = GenFarmerClient(base_url, timeout=15.0, allow_mutations=False)
        user_id = discover_user_id(read_client.get_current_user())
        if user_id is None:
            raise GenFarmerError("could not resolve numeric GenFarmer user id")

        live_flow = FlowDocument.from_app_payload(read_client.get_app(app_id))
        validate_browse_one_flow(live_flow)
        live_match = canonical_hash(semantic_flow(doc.flow)) == canonical_hash(semantic_flow(live_flow))
        if not live_match:
            raise RuntimeError("live GenFarmer app does not match compiled browse-one runtime semantics")

        bindings = []
        for page in range(1, args.pages + 1):
            bindings.extend(
                extract_run_bindings(
                    read_client.list_runs(user_id=user_id, page=page, limit=100)
                )
            )
        selected = newest_for_app(bindings, app_id)
        if selected is None:
            raise GenFarmerError("no persisted run/task binding found for browse-one app")
        target_device_id = exact_bound_device_id(selected, device)
        if target_device_id is None:
            raise RuntimeError(
                "persisted GenFarmer binding does not contain this exact ADB device id"
            )

        observer = AdbObserver(device)
        initial = observer.observe()
        foreground_recovered = False
        if not ready(initial):
            if not args.apply:
                raise RuntimeError(
                    "TikTok is not ready; dry-run does not mutate. Use --apply for bounded foreground recovery."
                )
            recovery = TikTokRuntime(device, observer=observer).ensure_foreground()
            result["foreground_recovery_attempts"] = recovery.attempts
            result["foreground_recovery_reason"] = recovery.reason
            if not recovery.success:
                raise RuntimeError(f"bounded foreground recovery failed: {recovery.reason}")
            foreground_recovered = recovery.attempts > 0

        before_obs = observer.observe()
        if not ready(before_obs):
            raise RuntimeError("TikTok foreground/no-interrupt precondition not proven")
        observer.capture_screenshot(private / "before.png")

        before_batch, pre_gate = capture_gate(
            device,
            candidate,
            samples=args.samples,
            interval=args.sample_interval,
            preferred_port=args.preferred_hierarchy_port,
        )
        write_batch(private, "before", before_batch)
        if not pre_gate.passed:
            raise RuntimeError(
                f"qualified feed selector precondition failed with counts {pre_gate.counts}"
            )

        result.update(
            {
                "browse_route_valid": True,
                "runtime_action_count": len(route),
                "live_runtime_semantic_match": True,
                "exact_adb_device_match": True,
                "foreground_recovered": foreground_recovered,
                "pre_selector_counts": list(pre_gate.counts),
                "pre_selector_pass": True,
                "pre_hierarchy_provider": before_batch.provider,
                "pre_hierarchy_remote_port": before_batch.remote_port,
            }
        )

        if not args.apply:
            result["status"] = "DRY_RUN_READY"
            result["reason"] = (
                "compiled/live browse-one match, exact device binding, foreground state, "
                "and qualified feed selector all passed"
            )
            shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print("=" * 78)
            print("TIKTOK AUTO SELECTOR-GUARDED BROWSE_ONE")
            print("=" * 78)
            print("Mode:                       DRY-RUN")
            print("Status:                     DRY_RUN_READY")
            print(f"Feed selector pre-counts:   {pre_gate.counts}")
            print(f"Hierarchy provider:         {before_batch.provider}")
            print("GenFarmer/device mutation:  NONE")
            print(f"Private evidence:           {private.relative_to(ROOT)}")
            print(f"Shareable result:           {shareable_path.relative_to(ROOT)}")
            print("=" * 78)
            return 0

        mutation = GenFarmerClient(base_url, timeout=20.0, allow_mutations=True)
        created = mutation.create_run(
            user_id=user_id,
            task_id=selected.task_id,
            app_id=app_id,
            status=0,
        )
        (private / "create-run.response.json").write_text(
            json.dumps(created, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        created_binding = created_run_binding(
            created,
            app_id=app_id,
            task_id=selected.task_id,
        )
        if created_binding is None:
            raise RuntimeError("fresh GenFarmer run id was not proven; execution not attempted")

        executed = mutation.execute_run(
            created_binding.run_id,
            device_ids=[target_device_id],
        )
        (private / "execute-run.response.json").write_text(
            json.dumps(executed, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if args.post_settle:
            time.sleep(args.post_settle)

        post_gate = None
        after_batch = None
        last_error = None
        for attempt in range(1, args.post_attempts + 1):
            after_obs = observer.observe()
            if not ready(after_obs):
                last_error = RuntimeError(
                    "TikTok foreground/no-interrupt postcondition not yet proven"
                )
            else:
                try:
                    batch, gate = capture_gate(
                        device,
                        candidate,
                        samples=args.samples,
                        interval=args.sample_interval,
                        preferred_port=(
                            before_batch.remote_port
                            if before_batch.remote_port is not None
                            else args.preferred_hierarchy_port
                        ),
                    )
                    after_batch = batch
                    post_gate = gate
                    if gate.passed:
                        last_error = None
                        break
                    last_error = RuntimeError(
                        f"qualified feed selector postcondition counts {gate.counts}"
                    )
                except HierarchyRuntimeError as exc:
                    last_error = exc
            if attempt < args.post_attempts:
                time.sleep(1.0)

        if after_batch is not None:
            write_batch(private, "after", after_batch)
        observer.capture_screenshot(private / "after.png")

        if post_gate is None or not post_gate.passed:
            raise RuntimeError(
                "GenFarmer browse was triggered but independent feed postcondition was not proven"
                + (f": {last_error}" if last_error else "")
            )

        result.update(
            {
                "fresh_run_created": True,
                "execute_requested_device_count": 1,
                "post_selector_counts": list(post_gate.counts),
                "post_selector_pass": True,
                "post_hierarchy_provider": after_batch.provider,
                "post_hierarchy_remote_port": after_batch.remote_port,
                "status": "PASS_SELECTOR_GUARDED_EXECUTION",
                "reason": (
                    "one GenFarmer browse completed and the qualified feed selector "
                    "was independently proven before and after"
                ),
            }
        )
        shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print("=" * 78)
        print("TIKTOK AUTO SELECTOR-GUARDED BROWSE_ONE")
        print("=" * 78)
        print("Mode:                       APPLY")
        print("Status:                     PASS_SELECTOR_GUARDED_EXECUTION")
        print(f"Foreground recovery:        {'YES' if foreground_recovered else 'NOT NEEDED'}")
        print(f"Feed selector pre-counts:   {pre_gate.counts}")
        print(f"Feed selector post-counts:  {post_gate.counts}")
        print(f"Pre hierarchy provider:     {before_batch.provider}")
        print(f"Post hierarchy provider:    {after_batch.provider}")
        print("Action executor:            GenFarmer")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable_path.relative_to(ROOT)}")
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
    ) as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable_path.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
