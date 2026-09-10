#!/usr/bin/env python3
"""Qualify feed-anchor candidates against a known non-feed TikTok screen.

Run after `tiktok_uia2_runtime_discovery.py` has learned positive candidates on
normal TikTok feed. The operator places TikTok on one known non-feed screen
(Profile/Search/Comments) and explicitly confirms that state. This script then
reuses the previously discovered hierarchy port, captures repeated read-only XML
snapshots, and removes every positive candidate that appears on the negative
screen.

No tap, swipe, WebDriver session, helper install/restart, or GenFarmer stop is
performed. Exact XML/XPath values stay in ignored private evidence.
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

from genfarmer_automation.adb_observer import AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.atx_bridge import extract_atx_hierarchy_xml  # noqa: E402
from genfarmer_automation.feed_anchor_qualification import (  # noqa: E402
    FeedAnchorQualificationError,
    candidates_from_payload,
    qualify_against_negative_xml,
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
    req = urllib.request.Request(url, headers={"User-Agent": "genfarmer-feed-anchor-negative-qualifier/1"})
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


def resolve_positive_paths(value: Path) -> tuple[Path, Path]:
    path = value.expanduser().resolve()
    if path.is_file():
        candidates_path = path
        private_dir = path.parent
    else:
        private_dir = path
        candidates_path = private_dir / "candidates.private.json"
    if not candidates_path.is_file():
        raise RuntimeError(f"positive candidates not found: {candidates_path}")
    return private_dir, candidates_path


def discover_saved_port(private_dir: Path) -> int | None:
    parent = private_dir.parent
    shareables = sorted(parent.glob("*.shareable.json"))
    for path in shareables:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        value = payload.get("selected_remote_port") if isinstance(payload, dict) else None
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535:
            return value
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Reject feed-anchor candidates present on a confirmed non-feed TikTok screen")
    ap.add_argument("positive", type=Path, help="positive discovery private directory or candidates.private.json")
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB")
    ap.add_argument("--remote-port", type=int, help="hierarchy device port; defaults to positive discovery shareable result")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--interval", type=float, default=0.35)
    ap.add_argument("--screen-label", choices=("profile", "search", "comments", "other"), required=True)
    ap.add_argument("--confirm-non-feed", action="store_true", help="required explicit confirmation that current TikTok screen is not the normal feed")
    args = ap.parse_args()

    if not args.confirm_non_feed:
        print("ERROR: --confirm-non-feed is required; place TikTok on a known non-feed screen first", file=sys.stderr)
        return 2
    if not 2 <= args.samples <= 8:
        print("ERROR: --samples must be 2..8", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not device:
        print("ERROR: configure DEFAULT_DEVICE_ADB or pass --device", file=sys.stderr)
        return 2

    try:
        private_dir, candidates_path = resolve_positive_paths(args.positive)
        raw = json.loads(candidates_path.read_text(encoding="utf-8"))
        positive = candidates_from_payload(raw)
        remote_port = args.remote_port or discover_saved_port(private_dir)
        if remote_port is None:
            raise RuntimeError("could not recover hierarchy port from positive evidence; pass --remote-port")

        observation = AdbObserver(device).observe()
        if observation.adb_state != "device" or not observation.tiktok_foreground or observation.interrupt is not InterruptKind.NONE:
            raise RuntimeError("TikTok foreground/no-interrupt precondition not proven")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
        out = ROOT / "evidence" / f"tiktok-feed-anchor-negative-{safe_device}-{stamp}"
        private = out / "private"
        private.mkdir(parents=True, exist_ok=True)

        local_port = create_forward(device, remote_port)
        try:
            base = f"http://127.0.0.1:{local_port}"
            negatives: list[str] = []
            for index in range(args.samples):
                xml = capture_xml(base)
                negatives.append(xml)
                (private / f"negative-{index + 1:02d}.xml").write_text(xml, encoding="utf-8")
                if index + 1 < args.samples and args.interval:
                    time.sleep(args.interval)
        finally:
            remove_forward(device, local_port)

        qualified = qualify_against_negative_xml(positive, negatives, package=TIKTOK_PACKAGE)
        (private / "qualified-candidates.private.json").write_text(
            json.dumps([item.to_dict() for item in qualified], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "screen_label": args.screen_label,
            "positive_candidate_count": len(positive),
            "negative_samples": len(negatives),
            "qualified_candidate_count": len(qualified),
            "rejected_candidate_count": len(positive) - len(qualified),
            "top_qualified_kind": qualified[0].kind if qualified else None,
            "top_qualified_unique_in_all": qualified[0].unique_in_all if qualified else False,
            "selector_values_private": True,
            "app_ui_actions": 0,
        }
        shareable = out / "tiktok-feed-anchor-negative.shareable.json"
        shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print("=" * 78)
        print("TIKTOK FEED-ANCHOR NEGATIVE QUALIFICATION")
        print("=" * 78)
        print(f"Known non-feed screen:     {args.screen_label}")
        print(f"Positive candidates:       {len(positive)}")
        print(f"Negative XML samples:      {len(negatives)}")
        print(f"Candidates rejected:       {len(positive) - len(qualified)}")
        print(f"Candidates qualified:      {len(qualified)}")
        for index, candidate in enumerate(qualified[:8], 1):
            print(
                f"Qualified {index:02d}: kind={candidate.kind}, score={candidate.score}, "
                f"unique={'YES' if candidate.unique_in_all else 'NO'}, occurrences={candidate.occurrences}"
            )
        print("App UI actions:             NONE")
        print(f"Private qualified file:    {(private / 'qualified-candidates.private.json').relative_to(ROOT)}")
        print(f"Shareable result:          {shareable.relative_to(ROOT)}")
        if not qualified:
            print("Result: no candidate is feed-specific against this negative screen; do not patch ElementExists.")
        else:
            print("Next: qualify against at least one additional non-feed screen before patching ElementExists.")
        print("=" * 78)
        return 0 if qualified else 1
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError, UiXmlError, FeedAnchorQualificationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
