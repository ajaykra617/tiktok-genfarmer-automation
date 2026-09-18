#!/usr/bin/env python3
"""Merge private interaction JSONL traces into a readable diagnostic timeline."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys


def _load(directory: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(directory.glob("trace-*.jsonl")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{path}:{number}: invalid JSONL: {exc}") from exc
            if isinstance(row, dict):
                row["_source"] = path.name
                rows.append(row)
    rows.sort(key=lambda row: (str(row.get("timestamp_utc", "")), int(row.get("pid", 0)), int(row.get("sequence", 0))))
    return rows


def _compact(value, limit: int = 500) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= limit else text[: limit - 3] + "..."


def main() -> int:
    ap = argparse.ArgumentParser(description="Readable merged interaction trace report")
    ap.add_argument("trace_dir", type=Path)
    ap.add_argument("--tail", type=int, default=200)
    ap.add_argument("--focus-errors-live", action="store_true")
    args = ap.parse_args()

    if not args.trace_dir.is_dir():
        print(f"ERROR: trace directory not found: {args.trace_dir}", file=sys.stderr)
        return 2
    rows = _load(args.trace_dir)
    if not rows:
        print("ERROR: no trace-*.jsonl files found", file=sys.stderr)
        return 2

    categories = Counter(str(row.get("category", "unknown")) for row in rows)
    levels = Counter(str(row.get("level", "INFO")) for row in rows)
    devices = sorted({str(row.get("device")) for row in rows if row.get("device")})

    print("=" * 100)
    print("INTERACTION TRACE REPORT")
    print("=" * 100)
    print(f"Trace directory: {args.trace_dir}")
    print(f"Events:          {len(rows)}")
    print(f"Devices:         {', '.join(devices) if devices else '-'}")
    print(f"Categories:      {dict(categories)}")
    print(f"Levels:          {dict(levels)}")

    selected = rows
    if args.focus_errors_live:
        selected = [
            row for row in rows
            if str(row.get("level", "INFO")).upper() in {"ERROR", "WARNING"}
            or str(row.get("category", "")).casefold() == "live"
            or "timeout" in str(row.get("event", "")).casefold()
            or "restart" in str(row.get("event", "")).casefold()
        ]
    if args.tail > 0:
        selected = selected[-args.tail:]

    print("-" * 100)
    for row in selected:
        ts = str(row.get("timestamp_utc", ""))
        device = str(row.get("device") or "-")
        category = str(row.get("category") or "-")
        event = str(row.get("event") or "-")
        level = str(row.get("level") or "INFO")
        details = _compact(row.get("details", {}))
        print(f"{ts} [{device}] {level:<7} {category}.{event} {details}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
