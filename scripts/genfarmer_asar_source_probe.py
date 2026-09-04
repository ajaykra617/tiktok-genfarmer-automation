#!/usr/bin/env python3
"""Read-only source probe for GenFarmer's Electron ``app.asar`` archive.

This script opens the ASAR archive structurally rather than scanning the entire
248 MB file as an opaque byte stream. It searches text-bearing bundled files for
known Automation palette labels and then reports nearby token/field candidates
without emitting raw proprietary source snippets.

It does not modify GenFarmer, extract source into the repository, click the UI,
or call any GenFarmer mutation API.
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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

try:
    from asar import AsarArchive
except ImportError:  # pragma: no cover - user-facing dependency error
    print(
        'ERROR: Python package "asar" is missing. Run: python -m pip install -e ".[dev]"',
        file=sys.stderr,
    )
    raise SystemExit(2)


KNOWN_PALETTE_ANCHORS = (
    "Press Back",
    "Press Home",
    "Press Menu",
    "Change device",
    "Start App",
    "Stop App",
    "Install App",
    "Variables",
    "Context Menu",
    "ADB shell command",
    "Sleep",
    "Screenshot",
    "DeepSeek",
)

KNOWN_RUNTIME_KEYS = (
    "action",
    "type",
    "nodeType",
    "category",
    "group",
    "label",
    "title",
    "successNode",
    "failNode",
    "nodeLog",
    "nodeSleep",
    "nodeTimeout",
    "timeoutAdbReconnect",
    "timeoutNextNode",
    "timeoutType",
    "timeoutFrom",
    "timeoutTo",
    "outputVariable",
    "casePaths",
    "breakpoint",
    "disabled",
    "sourceHandle",
    "targetHandle",
)

TEXT_SUFFIXES = {
    ".js",
    ".mjs",
    ".cjs",
    ".json",
    ".html",
    ".css",
    ".vue",
    ".ts",
    ".tsx",
    ".jsx",
}

# Captures safe string-valued object properties without reproducing source.
SAFE_FIELD_VALUE_RE = re.compile(
    r'''(?:(?:["'])?(label|title|name|action|type|nodeType|category|group)(?:["'])?)\s*:\s*(["'])([^"'\r\n]{1,120})\2'''
)

# Generic object-key collector used only as a structural hint.
OBJECT_KEY_RE = re.compile(r'''(?:^|[,{])\s*(?:["'])?([A-Za-z_$][A-Za-z0-9_$]{1,64})(?:["'])?\s*:''')

NOISY_KEYS = {
    "data",
    "value",
    "key",
    "name",
    "length",
    "children",
    "style",
    "class",
    "className",
    "props",
    "id",
    "x",
    "y",
    "width",
    "height",
    "color",
    "icon",
    "text",
    "description",
}


def default_asar_path() -> Path:
    local = os.getenv("LOCALAPPDATA")
    if not local:
        return Path("resources/app.asar")
    return Path(local) / "Programs" / "GenFarmer" / "resources" / "app.asar"


def to_text(raw: Any) -> str | None:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode("utf-8", errors="ignore")
    return None


def safe_value(value: str) -> str | None:
    value = value.strip()
    if not value or len(value) > 120:
        return None
    # Keep only token/label-like strings. Reject URLs, email-like values and
    # strings with braces/newlines that could carry app-specific content.
    if any(ch in value for ch in ("\n", "\r", "{", "}", "@")):
        return None
    if value.startswith(("http://", "https://")):
        return None
    return value


def windows_around(text: str, needle: str, radius: int) -> list[str]:
    lowered = text.lower()
    target = needle.lower()
    windows: list[str] = []
    start = 0
    while True:
        idx = lowered.find(target, start)
        if idx < 0:
            break
        left = max(0, idx - radius)
        right = min(len(text), idx + len(needle) + radius)
        windows.append(text[left:right])
        start = idx + len(target)
        if len(windows) >= 30:
            break
    return windows


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only structured source probe for GenFarmer app.asar")
    parser.add_argument("--asar", type=Path, default=default_asar_path())
    parser.add_argument("--window", type=int, default=8000, help="Characters around each known palette label to inspect")
    parser.add_argument("--max-file-mb", type=int, default=96, help="Skip individual bundled text files larger than this")
    args = parser.parse_args()

    archive_path = args.asar.expanduser().resolve()
    if not archive_path.exists():
        print(f"ERROR: app.asar not found: {archive_path}", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-asar-source-probe-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    matched_files: list[dict[str, Any]] = []
    anchor_summary: dict[str, dict[str, Any]] = {}
    for anchor in KNOWN_PALETTE_ANCHORS:
        anchor_summary[anchor] = {
            "files": 0,
            "occurrences": 0,
            "safe_field_values": defaultdict(Counter),
            "nearby_runtime_keys": Counter(),
            "nearby_structural_keys": Counter(),
        }

    invalid_args_files: list[str] = []
    scanned_files = 0
    scanned_bytes = 0
    skipped_large = 0
    read_failures = 0

    max_bytes = max(1, args.max_file_mb) * 1024 * 1024

    try:
        archive_ctx = AsarArchive(archive_path, mode="r")
    except TypeError:
        # Compatibility with older PyASAR constructor shape.
        archive_ctx = AsarArchive.open(str(archive_path))

    with archive_ctx as archive:
        try:
            entries = list(archive.list())
        except Exception as exc:
            print(f"ERROR: cannot list ASAR archive: {exc}", file=sys.stderr)
            return 1

        for entry in entries:
            path = Path(str(entry))
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                raw = archive.read(path, follow_link=True)
            except TypeError:
                try:
                    raw = archive.read(path)
                except Exception:
                    read_failures += 1
                    continue
            except Exception:
                read_failures += 1
                continue

            if isinstance(raw, (bytes, bytearray)) and len(raw) > max_bytes:
                skipped_large += 1
                continue
            text = to_text(raw)
            if text is None:
                continue

            scanned_files += 1
            scanned_bytes += len(text.encode("utf-8", errors="ignore"))

            if "Invalid args. Exiting..." in text:
                invalid_args_files.append(path.as_posix())

            matched = [anchor for anchor in KNOWN_PALETTE_ANCHORS if anchor.lower() in text.lower()]
            if not matched:
                continue

            file_record = {
                "path": path.as_posix(),
                "matched_anchors": matched,
                "anchor_count": len(matched),
            }
            matched_files.append(file_record)

            for anchor in matched:
                summary = anchor_summary[anchor]
                windows = windows_around(text, anchor, max(1000, args.window))
                summary["files"] += 1
                summary["occurrences"] += len(windows)

                for window in windows:
                    for key in KNOWN_RUNTIME_KEYS:
                        count = len(re.findall(re.escape(key), window, flags=re.IGNORECASE))
                        if count:
                            summary["nearby_runtime_keys"][key] += count

                    for field, _, raw_value in SAFE_FIELD_VALUE_RE.findall(window):
                        value = safe_value(raw_value)
                        if value is not None:
                            summary["safe_field_values"][field][value] += 1

                    for key in OBJECT_KEY_RE.findall(window):
                        if key not in NOISY_KEYS:
                            summary["nearby_structural_keys"][key] += 1

    serial_anchors: list[dict[str, Any]] = []
    for anchor in KNOWN_PALETTE_ANCHORS:
        summary = anchor_summary[anchor]
        if not summary["files"]:
            continue
        serial_anchors.append(
            {
                "anchor": anchor,
                "files": summary["files"],
                "occurrences": summary["occurrences"],
                "safe_field_values": {
                    field: [
                        {"value": value, "count": count}
                        for value, count in counter.most_common(40)
                    ]
                    for field, counter in sorted(summary["safe_field_values"].items())
                },
                "nearby_runtime_keys": dict(summary["nearby_runtime_keys"].most_common()),
                "nearby_structural_keys": [
                    {"key": key, "count": count}
                    for key, count in summary["nearby_structural_keys"].most_common(80)
                ],
            }
        )

    matched_files.sort(key=lambda item: (-item["anchor_count"], item["path"]))

    result = {
        "catalog_format": 1,
        "privacy": "shareable token/structure-only ASAR source probe; no raw bundled source snippets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "genfarmer_package": "resources/app.asar",
        "archive_size_bytes": archive_path.stat().st_size,
        "text_files_scanned": scanned_files,
        "text_bytes_scanned": scanned_bytes,
        "large_text_files_skipped": skipped_large,
        "read_failures": read_failures,
        "known_palette_anchors_requested": list(KNOWN_PALETTE_ANCHORS),
        "known_palette_anchors_found": [item["anchor"] for item in serial_anchors],
        "matched_source_files": matched_files[:100],
        "anchor_analysis": serial_anchors,
        "invalid_args_message_source_files": sorted(set(invalid_args_files))[:20],
    }

    out_path = out_dir / "asar-source-probe.shareable.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER STRUCTURED APP.ASAR SOURCE PROBE")
    print("=" * 78)
    print(f"Archive: {archive_path}")
    print(f"Text files scanned: {scanned_files}")
    print(f"Known palette labels found: {len(serial_anchors)}/{len(KNOWN_PALETTE_ANCHORS)}")
    for item in serial_anchors:
        print(f" - {item['anchor']}: files={item['files']} occurrences={item['occurrences']}")
    print("Top source files by known-node coverage:")
    for item in matched_files[:12]:
        print(f" - {item['path']}: {item['anchor_count']} anchor(s)")
    if invalid_args_files:
        print("Found source file(s) containing 'Invalid args. Exiting...' (reported in JSON).")
    print(f"Shareable result: {out_path.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified or extracted into the repository.")
    print("=" * 78)

    return 0 if serial_anchors else 1


if __name__ == "__main__":
    raise SystemExit(main())
