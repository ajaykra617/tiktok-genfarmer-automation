#!/usr/bin/env python3
"""Find the best already-qualified feed-anchor selectors that survive another device.

This is read-only. It loads the private ranked candidate set from the source
device and hierarchy XML already captured on the target device, then evaluates
all candidates. Exact selector values remain private and are never printed.

The private survivors file preserves original ranking order and adds
``source_rank`` metadata so downstream tooling can retarget the live GenFarmer
ElementExists node without re-running selector discovery.
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

from genfarmer_automation.cross_device_anchor import (  # noqa: E402
    evaluate_cross_device_candidates,
    survivor_ranks,
)
from genfarmer_automation.feed_anchor_qualification import (  # noqa: E402
    FeedAnchorQualificationError,
    candidates_from_payload,
)
from genfarmer_automation.feed_anchor_variation import FeedAnchorVariationError  # noqa: E402
from genfarmer_automation.ui_xml import UiXmlError  # noqa: E402

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


def main() -> int:
    ap = argparse.ArgumentParser(description="Sweep ranked TikTok feed anchors across target-device hierarchy XML")
    ap.add_argument("candidates", type=Path, help="private ranked-candidates.private.json from the source device")
    ap.add_argument("--xml-dir", type=Path, required=True, help="private target-device hierarchy directory")
    ap.add_argument("--min-samples", type=int, default=3)
    ap.add_argument("--show", type=int, default=8, help="number of survivor ranks to print, 1..20")
    args = ap.parse_args()

    if args.min_samples < 2:
        print("ERROR: --min-samples must be >= 2", file=sys.stderr)
        return 2
    if not 1 <= args.show <= 20:
        print("ERROR: --show must be 1..20", file=sys.stderr)
        return 2

    try:
        raw = json.loads(args.candidates.expanduser().read_text(encoding="utf-8"))
        candidates = candidates_from_payload(raw)
        if not candidates:
            raise FeedAnchorQualificationError("candidate file contained no usable selectors")

        xml_files = sorted(args.xml_dir.expanduser().glob("ui-*.xml"))
        if len(xml_files) < args.min_samples:
            raise RuntimeError(
                f"expected at least {args.min_samples} hierarchy samples in {args.xml_dir}; found {len(xml_files)}"
            )
        snapshots = [path.read_text(encoding="utf-8") for path in xml_files]
        results = evaluate_cross_device_candidates(
            candidates,
            snapshots,
            package=TIKTOK_PACKAGE,
        )
        ranks = survivor_ranks(results)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = ROOT / "evidence" / f"tiktok-feed-anchor-cross-device-sweep-{stamp}"
        private = out / "private"
        private.mkdir(parents=True, exist_ok=True)

        survivor_payload: list[dict[str, object]] = []
        if not isinstance(raw, list):
            raise FeedAnchorQualificationError("candidate payload must be a list")
        for rank in ranks:
            original = raw[rank - 1]
            if not isinstance(original, dict):
                continue
            copied = dict(original)
            copied["source_rank"] = rank
            survivor_payload.append(copied)
        survivors_file = private / "survivors.private.json"
        survivors_file.write_text(json.dumps(survivor_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        result = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if ranks else "NO_COMMON_SELECTOR",
            "input_candidates": len(candidates),
            "target_xml_samples": len(snapshots),
            "survivor_count": len(ranks),
            "best_source_rank": ranks[0] if ranks else None,
            "best_kind": candidates[ranks[0] - 1].kind if ranks else None,
            "selector_values_private": True,
            "app_ui_actions": 0,
        }
        shareable = out / "tiktok-feed-anchor-cross-device-sweep.shareable.json"
        shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print("=" * 78)
        print("TIKTOK FEED-ANCHOR CROSS-DEVICE SWEEP")
        print("=" * 78)
        print(f"Status:                    {result['status']}")
        print(f"Source ranked candidates:  {len(candidates)}")
        print(f"Target hierarchy samples:  {len(snapshots)}")
        print(f"Cross-device survivors:    {len(ranks)}")
        if ranks:
            print(f"Best source rank:          {ranks[0]} ({candidates[ranks[0] - 1].kind})")
            for display_index, rank in enumerate(ranks[: args.show], start=1):
                item = results[rank - 1]
                print(
                    f"Survivor {display_index:02d}: source_rank={rank}, kind={item.kind}, occurrences={item.counts}"
                )
        print("Exact selector values:      PRIVATE / NOT PRINTED")
        print("App UI actions:             NONE")
        print(f"Private survivors file:    {survivors_file.relative_to(ROOT)}")
        print(f"Shareable result:          {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0 if ranks else 1
    except (
        OSError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
        FeedAnchorQualificationError,
        FeedAnchorVariationError,
        UiXmlError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
