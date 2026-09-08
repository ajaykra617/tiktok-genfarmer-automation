#!/usr/bin/env python3
"""Capture Android UIAutomator XML and learn stable XPath candidates.

This is the automation bridge between ADB-observed UI state and GenFarmer's
XPath-based ElementExists node.  Exact XML and selector values stay under the
ignored evidence/private directory; console/shareable output contains only
counts and selector kinds.

The probe creates one temporary XML file on the device via `uiautomator dump`
and removes it after each capture.  It does not tap, swipe, install software, or
change application state.
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

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_observer import AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.ui_xml import (  # noqa: E402
    UiXmlError,
    filter_against_negative_xml,
    learn_selector_candidates,
    parse_ui_xml,
)

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"
REMOTE_XML = "/sdcard/genfarmer_python_ui_probe.xml"


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


def adb(device: str, *args: str, timeout: float = 12.0) -> subprocess.CompletedProcess[bytes]:
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


def capture_xml(device: str) -> str:
    errors: list[str] = []
    for dump_args in (
        ("shell", "uiautomator", "dump", "--compressed", REMOTE_XML),
        ("shell", "uiautomator", "dump", REMOTE_XML),
    ):
        proc = adb(device, *dump_args, timeout=15.0)
        if proc.returncode != 0:
            errors.append(proc.stderr.decode(errors="replace").strip() or f"exit {proc.returncode}")
            continue
        cat = adb(device, "exec-out", "cat", REMOTE_XML, timeout=10.0)
        if cat.returncode != 0:
            errors.append(cat.stderr.decode(errors="replace").strip() or f"cat exit {cat.returncode}")
            continue
        text = cat.stdout.decode("utf-8", errors="replace").strip()
        try:
            parse_ui_xml(text)
        except UiXmlError as exc:
            errors.append(str(exc))
            continue
        adb(device, "shell", "rm", "-f", REMOTE_XML, timeout=5.0)
        return text
    adb(device, "shell", "rm", "-f", REMOTE_XML, timeout=5.0)
    raise RuntimeError("uiautomator dump failed: " + " | ".join(errors[-2:]))


def load_negative_xml(path: Path | None) -> list[str]:
    if path is None:
        return []
    if not path.exists():
        raise RuntimeError(f"negative XML path not found: {path}")
    files = [path] if path.is_file() else sorted(path.rglob("*.xml"))
    values = [item.read_text(encoding="utf-8", errors="replace") for item in files]
    if not values:
        raise RuntimeError("negative XML path contains no .xml files")
    return values


def main() -> int:
    ap = argparse.ArgumentParser(description="Learn stable TikTok XPath candidates from repeated ADB UI XML dumps")
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB")
    ap.add_argument("--samples", type=int, default=3, help="repeated XML dumps, 2..8")
    ap.add_argument("--interval", type=float, default=0.4)
    ap.add_argument("--include-text", action="store_true", help="also consider stable non-dynamic text selectors")
    ap.add_argument("--negative-dir", type=Path, help="optional prior non-feed XML file/directory; candidates present there are rejected")
    args = ap.parse_args()

    if not 2 <= args.samples <= 8:
        print("ERROR: --samples must be 2..8", file=sys.stderr)
        return 2
    if args.interval < 0:
        print("ERROR: --interval must be non-negative", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not device:
        print("ERROR: configure DEFAULT_DEVICE_ADB or pass --device", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
    out = ROOT / "evidence" / f"tiktok-ui-xml-selector-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)

    try:
        observation = AdbObserver(device).observe()
        if observation.adb_state != "device" or not observation.tiktok_foreground or observation.interrupt is not InterruptKind.NONE:
            raise RuntimeError("TikTok foreground/no-interrupt precondition not proven")

        snapshots: list[str] = []
        for index in range(args.samples):
            xml = capture_xml(device)
            snapshots.append(xml)
            (private / f"ui-{index + 1:02d}.xml").write_text(xml, encoding="utf-8")
            if index + 1 < args.samples and args.interval:
                time.sleep(args.interval)

        candidates = learn_selector_candidates(
            snapshots,
            package=TIKTOK_PACKAGE,
            include_text=args.include_text,
        )
        negatives = load_negative_xml(args.negative_dir)
        if negatives:
            candidates = filter_against_negative_xml(candidates, negatives, package=TIKTOK_PACKAGE)

        exact = [candidate.to_dict() for candidate in candidates]
        (private / "candidates.private.json").write_text(json.dumps(exact, ensure_ascii=False, indent=2), encoding="utf-8")
        shareable = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "samples": len(snapshots),
            "candidate_count": len(candidates),
            "negative_filter_used": bool(negatives),
            "top_candidate_kind": candidates[0].kind if candidates else None,
            "top_candidate_unique_in_all": candidates[0].unique_in_all if candidates else False,
            "top_candidate_score": candidates[0].score if candidates else None,
            "selector_values_private": True,
        }
        shareable_path = out / "tiktok-ui-xml-selector.shareable.json"
        shareable_path.write_text(json.dumps(shareable, indent=2), encoding="utf-8")

        print("=" * 78)
        print("TIKTOK ADB UI-XML SELECTOR PROBE")
        print("=" * 78)
        print(f"Samples captured:        {len(snapshots)}")
        print(f"Stable candidates:       {len(candidates)}")
        print(f"Negative filter used:    {'YES' if negatives else 'NO'}")
        for index, candidate in enumerate(candidates[:10], 1):
            print(
                f"Candidate {index:02d}: kind={candidate.kind}, score={candidate.score}, "
                f"unique={'YES' if candidate.unique_in_all else 'NO'}, occurrences={candidate.occurrences}"
            )
        print(f"Private XML/candidates:  {private.relative_to(ROOT)}")
        print(f"Shareable result:        {shareable_path.relative_to(ROOT)}")
        if candidates:
            print("Next: patch a reviewed candidate into the GenFarmer ElementExists node with the private candidate file.")
        else:
            print("No safe stable selector candidate was learned from this sample.")
        print("=" * 78)
        return 0 if candidates else 1
    except (RuntimeError, UiXmlError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
