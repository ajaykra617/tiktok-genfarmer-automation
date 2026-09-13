#!/usr/bin/env python3
"""Rank robust feed-anchor candidates using feed-state geometry.

Input candidates should already have survived negative-screen qualification and
positive feed-variation qualification.  Exact selector values remain in ignored
private evidence; console/shareable output exposes only structural metrics.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.feed_anchor_qualification import candidates_from_payload  # noqa: E402
from genfarmer_automation.feed_anchor_ranking import (  # noqa: E402
    FeedAnchorRankingError,
    rank_feed_anchor_candidates,
)

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


def main() -> int:
    ap = argparse.ArgumentParser(description="Rank already-qualified TikTok feed-anchor selectors")
    ap.add_argument("candidates", type=Path, help="qualified-candidates.private.json from positive variation")
    ap.add_argument("--xml-dir", type=Path, required=True, help="private directory containing feed-*.xml positive snapshots")
    args = ap.parse_args()

    try:
        raw = json.loads(args.candidates.expanduser().read_text(encoding="utf-8"))
        candidates = candidates_from_payload(raw)
        xml_paths = sorted(args.xml_dir.expanduser().glob("feed-*.xml"))
        if len(xml_paths) < 2:
            raise RuntimeError("--xml-dir must contain at least two feed-*.xml snapshots")
        xml = [path.read_text(encoding="utf-8") for path in xml_paths]
        ranked = rank_feed_anchor_candidates(candidates, xml, package=TIKTOK_PACKAGE)
        if not ranked:
            raise RuntimeError("no candidate retained usable unique geometry across the supplied feed snapshots")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = ROOT / "evidence" / f"tiktok-feed-anchor-ranking-{stamp}"
        private = out / "private"
        private.mkdir(parents=True, exist_ok=True)
        ranked_path = private / "ranked-candidates.private.json"
        ranked_path.write_text(
            json.dumps([item.to_private_dict() for item in ranked], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        top = ranked[0]
        margin = top.rank_score - ranked[1].rank_score if len(ranked) > 1 else top.rank_score
        result = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "input_candidates": len(candidates),
            "positive_xml_snapshots": len(xml),
            "ranked_candidates": len(ranked),
            "top_kind": top.candidate.kind,
            "top_rank_score": round(top.rank_score, 3),
            "top_median_area_ratio": round(top.median_area_ratio, 6),
            "top_center_coverage_ratio": round(top.center_coverage_ratio, 6),
            "top_geometry_stability": round(top.geometry_stability, 6),
            "top_score_margin": round(margin, 3),
            "selector_values_private": True,
        }
        shareable = out / "tiktok-feed-anchor-ranking.shareable.json"
        shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print("=" * 78)
        print("TIKTOK FEED-ANCHOR ROBUSTNESS RANKING")
        print("=" * 78)
        print(f"Input qualified candidates: {len(candidates)}")
        print(f"Positive feed snapshots:    {len(xml)}")
        print(f"Ranked candidates:          {len(ranked)}")
        for index, item in enumerate(ranked[:8], 1):
            print(
                f"Rank {index:02d}: kind={item.candidate.kind}, score={item.rank_score:.1f}, "
                f"area={item.median_area_ratio * 100:.1f}%, center={item.center_coverage_ratio * 100:.0f}%, "
                f"geometry_stability={item.geometry_stability * 100:.0f}%"
            )
        print("Exact selector values:      PRIVATE / NOT PRINTED")
        print(f"Private ranked file:        {ranked_path.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("Next: patch ranked candidate 1 into the feed-anchor ElementExists lab flow.")
        print("=" * 78)
        return 0
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError, FeedAnchorRankingError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
