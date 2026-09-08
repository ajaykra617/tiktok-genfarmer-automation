#!/usr/bin/env python3
"""Run one passive TikTok browse transition through GenFarmer with proof.

Dry-run by default.  ``--apply`` is allowed only when all of these gates pass:
- compiled file is exactly the short browse-one graph;
- the live GenFarmer app has the same runtime semantics as that compiled file;
- a recent persisted run exposes the same task binding;
- one GenFarmer device id exactly equals DEFAULT_DEVICE_ADB;
- TikTok is foreground with no known interrupt;
- the no-action control window has enough stable baseline area to be trustworthy;
- no-action control drift stays below the visual transition gate.

The apply path creates a fresh run, executes it on exactly that one bound device,
and reports success only if the post-action visual transition is conservatively
proven.  A successful GenFarmer HTTP/node response alone is never success.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
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

from genfarmer_automation.adb_observer import AdbObservationError, AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.browse_one import (  # noqa: E402
    BrowseOneError,
    control_window_is_safe,
    created_run_binding,
    exact_bound_device_id,
    validate_browse_one_flow,
)
from genfarmer_automation.flow import FlowDocument  # noqa: E402
from genfarmer_automation.genfarm_file import GenFarmDocument, GenFarmFileError  # noqa: E402
from genfarmer_automation.genfarmer_client import GenFarmerClient, GenFarmerError  # noqa: E402
from genfarmer_automation.run_binding import extract_run_bindings, newest_for_app  # noqa: E402
from genfarmer_automation.screen_transition import (  # noqa: E402
    TransitionDecision,
    TransitionReport,
    assess_visual_transition,
)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


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
    data = node.get("data")
    data_map = data if isinstance(data, Mapping) else {}
    return {
        "id": str(node.get("id")),
        "type": node.get("type"),
        "action": data_map.get("action"),
        "options": data_map.get("options"),
        "successNode": data_map.get("successNode"),
        "failNode": data_map.get("failNode"),
        "startLoopNode": data_map.get("startLoopNode"),
    }


def semantic_edge(edge: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": str(edge.get("source")),
        "target": str(edge.get("target")),
        "sourceHandle": edge.get("sourceHandle"),
        "targetHandle": edge.get("targetHandle"),
    }


def semantic_flow(flow: FlowDocument) -> dict[str, Any]:
    nodes = [semantic_node(node) for node in flow.nodes if isinstance(node, Mapping)]
    nodes.sort(key=lambda item: item["id"])
    edges = [semantic_edge(edge) for edge in flow.edges if isinstance(edge, Mapping)]
    edges.sort(key=lambda item: (item["source"], item["target"], str(item["sourceHandle"]), str(item["targetHandle"])))
    return {"nodes": nodes, "edges": edges}


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def collect_frames(observer: AdbObserver, count: int, interval: float):
    frames = []
    for index in range(count):
        frames.append(observer.capture_raw_frame())
        if index + 1 < count and interval:
            time.sleep(interval)
    return frames


def report_dict(report: TransitionReport) -> dict[str, Any]:
    value = asdict(report)
    value["decision"] = report.decision.value
    return value


def ready(observation) -> bool:
    return (
        observation.adb_state == "device"
        and observation.tiktok_foreground
        and observation.interrupt is InterruptKind.NONE
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Dry-run or execute one verified TikTok browse through GenFarmer")
    ap.add_argument("compiled", type=Path, help="compiled browse-one .genfarm file")
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB")
    ap.add_argument("--apply", action="store_true", help="create and execute exactly one GenFarmer run")
    ap.add_argument("--pages", type=int, default=5, help="recent run pages used to recover task binding")
    ap.add_argument("--frames", type=int, default=3)
    ap.add_argument("--frame-interval", type=float, default=0.25)
    ap.add_argument("--control-gap", type=float, default=1.0)
    ap.add_argument("--post-settle", type=float, default=3.0)
    args = ap.parse_args()

    if not 1 <= args.pages <= 20:
        print("ERROR: --pages must be 1..20", file=sys.stderr)
        return 2
    if not 2 <= args.frames <= 8:
        print("ERROR: --frames must be 2..8", file=sys.stderr)
        return 2
    if min(args.frame_interval, args.control_gap, args.post_settle) < 0:
        print("ERROR: timing values must be non-negative", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not base_url or not device:
        print("ERROR: configure GENFARMER_BASE_URL and DEFAULT_DEVICE_ADB (or pass --device)", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
    out = ROOT / "evidence" / f"tiktok-browse-one-genfarmer-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable_path = out / "tiktok-browse-one-genfarmer.shareable.json"

    result: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "status": "STARTED",
        "action_executor": "genfarmer",
    }

    try:
        doc = GenFarmDocument.load(args.compiled)
        compiled_flow = doc.flow
        route = validate_browse_one_flow(compiled_flow)
        payload = doc.to_dict()
        raw_app_id = payload.get("id")
        if not isinstance(raw_app_id, (str, int)) or isinstance(raw_app_id, bool) or not str(raw_app_id):
            raise BrowseOneError("compiled browse-one export must preserve the live app id")
        app_id = str(raw_app_id)
        result["route_validated"] = True
        result["runtime_action_count"] = len(route)

        read_client = GenFarmerClient(base_url, timeout=15.0, allow_mutations=False)
        user_id = discover_user_id(read_client.get_current_user())
        if user_id is None:
            raise GenFarmerError("could not resolve numeric GenFarmer user id")

        live_payload = read_client.get_app(app_id)
        live_flow = FlowDocument.from_app_payload(live_payload)
        live_route = validate_browse_one_flow(live_flow)
        compiled_semantic_hash = canonical_hash(semantic_flow(compiled_flow))
        live_semantic_hash = canonical_hash(semantic_flow(live_flow))
        live_match = compiled_semantic_hash == live_semantic_hash
        result["live_browse_route_valid"] = live_route == route
        result["live_runtime_semantic_match"] = live_match
        (private / "compiled.semantic.json").write_text(json.dumps(semantic_flow(compiled_flow), indent=2), encoding="utf-8")
        (private / "live.semantic.json").write_text(json.dumps(semantic_flow(live_flow), indent=2), encoding="utf-8")
        if not live_match:
            result["status"] = "BLOCKED_LIVE_FLOW_MISMATCH"
            result["reason"] = "live GenFarmer app is not the compiled browse-one module; apply the compiled file first"
            raise RuntimeError(result["reason"])

        bindings = []
        raw_pages = []
        for page in range(1, args.pages + 1):
            page_payload = read_client.list_runs(user_id=user_id, page=page, limit=100)
            raw_pages.append(page_payload)
            bindings.extend(extract_run_bindings(page_payload))
        (private / "runs.raw.json").write_text(json.dumps(raw_pages, ensure_ascii=False, indent=2), encoding="utf-8")
        selected = newest_for_app(bindings, app_id)
        if selected is None:
            raise GenFarmerError("no persisted run/task binding found for this app")
        (private / "binding.private.json").write_text(json.dumps(selected.private_dict(), indent=2), encoding="utf-8")
        target_device_id = exact_bound_device_id(selected, device)
        result["recent_binding_found"] = True
        result["binding_device_ref_count"] = len(selected.device_ids)
        result["exact_adb_device_match"] = target_device_id is not None
        if target_device_id is None:
            result["status"] = "BLOCKED_DEVICE_BINDING"
            result["reason"] = "none of the persisted GenFarmer device ids exactly equals DEFAULT_DEVICE_ADB; refusing fuzzy selection"
            raise RuntimeError(result["reason"])

        observer = AdbObserver(device)
        initial = observer.observe()
        result["initial"] = initial.to_dict()
        observer.capture_screenshot(private / "initial.png")
        if not ready(initial):
            result["status"] = "BLOCKED_NOT_READY"
            result["reason"] = "TikTok foreground/no-interrupt precondition not proven"
            raise RuntimeError(result["reason"])

        before = collect_frames(observer, args.frames, args.frame_interval)
        if args.control_gap:
            time.sleep(args.control_gap)
        control_frames = collect_frames(observer, args.frames, args.frame_interval)
        control = assess_visual_transition(before, control_frames)
        result["control"] = report_dict(control)
        result["control_window_safe"] = control_window_is_safe(control)
        if not control_window_is_safe(control):
            if control.decision is TransitionDecision.PROVEN_CHANGED:
                result["status"] = "INCONCLUSIVE_CONTROL_DRIFT"
                result["reason"] = "screen changed enough without an action; visual postcondition is unsafe for this sample"
            else:
                result["status"] = "INCONCLUSIVE_CONTROL_BASELINE"
                result["reason"] = (
                    "no-action control baseline did not contain enough temporally stable screen area; "
                    "refusing to mutate because later visual verification would be untrustworthy"
                )
            raise RuntimeError(result["reason"])

        if not args.apply:
            result["status"] = "DRY_RUN_READY"
            result["reason"] = "all fail-closed gates passed; rerun with --apply for one GenFarmer browse-one run"
            exit_code = 0
            action_report = None
        else:
            mutation_client = GenFarmerClient(base_url, timeout=20.0, allow_mutations=True)
            created = mutation_client.create_run(
                user_id=user_id,
                task_id=selected.task_id,
                app_id=app_id,
                status=0,
            )
            (private / "create-run.response.json").write_text(json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8")
            created_binding = created_run_binding(created, app_id=app_id, task_id=selected.task_id)
            if created_binding is None:
                result["status"] = "BLOCKED_CREATED_RUN_ID_UNPROVEN"
                result["reason"] = "create-run response did not expose one unambiguous matching run id; execution was not attempted"
                raise RuntimeError(result["reason"])

            executed = mutation_client.execute_run(created_binding.run_id, device_ids=[target_device_id])
            (private / "execute-run.response.json").write_text(json.dumps(executed, ensure_ascii=False, indent=2), encoding="utf-8")
            result["fresh_run_created"] = True
            result["execute_requested_device_count"] = 1

            if args.post_settle:
                time.sleep(args.post_settle)
            post = observer.observe()
            result["post_observation"] = post.to_dict()
            observer.capture_screenshot(private / "after.png")
            if not ready(post):
                result["status"] = "BLOCKED_AFTER_GENFARMER"
                result["reason"] = "TikTok foreground/no-interrupt postcondition failed after GenFarmer execution"
                raise RuntimeError(result["reason"])

            after = collect_frames(observer, args.frames, args.frame_interval)
            adaptive_changed_ratio = max(0.15, float(control.changed_ratio_of_stable) + 0.10)
            action_report = assess_visual_transition(
                control_frames,
                after,
                min_changed_ratio=adaptive_changed_ratio,
            )
            result["action_transition"] = report_dict(action_report)
            result["adaptive_min_changed_ratio"] = adaptive_changed_ratio
            if action_report.decision is TransitionDecision.PROVEN_CHANGED:
                result["status"] = "PASS_GENFARMER_VISUAL_TRANSITION"
                result["reason"] = "GenFarmer executed one browse module and the independent postcondition proved persistent distributed change"
                exit_code = 0
            else:
                result["status"] = "INCONCLUSIVE_AFTER_GENFARMER"
                result["reason"] = "GenFarmer run was triggered but the independent visual postcondition was not proven"
                exit_code = 1

        shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("=" * 78)
        print("TIKTOK SUPERVISED BROWSE_ONE VIA GENFARMER")
        print("=" * 78)
        print(f"Mode:                    {'APPLY' if args.apply else 'DRY-RUN'}")
        print(f"Status:                  {result['status']}")
        print("Browse-one route:        VALID")
        print(f"Live semantic match:     {'YES' if result.get('live_runtime_semantic_match') else 'NO'}")
        print(f"Persisted device refs:   {result.get('binding_device_ref_count', 0)}")
        print(f"Exact ADB device match:  {'YES' if result.get('exact_adb_device_match') else 'NO'}")
        print(f"Control stable ratio:    {control.baseline_stable_ratio * 100:.1f}%")
        print(f"Control changed ratio:   {control.changed_ratio_of_stable * 100:.1f}%")
        print(f"Control decision:        {control.decision.value}")
        if action_report is not None:
            print(f"Action changed ratio:    {action_report.changed_ratio_of_stable * 100:.1f}%")
            print(f"Changed cells:           {action_report.changed_cells}/{action_report.occupied_cells}")
            print(f"Transition decision:     {action_report.decision.value}")
        print(f"Reason:                  {result.get('reason', '')}")
        if not args.apply and result["status"] == "DRY_RUN_READY":
            print("Next:                    rerun the same command with --apply")
        print(f"Private evidence:        {private.relative_to(ROOT)}")
        print(f"Shareable result:        {shareable_path.relative_to(ROOT)}")
        print("=" * 78)
        return exit_code

    except (BrowseOneError, GenFarmFileError, GenFarmerError, AdbObservationError, OSError, ValueError, RuntimeError) as exc:
        if result.get("status") == "STARTED":
            result["status"] = "ERROR"
            result["reason"] = str(exc)
        shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("=" * 78)
        print("TIKTOK SUPERVISED BROWSE_ONE VIA GENFARMER")
        print("=" * 78)
        print(f"Mode:   {'APPLY' if args.apply else 'DRY-RUN'}")
        print(f"Status: {result.get('status')}")
        print(f"Reason: {result.get('reason', str(exc))}")
        print(f"Private evidence: {private.relative_to(ROOT)}")
        print(f"Shareable result: {shareable_path.relative_to(ROOT)}")
        print("No further action was attempted after the failing gate.")
        print("=" * 78)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
