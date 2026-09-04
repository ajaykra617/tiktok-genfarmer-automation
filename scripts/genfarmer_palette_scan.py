#!/usr/bin/env python3
"""Read-only scanner for GenFarmer automation action tokens in ``app.asar``.

Purpose:
- complement live ``script.flow`` learning;
- discover likely automation node/action identifiers that may not yet appear in
  the user's existing Automation Apps;
- avoid extracting or modifying GenFarmer packaged files.

The shareable result contains only token-like action names, marker counts and
option-key candidates. It never includes raw source snippets.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]

ACTION_RE = re.compile(
    rb'''(?ix)
    ["']?action["']?\s*[:=]\s*["']
    ([A-Za-z0-9_.:/-]{1,120})
    ["']
    '''
)
KEY_RE = re.compile(rb'''["']?([A-Za-z_][A-Za-z0-9_-]{0,63})["']?\s*:''')

MARKERS = (
    b"nodeSleep",
    b"nodeTimeout",
    b"timeoutAdbReconnect",
    b"timeoutNextNode",
    b"successNode",
    b"failNode",
    b"sourcePosition",
    b"targetPosition",
    b"casePaths",
    b"breakpoint",
    b"outputVariable",
)

# These are useful structural keys, but not user data. If they occur near a
# likely action declaration we count them as candidate option/schema keys.
KEY_ALLOW = {
    "action", "options", "icon", "type", "disabled", "breakpoint",
    "nodeLog", "nodeSleep", "nodeTimeout", "timeoutAdbReconnect",
    "timeoutNextNode", "outputVariable", "successNode", "failNode",
    "timeout", "timeoutFrom", "timeoutTo", "timeoutType", "casePaths",
    "command", "sourcePosition", "targetPosition", "sourceHandle",
    "targetHandle", "package", "activity", "selector", "resourceId",
    "resourceID", "xpath", "xpathLite", "text", "className", "description",
    "x", "y", "duration", "direction", "variable", "value", "key",
}


def locate_app_asar(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path
        raise FileNotFoundError(path)

    candidates: list[Path] = []
    local = os.getenv("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Programs" / "GenFarmer" / "resources" / "app.asar")
    user = os.getenv("USERPROFILE")
    if user:
        candidates.append(Path(user) / "AppData" / "Local" / "Programs" / "GenFarmer" / "resources" / "app.asar")
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("GenFarmer resources/app.asar not found; pass --asar PATH")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only GenFarmer app.asar automation action scan")
    parser.add_argument("--asar", help="Explicit path to resources/app.asar")
    parser.add_argument("--chunk-mb", type=int, default=8)
    parser.add_argument("--context-bytes", type=int, default=1800)
    parser.add_argument("--min-score", type=int, default=2)
    args = parser.parse_args()

    try:
        asar = locate_app_asar(args.asar)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    chunk_size = max(1, args.chunk_mb) * 1024 * 1024
    context = max(256, args.context_bytes)
    overlap = max(context * 2, 8192)

    actions: dict[str, dict[str, object]] = {}
    global_key_counts: Counter[str] = Counter()
    scanned = 0
    carry = b""

    with asar.open("rb") as fh:
        while True:
            block = fh.read(chunk_size)
            if not block:
                break
            scanned += len(block)
            data = carry + block
            for match in ACTION_RE.finditer(data):
                try:
                    token = match.group(1).decode("ascii")
                except UnicodeDecodeError:
                    continue
                start = max(0, match.start() - context)
                end = min(len(data), match.end() + context)
                window = data[start:end]
                marker_hits = {m.decode("ascii"): window.count(m) for m in MARKERS if m in window}
                score = len(marker_hits)
                # Boost objects that look like Vue Flow automation node definitions.
                if b"options" in window:
                    score += 1
                if b"icon" in window:
                    score += 1
                if b"custom" in window:
                    score += 1

                entry = actions.setdefault(
                    token,
                    {
                        "action": token,
                        "occurrences": 0,
                        "max_confidence_score": 0,
                        "marker_counts": Counter(),
                        "nearby_schema_keys": Counter(),
                    },
                )
                entry["occurrences"] = int(entry["occurrences"]) + 1
                entry["max_confidence_score"] = max(int(entry["max_confidence_score"]), score)
                marker_counter = entry["marker_counts"]
                assert isinstance(marker_counter, Counter)
                marker_counter.update(marker_hits)

                key_counter = entry["nearby_schema_keys"]
                assert isinstance(key_counter, Counter)
                for key_match in KEY_RE.finditer(window):
                    try:
                        key = key_match.group(1).decode("ascii")
                    except UnicodeDecodeError:
                        continue
                    if key in KEY_ALLOW:
                        key_counter[key] += 1
                        global_key_counts[key] += 1

            carry = data[-overlap:] if len(data) > overlap else data

    selected = []
    for token, raw in actions.items():
        score = int(raw["max_confidence_score"])
        if score < args.min_score:
            continue
        markers = raw["marker_counts"]
        keys = raw["nearby_schema_keys"]
        assert isinstance(markers, Counter)
        assert isinstance(keys, Counter)
        selected.append(
            {
                "action": token,
                "occurrences": int(raw["occurrences"]),
                "confidence_score": score,
                "marker_counts": dict(markers.most_common()),
                "nearby_schema_keys": [
                    {"key": key, "count": count}
                    for key, count in keys.most_common(40)
                ],
            }
        )
    selected.sort(key=lambda item: (-item["confidence_score"], -item["occurrences"], item["action"]))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = ROOT / "evidence" / f"genfarmer-palette-scan-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_path = evidence_dir / "palette-candidates.shareable.json"
    output = {
        "catalog_format": 1,
        "privacy": "shareable token-only static scan; no raw app.asar source snippets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "genfarmer_package": "resources/app.asar",
        "bytes_scanned": scanned,
        "min_confidence_score": args.min_score,
        "action_candidates": selected,
        "global_nearby_schema_keys": [
            {"key": key, "count": count}
            for key, count in global_key_counts.most_common(80)
        ],
    }
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 76)
    print("GENFARMER PACKAGED NODE/ACTION PALETTE SCAN")
    print("=" * 76)
    print(f"Source: {asar}")
    print("Mode: read-only; no extraction or modification")
    print(f"Bytes scanned: {scanned}")
    print(f"High-confidence action candidates: {len(selected)}")
    for item in selected[:80]:
        print(
            f" - {item['action']}: score={item['confidence_score']} "
            f"occurrences={item['occurrences']}"
        )
    if len(selected) > 80:
        print(f" ... {len(selected) - 80} more saved locally")
    print(f"Shareable result: {out_path.relative_to(ROOT)}")
    print("No GenFarmer files were modified.")
    print("=" * 76)
    return 0 if selected else 1


if __name__ == "__main__":
    raise SystemExit(main())
