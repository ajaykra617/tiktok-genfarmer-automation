#!/usr/bin/env python3
"""Explore TikTok from a configured keyword/hashtag/account/link source.

This is account-local discovery only. It performs no likes, follows, replies,
DMs, or cross-account engagement. Search controls are resolved from fresh native
hierarchy bounds; link exploration uses Android's explicit VIEW intent targeted
to the authorized TikTok package.

Runtime recovery is bounded and shared with the rest of the automation engine.
Only read-only observation/hierarchy operations may be retried. UI mutations
(taps, text entry, ENTER) are never automatically replayed after a timeout.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_actions import AdbActions, AdbActionError  # noqa: E402
from genfarmer_automation.adb_observer import AdbObservationError, AdbObserver  # noqa: E402
from genfarmer_automation.hierarchy_runtime import HierarchyRuntimeError, capture_hierarchy_batch  # noqa: E402
from genfarmer_automation.native_ui import (  # noqa: E402
    NativeUiError,
    NativeUiNotFound,
    collect_nodes,
    find_exact_semantic_node,
    find_semantic_node,
)
from genfarmer_automation.runtime_supervisor import (  # noqa: E402
    RuntimeSupervisorError,
    TikTokRuntimeSupervisor,
)
from genfarmer_automation.search_entry import wait_for_search_editable  # noqa: E402
from genfarmer_automation import tiktok_semantics as semantics  # noqa: E402

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _capture(device: str, preferred_port: int) -> tuple[str, str]:
    batch = capture_hierarchy_batch(
        device,
        count=1,
        interval=0.0,
        preferred_port=preferred_port,
        helper_timeout=4.0,
        max_ports=12,
    )
    return batch.snapshots[0], batch.provider


def _open_link(device: str, url: str) -> None:
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise ValueError("link explore source must be an http(s) URL")
    try:
        proc = subprocess.run(
            [
                "adb", "-s", device, "shell", "am", "start", "-W",
                "-a", "android.intent.action.VIEW", "-d", url,
                "-p", TIKTOK_PACKAGE,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30.0,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("adb was not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        # Do not replay this mutation automatically: the intent may already have
        # been delivered even though the host-side command timed out.
        raise RuntimeError("TikTok link intent timed out") from exc
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace").strip() or "TikTok link intent failed")


def _query_visible(xml: str, query: str) -> bool:
    needle = " ".join(query.casefold().split())
    for node in collect_nodes(xml, package=TIKTOK_PACKAGE):
        for value in (node.text, node.content_desc):
            normalized = " ".join(value.casefold().split())
            if needle and needle in normalized:
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Authorized TikTok Boost explore controller")
    ap.add_argument("--type", choices=("keyword", "hashtag", "account", "link"), required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--device", required=True)
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    raw_value = args.value.strip()
    if not raw_value:
        print("ERROR: --value must not be empty", file=sys.stderr)
        return 2
    query = raw_value
    if args.type == "hashtag":
        query = query.lstrip("#").strip()
    elif args.type == "account":
        query = query.lstrip("@").strip()
    if not query:
        print("ERROR: explore query became empty after normalization", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-boost-explore-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-boost-explore.shareable.json"
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "source_type": args.type,
        "source_value_private": True,
        "engagement_actions": 0,
    }
    (private / "source.private.json").write_text(
        json.dumps({"type": args.type, "value": raw_value}, indent=2), encoding="utf-8"
    )

    if not args.apply:
        result["status"] = "DRY_RUN_READY"
        _write_json(shareable, result)
        print("=" * 78)
        print("TIKTOK BOOST EXPLORE")
        print("=" * 78)
        print("Mode:                       DRY-RUN")
        print("Status:                     DRY_RUN_READY")
        print(f"Source type:                {args.type}")
        print("Mutation:                   NONE")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    supervisor = None
    try:
        observer = AdbObserver(args.device)
        actions = AdbActions(args.device)
        supervisor = TikTokRuntimeSupervisor(args.device, observer=observer, actions=actions)
        supervisor.ensure_ready(apply=True)

        if args.type == "link":
            _open_link(args.device, raw_value)
            time.sleep(4.0)
            supervisor.ensure_ready(apply=True)

            screenshot_captured = False
            try:
                observer.capture_screenshot(private / "link-context.png")
                screenshot_captured = True
            except AdbObservationError:
                pass

            try:
                xml, provider = supervisor.run_read_only(
                    lambda: _capture(args.device, args.preferred_hierarchy_port)
                )
                (private / "link-context.xml").write_text(xml, encoding="utf-8")
            except HierarchyRuntimeError:
                # Link qualification only requires TikTok foreground proof. The
                # hierarchy is useful evidence but not the link correctness gate.
                provider = None
            result.update(
                {
                    "status": "PASS",
                    "context_verified": "tiktok_foreground",
                    "hierarchy_provider": provider,
                    "screenshot_captured": screenshot_captured,
                }
            )
        else:
            xml, provider = supervisor.run_read_only(
                lambda: _capture(args.device, args.preferred_hierarchy_port)
            )
            (private / "feed-before-search.xml").write_text(xml, encoding="utf-8")
            search = find_semantic_node(xml, semantics.SEARCH, package=TIKTOK_PACKAGE)
            actions.tap(*search.center)
            time.sleep(1.5)
            supervisor.ensure_ready(apply=True)

            search_entry_captures: list[tuple[str, str]] = []

            def capture_search_entry() -> str:
                xml_value, provider_value = supervisor.run_read_only(
                    lambda: _capture(args.device, args.preferred_hierarchy_port)
                )
                search_entry_captures.append((xml_value, provider_value))
                attempt_number = len(search_entry_captures)
                (private / f"search-entry-{attempt_number}.xml").write_text(
                    xml_value,
                    encoding="utf-8",
                )
                return xml_value

            search_entry = wait_for_search_editable(
                capture_search_entry,
                package=TIKTOK_PACKAGE,
            )
            xml = search_entry.xml
            provider2 = search_entry_captures[-1][1]
            (private / "search-entry.xml").write_text(xml, encoding="utf-8")
            edit = search_entry.node
            actions.tap(*edit.center)
            actions.input_text(query)
            actions.keyevent(66)  # ENTER
            time.sleep(3.0)
            supervisor.ensure_ready(apply=True)

            xml, provider3 = supervisor.run_read_only(
                lambda: _capture(args.device, args.preferred_hierarchy_port)
            )
            (private / "search-results.xml").write_text(xml, encoding="utf-8")
            tab_selected = False
            if args.type == "hashtag":
                try:
                    tab = find_exact_semantic_node(xml, semantics.HASHTAG_TABS, package=TIKTOK_PACKAGE)
                    actions.tap(*tab.center)
                    tab_selected = True
                    time.sleep(1.5)
                    supervisor.ensure_ready(apply=True)
                    xml, provider3 = supervisor.run_read_only(
                        lambda: _capture(args.device, args.preferred_hierarchy_port)
                    )
                except NativeUiNotFound:
                    pass
            elif args.type == "account":
                try:
                    tab = find_exact_semantic_node(xml, semantics.ACCOUNT_TABS, package=TIKTOK_PACKAGE)
                    actions.tap(*tab.center)
                    tab_selected = True
                    time.sleep(1.5)
                    supervisor.ensure_ready(apply=True)
                    xml, provider3 = supervisor.run_read_only(
                        lambda: _capture(args.device, args.preferred_hierarchy_port)
                    )
                except NativeUiNotFound:
                    pass

            supervisor.ensure_ready(apply=True)
            screenshot_captured = False
            try:
                observer.capture_screenshot(private / "explore-context.png")
                screenshot_captured = True
            except AdbObservationError:
                pass

            query_proven = _query_visible(xml, query)
            if not query_proven:
                raise RuntimeError("search completed but configured query was not proven in the fresh UI hierarchy")
            result.update(
                {
                    "status": "PASS",
                    "context_verified": "query_visible",
                    "specialized_tab_selected": tab_selected,
                    "hierarchy_providers": sorted({provider, provider2, provider3}),
                    "search_entry_attempts": search_entry.attempts,
                    "screenshot_captured": screenshot_captured,
                }
            )

        result["recovery_budget_used"] = supervisor.snapshot().recovery_budget_used
        _write_json(shareable, result)
        print("=" * 78)
        print("TIKTOK BOOST EXPLORE")
        print("=" * 78)
        print("Status:                     PASS")
        print(f"Source type:                {args.type}")
        print(f"Context verification:       {result['context_verified']}")
        print(f"Recovery budget used:       {result['recovery_budget_used']}")
        print("Engagement actions:         NONE")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except (
        RuntimeError,
        ValueError,
        AdbActionError,
        AdbObservationError,
        HierarchyRuntimeError,
        NativeUiError,
        RuntimeSupervisorError,
    ) as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        if supervisor is not None:
            result["recovery_budget_used"] = supervisor.snapshot().recovery_budget_used
        _write_json(shareable, result)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
