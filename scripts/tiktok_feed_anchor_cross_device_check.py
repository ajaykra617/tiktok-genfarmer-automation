#!/usr/bin/env python3
"""Validate one ranked feed-anchor selector against hierarchy XML on another device.

This is read-only. It does not launch, tap, swipe, create sessions, or mutate
GenFarmer. It consumes hierarchy XML already captured by
`tiktok_uia2_runtime_discovery.py` on the target device and checks that the
selected ranked selector appears exactly once in every sample.

Exact selector values remain private and are never printed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.feed_anchor_qualification import (  # noqa: E402
    FeedAnchorQualificationError,
    candidates_from_payload,
)
from genfarmer_automation.feed_anchor_variation import (  # noqa: E402
    FeedAnchorVariationError,
    candidate_counts,
)
from genfarmer_automation.ui_xml import UiXmlError  # noqa: E402

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a ranked TikTok feed anchor on hierarchy XML from another device")
    ap.add_argument("candidates", type=Path, help="private ranked-candidates.private.json")
    ap.add_argument("--xml-dir", type=Path, required=True, help="private directory from tiktok_uia2_runtime_discovery.py")
    ap.add_argument("--candidate", type=int, default=1, help="1-based ranked candidate index")
    ap.add_argument("--min-samples", type=int, default=3, help="minimum hierarchy samples required")
    args = ap.parse_args()

    if args.candidate < 1:
        print("ERROR: --candidate must be >= 1", file=sys.stderr)
        return 2
    if args.min_samples < 2:
        print("ERROR: --min-samples must be >= 2", file=sys.stderr)
        return 2

    try:
        raw = json.loads(args.candidates.expanduser().read_text(encoding="utf-8"))
        candidates = candidates_from_payload(raw)
        if not (1 <= args.candidate <= len(candidates)):
            raise FeedAnchorQualificationError("ranked candidate file does not contain the requested candidate")
        selected = candidates[args.candidate - 1]

        xml_files = sorted(args.xml_dir.expanduser().glob("ui-*.xml"))
        if len(xml_files) < args.min_samples:
            raise RuntimeError(
                f"expected at least {args.min_samples} hierarchy samples in {args.xml_dir}; found {len(xml_files)}"
            )
        snapshots = [path.read_text(encoding="utf-8") for path in xml_files]
        counts = candidate_counts(selected, snapshots, package=TIKTOK_PACKAGE)
        passed = bool(counts) and all(count == 1 for count in counts)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = ROOT / "evidence" / f"tiktok-feed-anchor-cross-device-{stamp}"
        out.mkdir(parents=True, exist_ok=True)
        result = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if passed else "FAIL",
            "candidate_index": args.candidate,
            "candidate_kind": selected.kind,
            "xml_samples": len(snapshots),
            "occurrences": list(counts),
            "present_exactly_once_in_all": passed,
            "selector_value_private": True,
            "app_ui_actions": 0,
        }
        shareable = out / "tiktok-feed-anchor-cross-device.shareable.json"
        shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print("=" * 78)
        print("TIKTOK FEED-ANCHOR CROSS-DEVICE CHECK")
        print("=" * 78)
        print(f"Status:                    {'PASS' if passed else 'FAIL'}")
        print(f"Ranked candidate:          {args.candidate} ({selected.kind})")
        print(f"Hierarchy samples:         {len(snapshots)}")
        print(f"Occurrences per sample:    {counts}")
        print(f"Exactly once in all:       {'YES' if passed else 'NO'}")
        print("Exact selector value:      PRIVATE / NOT PRINTED")
        print("App UI actions:            NONE")
        print(f"Shareable result:          {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0 if passed else 1
    except (
        OSError,
        json.JSONDecodeError,
        RuntimeError,
        FeedAnchorQualificationError,
        FeedAnchorVariationError,
        UiXmlError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
