#!/usr/bin/env python3
"""Run one passive GenFarmer TikTok browse with hierarchy feed guards.

This is the successor to the whole-screen visual gate for animated TikTok feeds.
Python proves the qualified feed selector immediately before and after the short
GenFarmer browse-one module. GenFarmer remains the action executor.

Dry-run is the default. ``--apply`` creates exactly one fresh GenFarmer run and
executes it on exactly one previously-observed bound device. A GenFarmer HTTP
response alone is never treated as the application-level postcondition.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Mapping
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_observer import AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.atx_bridge import extract_atx_hierarchy_xml  # noqa: E402
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
from genfarmer_automation.run_binding import extract_run_bindings, newest_for_app  # noqa: E402
from genfarmer_automation.selector_gate import assess_selector_gate  # noqa: E402
from genfarmer_automation.ui_xml import parse_ui_xml  # noqa: E402

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


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
        key=lambda item: (item["source"], item["target"], str(item["sourceHandle"]), str(item["targetHandle"])),
    )
    return {"nodes": nodes, "edges": edges}


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def adb(device: str, *args: str, timeout: float = 8.0) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["adb", "-s", device, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def create_forward(device: str, remote_port: int) -> int:
    proc = adb(device, "forward", "tcp:0", f"tcp:{remote_port}", timeout=6.0)
    if proc.returncode != 0:
        raise RuntimeError("could not create temporary hierarchy ADB forward")
    value = proc.stdout.decode("utf-8", errors="replace").strip()
    if not value.isdigit():
        raise RuntimeError("ADB did not return a temporary local forward port")
    return int(value)


def remove_forward(device: str, local_port: int) -> None:
    try:
        adb(device, "forward", "--remove", f"tcp:{local_port}", timeout=4.0)
    except Exception:
        pass


def hierarchy_xml(local_port: int, timeout: float = 8.0) -> str:
    req = urllib.request.Request(
        f"http://127.0.0.1:{local_port}/dump/hierarchy",
        headers={"User-Agent": "tiktok-selector-guard/1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace").strip()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"hierarchy request failed: {exc}") from exc
    try:
        payload: Any = json.loads(body)
    except json.JSONDecodeError:
        payload = body
    xml = extract_atx_hierarchy_xml(payload)
    if xml is None:
        raise RuntimeError("existing helper did not return hierarchy XML")
    parse_ui_xml(xml)
    return xml


def capture_hierarchy_samples(device: str, remote_port: int, count: int, interval: float) -> list[str]:
    local_port = create_forward(device, remote_port)
    try:
        snapshots: list[str] = []
        for index in range(count):
            snapshots.append(hierarchy_xml(local_port))
            if index + 1 < count and interval:
                time.sleep(interval)
        return snapshots
    finally:
        remove_forward(device, local_port)


def ready(observation) -> bool:
    return observation.adb_state == "device" and observation.tiktok_foreground and observation.interrupt is InterruptKind.NONE


def main() -> int:
    ap = argparse.ArgumentParser(description="Run one GenFarmer browse-one module guarded by the qualified feed selector")
    ap.add_argument("compiled", type=Path, help="compiled GF Lab - TikTok Browse One.genfarm")
    ap.add_argument("candidates", type=Path, help="private ranked-candidates.private.json")
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB")
    ap.add_argument("--hierarchy-port", type=int, default=8912)
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--sample-interval", type=float, default=0.30)
    ap.add_argument("--post-settle", type=float, default=3.0)
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.candidate < 1 or not 1 <= args.hierarchy_port <= 65535 or not 2 <= args.samples <= 6:
        print("ERROR: invalid candidate/port/sample arguments", file=sys.stderr)
        return 2
    if not 1 <= args.pages <= 20 or min(args.sample_interval, args.post_settle) < 0:
        print("ERROR: invalid page/timing arguments", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not base_url or not device:
        print("ERROR: configure GENFARMER_BASE_URL and pass --device or configure DEFAULT_DEVICE_ADB", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
    out = ROOT / "evidence" / f"tiktok-browse-one-selector-guarded-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable_path = out / "tiktok-browse-one-selector-guarded.shareable.json"

    result: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "candidate_index": args.candidate,
        "selector_value_private": True,
        "action_executor": "genfarmer",
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
            bindings.extend(extract_run_bindings(read_client.list_runs(user_id=user_id, page=page, limit=100)))
        selected = newest_for_app(bindings, app_id)
        if selected is None:
            raise GenFarmerError("no persisted run/task binding found for browse-one app")
        target_device_id = exact_bound_device_id(selected, device)
        if target_device_id is None:
            raise RuntimeError("persisted GenFarmer binding does not contain this exact ADB device id")

        observer = AdbObserver(device)
        before_obs = observer.observe()
        if not ready(before_obs):
            raise RuntimeError("TikTok foreground/no-interrupt precondition not proven")
        observer.capture_screenshot(private / "before.png")

        before_xml = capture_hierarchy_samples(device, args.hierarchy_port, args.samples, args.sample_interval)
        for index, xml in enumerate(before_xml, 1):
            (private / f"before-{index:02d}.xml").write_text(xml, encoding="utf-8")
        pre_gate = assess_selector_gate(candidate, before_xml, package=TIKTOK_PACKAGE)
        if not pre_gate.passed:
            raise RuntimeError(f"qualified feed selector precondition failed with counts {pre_gate.counts}")

        result.update({
            "browse_route_valid": True,
            "live_runtime_semantic_match": True,
            "exact_adb_device_match": True,
            "pre_selector_counts": list(pre_gate.counts),
            "pre_selector_pass": True,
        })

        if not args.apply:
            result["status"] = "DRY_RUN_READY"
            result["reason"] = "compiled/live browse-one match, exact device binding, and fresh feed selector precondition all passed"
            shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print("=" * 78)
            print("TIKTOK SELECTOR-GUARDED BROWSE_ONE VIA GENFARMER")
            print("=" * 78)
            print("Mode:                       DRY-RUN")
            print("Status:                     DRY_RUN_READY")
            print("Browse-one route:           VALID")
            print("Live semantic match:        YES")
            print("Exact ADB device match:     YES")
            print(f"Feed selector pre-counts:   {pre_gate.counts}")
            print("GenFarmer/device mutation:  NONE")
            print(f"Private evidence:           {private.relative_to(ROOT)}")
            print(f"Shareable result:           {shareable_path.relative_to(ROOT)}")
            print("=" * 78)
            return 0

        mutation = GenFarmerClient(base_url, timeout=20.0, allow_mutations=True)
        created = mutation.create_run(user_id=user_id, task_id=selected.task_id, app_id=app_id, status=0)
        (private / "create-run.response.json").write_text(json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8")
        created_binding = created_run_binding(created, app_id=app_id, task_id=selected.task_id)
        if created_binding is None:
            raise RuntimeError("fresh GenFarmer run id was not proven; execution not attempted")
        executed = mutation.execute_run(created_binding.run_id, device_ids=[target_device_id])
        (private / "execute-run.response.json").write_text(json.dumps(executed, ensure_ascii=False, indent=2), encoding="utf-8")

        if args.post_settle:
            time.sleep(args.post_settle)
        after_obs = observer.observe()
        observer.capture_screenshot(private / "after.png")
        if not ready(after_obs):
            raise RuntimeError("TikTok foreground/no-interrupt postcondition failed after GenFarmer run")

        after_xml = capture_hierarchy_samples(device, args.hierarchy_port, args.samples, args.sample_interval)
        for index, xml in enumerate(after_xml, 1):
            (private / f"after-{index:02d}.xml").write_text(xml, encoding="utf-8")
        post_gate = assess_selector_gate(candidate, after_xml, package=TIKTOK_PACKAGE)
        hierarchy_changed = canonical_hash(before_xml[-1]) != canonical_hash(after_xml[0])

        result.update({
            "fresh_run_created": True,
            "execute_requested_device_count": 1,
            "post_selector_counts": list(post_gate.counts),
            "post_selector_pass": post_gate.passed,
            "hierarchy_changed": hierarchy_changed,
        })
        if post_gate.passed:
            result["status"] = "PASS_SELECTOR_GUARDED_EXECUTION"
            result["reason"] = "GenFarmer executed one short browse module and fresh hierarchy proved the qualified feed state both before and after"
            exit_code = 0
        else:
            result["status"] = "POSTCONDITION_FAILED"
            result["reason"] = "GenFarmer run was triggered but the qualified feed selector was not proven afterward"
            exit_code = 1

        shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("=" * 78)
        print("TIKTOK SELECTOR-GUARDED BROWSE_ONE VIA GENFARMER")
        print("=" * 78)
        print("Mode:                       APPLY")
        print(f"Status:                     {result['status']}")
        print(f"Feed selector pre-counts:   {pre_gate.counts}")
        print(f"Feed selector post-counts:  {post_gate.counts}")
        print(f"Hierarchy changed:          {'YES' if hierarchy_changed else 'NO'}")
        print("Action executor:            GenFarmer")
        print("Exact selector value:       PRIVATE / NOT PRINTED")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable_path.relative_to(ROOT)}")
        print("=" * 78)
        return exit_code
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, GenFarmFileError, GenFarmerError, BrowseOneError) as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable_path.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
