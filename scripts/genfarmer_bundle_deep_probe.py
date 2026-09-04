#!/usr/bin/env python3
"""Read-only deep probe of GenFarmer's Automation editor bundle.

Targets the bundled `useScriptEditor-*.js` module that was empirically shown to
contain every known Automation palette label.  Instead of dumping proprietary
source, this script reconstructs privacy-safe structural associations around
known labels: enclosing object/array boundaries, property names, safe literal
values, identifier-valued fields, likely registry symbols, and source-map hints.

No GenFarmer files are modified and no workflow/API mutation is performed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

try:
    from asar import AsarArchive
except ImportError:
    print('ERROR: missing package "asar"; run: python -m pip install -e ".[dev]"', file=sys.stderr)
    raise SystemExit(2)

KNOWN = (
    "Press Back", "Press Home", "Press Menu", "Change device", "Start App",
    "Stop App", "Install App", "Variables", "Context Menu", "ADB shell command",
    "Sleep", "Screenshot", "DeepSeek",
)
SAFE_FIELDS = {
    "label", "title", "name", "action", "type", "nodeType", "category", "group",
    "component", "key", "kind", "field", "mode", "variant", "control", "inputType",
}
RUNTIME_KEYS = {
    "successNode", "failNode", "nodeLog", "nodeSleep", "nodeTimeout",
    "timeoutAdbReconnect", "timeoutNextNode", "timeoutType", "timeoutFrom",
    "timeoutTo", "outputVariable", "casePaths", "breakpoint", "disabled",
    "sourceHandle", "targetHandle", "options", "action",
}
GENERIC_UI = {
    "Fields", "Field", "Start", "Alert", "Basic Field", "CheckBox", "CheckBox Group",
    "Divider", "File", "Grid", "Group", "HTML", "Inline", "Input", "Input Number",
    "Layout", "Link", "Radio", "Select", "Slider", "Switch", "Text", "TextArea",
    "Title", "BaseEdge", "value", "label", "name", "type", "group", "input",
}
STRING_RE = re.compile(r'(["\'])(?P<v>(?:\\.|(?!\1).){1,160})\1')
PAIR_RE = re.compile(
    r'(?:(?:["\'])?(?P<k>[A-Za-z_$][A-Za-z0-9_$]{0,64})(?:["\'])?)\s*:\s*'
    r'(?P<q>["\'])(?P<v>(?:\\.|(?!\2).){1,160})\2'
)
IDENT_PAIR_RE = re.compile(
    r'(?:(?:["\'])?(?P<k>[A-Za-z_$][A-Za-z0-9_$]{0,64})(?:["\'])?)\s*:\s*'
    r'(?P<v>[A-Za-z_$][A-Za-z0-9_$]{0,80})(?=\s*[,}])'
)
KEY_RE = re.compile(r'(?:^|[,{])\s*(?:["\'])?([A-Za-z_$][A-Za-z0-9_$]{0,64})(?:["\'])?\s*:')
SYMBOL_RE = re.compile(r'(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]{0,80})\s*=\s*$')
SOURCE_MAP_RE = re.compile(r'[#@]\s*sourceMappingURL=([^\s]+)')


def default_asar() -> Path:
    local = os.getenv("LOCALAPPDATA")
    return Path(local or ".") / "Programs" / "GenFarmer" / "resources" / "app.asar"


def decode(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    return bytes(raw).decode("utf-8", errors="ignore")


def safe_literal(value: str) -> str | None:
    value = value.strip()
    if not value or len(value) > 120:
        return None
    if any(x in value for x in ("\n", "\r", "@", "http://", "https://", "{", "}")):
        return None
    # Require ordinary UI/token characters.  This keeps the report structural.
    if not re.fullmatch(r"[A-Za-z0-9 _./:+()\-]+", value):
        return None
    return value


def match_forward(text: str, start: int, opener: str, closer: str, limit: int = 60000) -> int | None:
    depth = 0
    quote: str | None = None
    esc = False
    i = start
    end = min(len(text), start + limit)
    while i < end:
        ch = text[i]
        if quote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in ('"', "'", '`'):
            quote = ch
            i += 1
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def enclosing(text: str, pos: int, opener: str, closer: str, back: int = 12000) -> tuple[int, int] | None:
    lo = max(0, pos - back)
    candidates = [m.start() for m in re.finditer(re.escape(opener), text[lo:pos])]
    for rel in reversed(candidates):
        start = lo + rel
        end = match_forward(text, start, opener, closer)
        if end is not None and start <= pos <= end:
            return start, end + 1
    return None


def object_summary(text: str, span: tuple[int, int] | None) -> dict[str, Any] | None:
    if not span:
        return None
    start, end = span
    chunk = text[start:end]
    if len(chunk) > 50000:
        return {"length": len(chunk), "too_large": True}
    keys = Counter(KEY_RE.findall(chunk))
    strings: dict[str, Counter[str]] = defaultdict(Counter)
    for m in PAIR_RE.finditer(chunk):
        key, val = m.group("k"), safe_literal(m.group("v"))
        if key in SAFE_FIELDS and val:
            strings[key][val] += 1
    identifiers: dict[str, Counter[str]] = defaultdict(Counter)
    for m in IDENT_PAIR_RE.finditer(chunk):
        key, val = m.group("k"), m.group("v")
        if key in SAFE_FIELDS and val not in {"true", "false", "null", "undefined"}:
            identifiers[key][val] += 1
    before = text[max(0, start - 140):start]
    symbol = None
    sm = SYMBOL_RE.search(before)
    if sm:
        symbol = sm.group(1)
    all_literals = Counter()
    for m in STRING_RE.finditer(chunk):
        val = safe_literal(m.group("v"))
        if val:
            all_literals[val] += 1
    likely_labels = [
        {"value": v, "count": c}
        for v, c in all_literals.most_common(120)
        if v not in GENERIC_UI and 2 <= len(v) <= 60 and (" " in v or v in KNOWN)
    ][:50]
    return {
        "length": len(chunk),
        "registry_symbol": symbol,
        "property_keys": [{"key": k, "count": c} for k, c in keys.most_common(80)],
        "safe_string_fields": {
            k: [{"value": v, "count": c} for v, c in ctr.most_common(30)]
            for k, ctr in sorted(strings.items())
        },
        "identifier_fields": {
            k: [{"value": v, "count": c} for v, c in ctr.most_common(30)]
            for k, ctr in sorted(identifiers.items())
        },
        "likely_label_literals": likely_labels,
        "runtime_keys_present": sorted(k for k in RUNTIME_KEYS if re.search(rf'\b{re.escape(k)}\b', chunk)),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Deep structural probe of GenFarmer useScriptEditor bundle")
    p.add_argument("--asar", type=Path, default=default_asar())
    p.add_argument("--bundle", default="dist/render/assets/useScriptEditor-HioTuYH4.js")
    args = p.parse_args()
    asar_path = args.asar.expanduser().resolve()
    if not asar_path.exists():
        print(f"ERROR: app.asar not found: {asar_path}", file=sys.stderr)
        return 2

    try:
        ctx = AsarArchive(asar_path, mode="r")
    except TypeError:
        ctx = AsarArchive.open(str(asar_path))

    with ctx as archive:
        try:
            entries = [str(x).replace("\\", "/") for x in archive.list()]
            raw = archive.read(Path(args.bundle), follow_link=True)
        except TypeError:
            raw = archive.read(Path(args.bundle))
        except Exception as exc:
            print(f"ERROR reading bundle {args.bundle}: {exc}", file=sys.stderr)
            return 1
        text = decode(raw)

        map_hints = SOURCE_MAP_RE.findall(text[-2000:])
        map_entries = [e for e in entries if "useScriptEditor" in e and e.endswith(".map")]
        source_map = {"source_mapping_url_hints": map_hints, "matching_map_entries": map_entries[:20]}
        if map_entries:
            try:
                mraw = archive.read(Path(map_entries[0]), follow_link=True)
            except TypeError:
                mraw = archive.read(Path(map_entries[0]))
            try:
                mp = json.loads(decode(mraw))
                source_map["sources"] = [str(x) for x in mp.get("sources", [])[:200]]
                source_map["names_count"] = len(mp.get("names", [])) if isinstance(mp.get("names"), list) else 0
                source_map["sources_content_present"] = bool(mp.get("sourcesContent"))
            except Exception:
                source_map["map_parse_error"] = True

    anchors = []
    aggregate_labels = Counter()
    object_key_sets = Counter()
    for anchor in KNOWN:
        positions = [m.start() for m in re.finditer(re.escape(anchor), text, flags=re.IGNORECASE)]
        records = []
        for pos in positions[:10]:
            obj = object_summary(text, enclosing(text, pos, "{", "}"))
            arr = object_summary(text, enclosing(text, pos, "[", "]"))
            if obj:
                for item in obj.get("likely_label_literals", []):
                    aggregate_labels[item["value"]] += item["count"]
                key_tuple = tuple(x["key"] for x in obj.get("property_keys", [])[:20])
                if key_tuple:
                    object_key_sets[key_tuple] += 1
            records.append({"object": obj, "array": arr})
        anchors.append({"anchor": anchor, "occurrences": len(positions), "structures": records})

    result = {
        "catalog_format": 1,
        "privacy": "shareable structural deep-probe; no raw GenFarmer source snippets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "bundle": args.bundle,
        "bundle_characters": len(text),
        "source_map": source_map,
        "anchors": anchors,
        "aggregate_likely_labels": [
            {"label": v, "score": c} for v, c in aggregate_labels.most_common(150)
            if v not in GENERIC_UI
        ],
        "common_enclosing_object_key_sets": [
            {"keys": list(keys), "count": count}
            for keys, count in object_key_sets.most_common(30)
        ],
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-bundle-deep-probe-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "bundle-deep-probe.shareable.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER AUTOMATION EDITOR DEEP BUNDLE PROBE")
    print("=" * 78)
    print(f"Bundle: {args.bundle}")
    print(f"Bundle characters: {len(text)}")
    print(f"Known anchors present: {sum(1 for a in anchors if a['occurrences'])}/{len(KNOWN)}")
    print(f"Source-map entries: {len(source_map.get('matching_map_entries', []))}")
    print("Top additional label candidates:")
    for item in result["aggregate_likely_labels"][:40]:
        print(f" - {item['label']}: score={item['score']}")
    print(f"Shareable result: {out.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified.")
    print("=" * 78)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
