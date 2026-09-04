#!/usr/bin/env python3
"""Strict read-only static scanner for GenFarmer 2.6.1 automation action tokens.

The first broad package scan produced false positives because generic application
code also contains fields named "action". This scanner is intentionally stricter:
it only considers PascalCase action tokens and boosts candidates that appear near
known GenFarmer runtime node fields such as nodeTimeout, successNode, failNode,
breakpoint, disabled, outputVariable, casePaths, and timeoutAdbReconnect.

No source snippets are emitted. Only action tokens and aggregate marker counts are
written to the shareable result.
"""

from __future__ import annotations

from collections import Counter
import argparse
import json
import mmap
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.flow_catalog_261 import VERIFIED_ACTIONS  # noqa: E402

DEFAULT_ASAR = (
    Path.home()
    / "AppData"
    / "Local"
    / "Programs"
    / "GenFarmer"
    / "resources"
    / "app.asar"
)

ACTION_RE = re.compile(
    rb"(?:[\"']action[\"']|\baction)\s*:\s*[\"']([A-Z][A-Za-z0-9_.-]{1,80})[\"']"
)

RUNTIME_MARKERS = (
    b"nodeSleep",
    b"nodeTimeout",
    b"timeoutAdbReconnect",
    b"timeoutNextNode",
    b"successNode",
    b"failNode",
    b"breakpoint",
    b"disabled",
    b"outputVariable",
    b"casePaths",
    b"timeoutType",
    b"sourcePosition",
    b"targetPosition",
)

KNOWN_LIVE_ACTIONS = {spec.action for spec in VERIFIED_ACTIONS.values()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict read-only GenFarmer app.asar action scanner")
    parser.add_argument("--asar", type=Path, default=DEFAULT_ASAR)
    parser.add_argument("--window", type=int, default=2200)
    parser.add_argument("--min-score", type=int, default=4)
    args = parser.parse_args()

    asar = args.asar.expanduser().resolve()
    if not asar.is_file():
        print(f"ERROR: app.asar not found: {asar}", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = ROOT / "evidence" / f"genfarmer-palette-scan-v2-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    stats: dict[str, dict] = {}
    raw_matches = 0

    with asar.open("rb") as fh:
        with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            size = len(mm)
            for match in ACTION_RE.finditer(mm):
                raw_matches += 1
                action = match.group(1).decode("ascii", errors="ignore")
                start = max(0, match.start() - max(256, args.window))
                end = min(size, match.end() + max(256, args.window))
                window = mm[start:end]

                marker_counts = {
                    marker.decode("ascii"): window.count(marker)
                    for marker in RUNTIME_MARKERS
                    if window.count(marker)
                }

                score = 0
                if action in KNOWN_LIVE_ACTIONS:
                    score += 8
                score += len(marker_counts)
                if len(marker_counts) >= 3:
                    score += 2
                if any(k in marker_counts for k in ("successNode", "failNode")):
                    score += 2
                if any(k in marker_counts for k in ("nodeTimeout", "timeoutAdbReconnect", "timeoutNextNode")):
                    score += 2

                entry = stats.setdefault(
                    action,
                    {
                        "action": action,
                        "occurrences": 0,
                        "best_score": 0,
                        "marker_counts": Counter(),
                        "live_verified": action in KNOWN_LIVE_ACTIONS,
                    },
                )
                entry["occurrences"] += 1
                entry["best_score"] = max(entry["best_score"], score)
                entry["marker_counts"].update(marker_counts)

    candidates = []
    for action, entry in sorted(stats.items()):
        if entry["best_score"] < args.min_score and not entry["live_verified"]:
            continue
        candidates.append(
            {
                "action": action,
                "occurrences": entry["occurrences"],
                "best_score": entry["best_score"],
                "live_verified": entry["live_verified"],
                "marker_counts": dict(sorted(entry["marker_counts"].items())),
            }
        )

    candidates.sort(key=lambda item: (-item["live_verified"], -item["best_score"], item["action"]))

    live_found = sorted(item["action"] for item in candidates if item["live_verified"])
    package_only = sorted(item["action"] for item in candidates if not item["live_verified"])

    output = {
        "catalog_format": 2,
        "privacy": "shareable strict token-only static scan; no raw app.asar source snippets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "genfarmer_package": "resources/app.asar",
        "bytes_scanned": asar.stat().st_size,
        "raw_action_syntax_matches": raw_matches,
        "min_confidence_score": args.min_score,
        "known_live_actions": sorted(KNOWN_LIVE_ACTIONS),
        "known_live_actions_found_in_package_scan": live_found,
        "package_only_candidates": package_only,
        "action_candidates": candidates,
    }

    out_path = evidence_dir / "palette-candidates-v2.shareable.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 76)
    print("GENFARMER STRICT PALETTE / ACTION SCAN V2")
    print("=" * 76)
    print(f"Package: {asar}")
    print(f"Bytes scanned: {asar.stat().st_size}")
    print(f"Raw action-syntax matches: {raw_matches}")
    print(f"High-confidence candidates: {len(candidates)}")
    print(f"Known live actions found: {len(live_found)}/{len(KNOWN_LIVE_ACTIONS)}")
    print("Candidates:")
    for item in candidates:
        marker_summary = ",".join(item["marker_counts"].keys()) or "-"
        status = "LIVE" if item["live_verified"] else "PACKAGE-ONLY"
        print(f" - {item['action']}: {status} score={item['best_score']} markers={marker_summary}")
    print(f"Shareable result: {out_path.relative_to(ROOT)}")
    print("Read-only; no GenFarmer files were modified or extracted.")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
