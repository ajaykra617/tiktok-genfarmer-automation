#!/usr/bin/env python3
"""Qualify surviving feed-anchor selectors across multiple feed items.

The input should already have survived non-feed negative qualification.  This
lab probe first proves that enough of those selectors are currently visible,
then (only with --apply and --confirm-feed) performs a small bounded number of
ADB-relative upward swipes.  After each swipe it rechecks TikTok foreground and
captures hierarchy XML through the already-discovered GenFarmer/openatx port.
Only selectors present exactly once in every sampled feed state survive.

ADB swipe is used only for qualification. Production browsing remains a
GenFarmer action with Python pre/post verification. Exact XML/XPath values stay
under ignored private evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_actions import AdbActions, AdbActionError  # noqa: E402
from genfarmer_automation.adb_observer import AdbObserver, AdbObservationError, InterruptKind  # noqa: E402
from genfarmer_automation.atx_bridge import extract_atx_hierarchy_xml  # noqa: E402
from genfarmer_automation.feed_anchor_qualification import candidates_from_payload  # noqa: E402
from genfarmer_automation.feed_anchor_variation import (  # noqa: E402
    FeedAnchorVariationError,
    qualify_across_feed_variants,
    unique_presence_ratio,
)
from genfarmer_automation.ui_xml import UiXmlError, parse_ui_xml  # noqa: E402

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
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def adb(device: str, *args: str, timeout: float = 8.0) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["adb", "-s", device, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("adb was not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"adb command timed out after {timeout}s") from exc


def create_forward(device: str, remote_port: int) -> int:
    proc = adb(device, "forward", "tcp:0", f"tcp:{remote_port}")
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or f"could not forward device tcp:{remote_port}")
    value = proc.stdout.decode("utf-8", errors="replace").strip()
    if not value.isdigit() or not (1 <= int(value) <= 65535):
        raise RuntimeError("adb returned invalid local forward port")
    return int(value)


def remove_forward(device: str, local_port: int) -> None:
    adb(device, "forward", "--remove", f"tcp:{local_port}", timeout=4.0)


def http_get(url: str, timeout: float = 8.0) -> tuple[int, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": "genfarmer-feed-anchor-variation/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    raw = body.decode("utf-8", errors="replace").strip()
    if not raw:
        return status, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def capture_xml(base: str) -> str:
    response = http_get(base + "/dump/hierarchy", timeout=10.0)
    if response is None:
        raise RuntimeError("hierarchy endpoint did not respond")
    xml = extract_atx_hierarchy_xml(response[1])
    if xml is None:
        raise RuntimeError("hierarchy endpoint response did not contain XML")
    parse_ui_xml(xml)
    return xml


def ready(observation) -> bool:
    return (
        observation.adb_state == "device"
        and observation.tiktok_foreground
        and observation.interrupt is InterruptKind.NONE
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Qualify feed-anchor candidates across several distinct feed states")
    ap.add_argument("candidates", type=Path, help="private qualified-candidates.private.json")
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB")
    ap.add_argument("--remote-port", type=int, required=True, help="known hierarchy device port")
    ap.add_argument("--swipes", type=int, default=3, help="bounded lab swipes, 1..5")
    ap.add_argument("--settle", type=float, default=1.2)
    ap.add_argument("--duration-ms", type=int, default=450)
    ap.add_argument("--min-current-match-ratio", type=float, default=0.50)
    ap.add_argument("--confirm-feed", action="store_true", help="confirm the phone is currently on the normal TikTok feed")
    ap.add_argument("--apply", action="store_true", help="perform the bounded lab swipes")
    args = ap.parse_args()

    if not 1 <= args.remote_port <= 65535:
        print("ERROR: --remote-port must be 1..65535", file=sys.stderr)
        return 2
    if not 1 <= args.swipes <= 5:
        print("ERROR: --swipes must be 1..5", file=sys.stderr)
        return 2
    if args.settle < 0:
        print("ERROR: --settle must be non-negative", file=sys.stderr)
        return 2
    if not 0.1 <= args.min_current_match_ratio <= 1.0:
        print("ERROR: --min-current-match-ratio must be 0.1..1.0", file=sys.stderr)
        return 2
    if args.apply and not args.confirm_feed:
        print("ERROR: --confirm-feed is required with --apply", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not device:
        print("ERROR: configure DEFAULT_DEVICE_ADB or pass --device", file=sys.stderr)
        return 2

    try:
        raw = json.loads(args.candidates.expanduser().read_text(encoding="utf-8"))
        candidates = candidates_from_payload(raw)
        if not candidates:
            raise RuntimeError("candidate file contains no selectors")

        observer = AdbObserver(device)
        initial_observation = observer.observe()
        if not ready(initial_observation):
            raise RuntimeError("TikTok foreground/no-interrupt precondition not proven")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
        out = ROOT / "evidence" / f"tiktok-feed-anchor-variation-{safe_device}-{stamp}"
        private = out / "private"
        private.mkdir(parents=True, exist_ok=True)

        local_port = create_forward(device, args.remote_port)
        try:
            base = f"http://127.0.0.1:{local_port}"
            first_xml = capture_xml(base)
            current_ratio = unique_presence_ratio(candidates, first_xml, package=TIKTOK_PACKAGE)
            (private / "feed-00.xml").write_text(first_xml, encoding="utf-8")
            observer.capture_screenshot(private / "feed-00.png")

            if current_ratio < args.min_current_match_ratio:
                raise RuntimeError(
                    f"current screen matched only {current_ratio * 100:.1f}% of surviving feed selectors; "
                    "refusing to swipe because normal feed state is not sufficiently proven"
                )

            if not args.apply:
                result = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "status": "DRY_RUN_READY",
                    "input_candidates": len(candidates),
                    "current_unique_match_ratio": current_ratio,
                    "swipes_executed": 0,
                    "selector_values_private": True,
                    "action_executor": "none",
                }
                shareable = out / "tiktok-feed-anchor-variation.shareable.json"
                shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")
                print("=" * 78)
                print("TIKTOK FEED-ANCHOR POSITIVE VARIATION")
                print("=" * 78)
                print("Mode:                      DRY-RUN")
                print("Status:                    DRY_RUN_READY")
                print(f"Input candidates:          {len(candidates)}")
                print(f"Current feed match ratio:  {current_ratio * 100:.1f}%")
                print("Swipes executed:           0")
                print("Next: rerun with --apply --confirm-feed for bounded lab variation testing.")
                print(f"Private evidence:          {private.relative_to(ROOT)}")
                print(f"Shareable result:          {shareable.relative_to(ROOT)}")
                print("=" * 78)
                return 0

            frame = observer.capture_raw_frame()
            actions = AdbActions(device)
            snapshots = [first_xml]
            for index in range(1, args.swipes + 1):
                before = observer.observe()
                if not ready(before):
                    raise RuntimeError(f"TikTok state became unsafe before lab swipe {index}")
                actions.swipe_up_relative(
                    width=frame.width,
                    height=frame.height,
                    duration_ms=args.duration_ms,
                )
                if args.settle:
                    time.sleep(args.settle)
                after = observer.observe()
                if not ready(after):
                    raise RuntimeError(f"TikTok foreground/no-interrupt postcondition failed after lab swipe {index}")
                xml = capture_xml(base)
                snapshots.append(xml)
                (private / f"feed-{index:02d}.xml").write_text(xml, encoding="utf-8")
                observer.capture_screenshot(private / f"feed-{index:02d}.png")
        finally:
            remove_forward(device, local_port)

        qualified = qualify_across_feed_variants(candidates, snapshots, package=TIKTOK_PACKAGE)
        qualified_path = private / "qualified-candidates.private.json"
        qualified_path.write_text(
            json.dumps([item.to_dict() for item in qualified], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if qualified else "NO_ROBUST_SELECTOR",
            "input_candidates": len(candidates),
            "current_unique_match_ratio": current_ratio,
            "feed_states_sampled": len(snapshots),
            "swipes_executed": args.swipes,
            "qualified_candidates": len(qualified),
            "rejected_candidates": len(candidates) - len(qualified),
            "top_qualified_kind": qualified[0].kind if qualified else None,
            "selector_values_private": True,
            "action_executor": "adb-relative-swipe-lab-only",
            "production_executor_unchanged": "GenFarmer",
        }
        shareable = out / "tiktok-feed-anchor-variation.shareable.json"
        shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print("=" * 78)
        print("TIKTOK FEED-ANCHOR POSITIVE VARIATION")
        print("=" * 78)
        print("Mode:                      APPLY (LAB QUALIFICATION)")
        print(f"Input candidates:          {len(candidates)}")
        print(f"Initial feed match ratio:  {current_ratio * 100:.1f}%")
        print(f"Feed states sampled:       {len(snapshots)}")
        print(f"Bounded lab swipes:        {args.swipes}")
        print(f"Candidates rejected:       {len(candidates) - len(qualified)}")
        print(f"Candidates qualified:      {len(qualified)}")
        for index, candidate in enumerate(qualified[:8], 1):
            print(
                f"Qualified {index:02d}: kind={candidate.kind}, score={candidate.score}, "
                f"unique={'YES' if candidate.unique_in_all else 'NO'}, occurrences={candidate.occurrences}"
            )
        print("Production action executor: GenFarmer (unchanged)")
        print(f"Private qualified file:    {qualified_path.relative_to(ROOT)}")
        print(f"Shareable result:          {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0 if qualified else 1
    except (
        RuntimeError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        UiXmlError,
        FeedAnchorVariationError,
        AdbActionError,
        AdbObservationError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
