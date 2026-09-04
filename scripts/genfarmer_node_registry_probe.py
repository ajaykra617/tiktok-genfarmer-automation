#!/usr/bin/env python3
"""Focused read-only probe for GenFarmer's Automation node registry bundle.

The structured ASAR probe identified ``dist/render/assets/useScriptEditor-*.js``
as the renderer bundle containing all known Automation palette labels. This
script analyzes that bundle specifically and emits a privacy-safe catalog of
likely node labels, internal semantic tokens, category/group values, and nearby
configuration keys.

No GenFarmer files are modified. Raw proprietary source snippets are never
written to the repository or shareable output.
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
except ImportError:  # pragma: no cover
    print('ERROR: Python package "asar" is missing. Run: python -m pip install -e ".[dev]"', file=sys.stderr)
    raise SystemExit(2)

DEFAULT_BUNDLE = "dist/render/assets/useScriptEditor-HioTuYH4.js"

KNOWN_ANCHORS = (
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

SAFE_FIELDS = (
    "label",
    "title",
    "name",
    "action",
    "type",
    "nodeType",
    "category",
    "group",
)

RUNTIME_KEYS = (
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
    "timeout",
    "outputVariable",
    "casePaths",
    "breakpoint",
    "disabled",
    "sourceHandle",
    "targetHandle",
    "packageName",
    "package",
    "activity",
    "command",
    "selector",
    "xpath",
    "resourceId",
    "text",
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "duration",
    "direction",
    "mode",
    "value",
    "variable",
    "variableName",
    "filePath",
    "path",
    "url",
    "method",
    "headers",
    "body",
)

FIELD_VALUE_RE = re.compile(
    r'''(?:(?:["'])?(label|title|name|action|type|nodeType|category|group)(?:["'])?)\s*:\s*(["'])([^"'\r\n]{1,160})\2'''
)
OBJECT_KEY_RE = re.compile(r'''(?:^|[,{])\s*(?:["'])?([A-Za-z_$][A-Za-z0-9_$]{1,80})(?:["'])?\s*:''')
STRING_RE = re.compile(r'''(["'])([^"'\r\n]{2,100})\1''')

NOISY_UI = {
    "Save", "Run", "Cancel", "Close", "Delete", "Edit", "Search", "Back",
    "OK", "Yes", "No", "Settings", "Device view", "Inspector", "My app",
    "Add", "Remove", "Open", "Confirm", "Error", "Success", "Warning",
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


def safe_token(value: str) -> str | None:
    value = value.strip()
    if not value or len(value) > 160:
        return None
    if any(ch in value for ch in ("\n", "\r", "{", "}", "@")):
        return None
    if value.startswith(("http://", "https://")):
        return None
    return value


def is_human_label(value: str) -> bool:
    value = value.strip()
    if value in NOISY_UI or len(value) < 3 or len(value) > 64:
        return False
    if value.startswith(("http://", "https://", "./", "../")):
        return False
    if any(ch in value for ch in ("{", "}", "=", ";", "\\", "@")):
        return False
    letters = sum(ch.isalpha() for ch in value)
    if letters < 3:
        return False
    # Favor palette-like display text rather than long prose/messages.
    words = value.split()
    if len(words) > 8:
        return False
    return True


def open_archive(path: Path):
    try:
        return AsarArchive(path, mode="r")
    except TypeError:
        return AsarArchive.open(str(path))


def read_bundle(archive, bundle: str) -> str:
    p = Path(bundle)
    try:
        raw = archive.read(p, follow_link=True)
    except TypeError:
        raw = archive.read(p)
    text = to_text(raw)
    if text is None:
        raise ValueError(f"bundle is not text: {bundle}")
    return text


def nearest_window(text: str, index: int, radius: int) -> str:
    return text[max(0, index - radius):min(len(text), index + radius)]


def association_record(window: str) -> dict[str, Any]:
    fields: dict[str, Counter[str]] = defaultdict(Counter)
    for field, _, raw in FIELD_VALUE_RE.findall(window):
        value = safe_token(raw)
        if value is not None:
            fields[field][value] += 1

    keys = Counter(OBJECT_KEY_RE.findall(window))
    runtime = {key: keys[key] for key in RUNTIME_KEYS if keys[key]}

    return {
        "safe_fields": {
            field: [
                {"value": value, "count": count}
                for value, count in counter.most_common(20)
            ]
            for field, counter in sorted(fields.items())
        },
        "runtime_keys": runtime,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Focused GenFarmer Automation node registry probe")
    parser.add_argument("--asar", type=Path, default=default_asar_path())
    parser.add_argument("--bundle", default=DEFAULT_BUNDLE)
    parser.add_argument("--radius", type=int, default=2200, help="Characters around each candidate label to inspect")
    args = parser.parse_args()

    archive_path = args.asar.expanduser().resolve()
    if not archive_path.exists():
        print(f"ERROR: app.asar not found: {archive_path}", file=sys.stderr)
        return 2

    with open_archive(archive_path) as archive:
        try:
            text = read_bundle(archive, args.bundle)
        except Exception as exc:
            print(f"ERROR: cannot read target bundle {args.bundle}: {exc}", file=sys.stderr)
            return 1

    # Collect all explicit safe field/value declarations in this bundle.
    bundle_fields: dict[str, Counter[str]] = defaultdict(Counter)
    field_occurrences: list[tuple[int, str, str]] = []
    for match in FIELD_VALUE_RE.finditer(text):
        field = match.group(1)
        value = safe_token(match.group(3))
        if value is None:
            continue
        bundle_fields[field][value] += 1
        field_occurrences.append((match.start(), field, value))

    # Candidate palette labels come primarily from label/title/name declarations.
    label_candidates: dict[str, dict[str, Any]] = {}
    for pos, field, value in field_occurrences:
        if field not in {"label", "title", "name"} or not is_human_label(value):
            continue
        window = nearest_window(text, pos, max(800, args.radius))
        assoc = association_record(window)
        action_values = {
            item["value"]
            for item in assoc["safe_fields"].get("action", [])
        }
        type_values = {
            item["value"]
            for item in assoc["safe_fields"].get("type", [])
        }
        score = 0
        if value in KNOWN_ANCHORS:
            score += 8
        if action_values:
            score += 5
        if any(key in assoc["runtime_keys"] for key in ("successNode", "failNode", "nodeTimeout", "nodeSleep")):
            score += 4
        if type_values & {"custom", "input", "helper", "custom-context-menu"}:
            score += 3
        if assoc["runtime_keys"]:
            score += min(4, len(assoc["runtime_keys"]))

        rec = label_candidates.setdefault(
            value,
            {
                "label": value,
                "occurrences": 0,
                "fields_seen_as": Counter(),
                "score": 0,
                "safe_fields": defaultdict(Counter),
                "runtime_keys": Counter(),
            },
        )
        rec["occurrences"] += 1
        rec["fields_seen_as"][field] += 1
        rec["score"] = max(rec["score"], score)
        for f, items in assoc["safe_fields"].items():
            for item in items:
                rec["safe_fields"][f][item["value"]] += item["count"]
        rec["runtime_keys"].update(assoc["runtime_keys"])

    # Also anchor directly on the 13 already-proven UI labels even when their
    # source declaration does not use label/title/name.
    anchor_analysis: list[dict[str, Any]] = []
    for anchor in KNOWN_ANCHORS:
        start = 0
        windows = []
        while True:
            idx = text.find(anchor, start)
            if idx < 0:
                break
            windows.append(nearest_window(text, idx, max(800, args.radius)))
            start = idx + len(anchor)
            if len(windows) >= 20:
                break
        merged_fields: dict[str, Counter[str]] = defaultdict(Counter)
        merged_keys = Counter()
        for window in windows:
            assoc = association_record(window)
            for f, items in assoc["safe_fields"].items():
                for item in items:
                    merged_fields[f][item["value"]] += item["count"]
            merged_keys.update(assoc["runtime_keys"])
        anchor_analysis.append(
            {
                "anchor": anchor,
                "occurrences": len(windows),
                "safe_fields": {
                    f: [{"value": v, "count": c} for v, c in counter.most_common(25)]
                    for f, counter in sorted(merged_fields.items())
                },
                "runtime_keys": dict(merged_keys.most_common()),
            }
        )

    serial_candidates = []
    for value, rec in label_candidates.items():
        if rec["score"] < 4:
            continue
        serial_candidates.append(
            {
                "label": value,
                "score": rec["score"],
                "occurrences": rec["occurrences"],
                "fields_seen_as": dict(rec["fields_seen_as"]),
                "safe_fields": {
                    f: [{"value": v, "count": c} for v, c in counter.most_common(30)]
                    for f, counter in sorted(rec["safe_fields"].items())
                },
                "runtime_keys": dict(rec["runtime_keys"].most_common()),
            }
        )
    serial_candidates.sort(key=lambda item: (-item["score"], item["label"].lower()))

    # Global semantic token inventory is useful for identifying internal action
    # names even before all labels can be paired confidently.
    global_fields = {
        field: [
            {"value": value, "count": count}
            for value, count in counter.most_common(250)
        ]
        for field, counter in sorted(bundle_fields.items())
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-node-registry-probe-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "node-registry.shareable.json"

    result = {
        "catalog_format": 1,
        "privacy": "shareable GenFarmer node-registry metadata; no raw proprietary source snippets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "genfarmer_package": "resources/app.asar",
        "bundle": args.bundle,
        "bundle_chars": len(text),
        "known_anchors": list(KNOWN_ANCHORS),
        "known_anchors_found": [a for a in KNOWN_ANCHORS if a in text],
        "candidate_node_labels": serial_candidates,
        "anchor_analysis": anchor_analysis,
        "global_safe_field_values": global_fields,
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER AUTOMATION NODE REGISTRY PROBE")
    print("=" * 78)
    print(f"Bundle: {args.bundle}")
    print(f"Bundle characters: {len(text)}")
    print(f"Known anchors found: {len(result['known_anchors_found'])}/{len(KNOWN_ANCHORS)}")
    print(f"Likely node-label candidates: {len(serial_candidates)}")
    print("Top candidates:")
    for item in serial_candidates[:80]:
        actions = [x['value'] for x in item['safe_fields'].get('action', [])[:4]]
        types = [x['value'] for x in item['safe_fields'].get('type', [])[:4]]
        print(f" - {item['label']}: score={item['score']} action={actions or '-'} type={types or '-'}")
    print(f"Shareable result: {out_path.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
