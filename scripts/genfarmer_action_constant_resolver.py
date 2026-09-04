#!/usr/bin/env python3
"""Resolve GenFarmer palette action constants such as ``H.PAUSE`` to literals.

The AST palette extractor proved that Automation palette rows use expressions
such as ``H.PRESS_BACK`` and ``H.SCREENSHOT`` for their action field.  This
read-only probe scans renderer JavaScript ASTs for the backing constant/enum
mappings without dumping raw proprietary source.

It dynamically discovers the constants used by direct ``label + action + icon``
palette rows, then searches all renderer assets for:

* object-literal properties whose key matches a palette constant and whose value
  is a string literal;
* direct member assignments such as ``X.PAUSE = \"Pause\"``;
* subscript assignments such as ``X[\"PAUSE\"] = \"Pause\"``.

Evidence is aggregated by constant name.  Known live script.flow actions are
used only as validation anchors; no unresolved value is guessed.
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
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]

try:
    from asar import AsarArchive
except ImportError:
    print('ERROR: missing package "asar"; run: python -m pip install -e ".[dev]"', file=sys.stderr)
    raise SystemExit(2)

try:
    from tree_sitter import Language, Parser
    import tree_sitter_javascript as tsjs
except ImportError:
    print('ERROR: missing tree-sitter dependencies; run: python -m pip install -e ".[dev]"', file=sys.stderr)
    raise SystemExit(2)

TEXT_SUFFIXES = {".js", ".mjs", ".cjs"}
IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]{0,100}$")
MEMBER_RE = re.compile(r"^(?P<ns>[A-Za-z_$][A-Za-z0-9_$]*)\.(?P<key>[A-Za-z_$][A-Za-z0-9_$]*)$")

LIVE_VALIDATION = {
    "ADB": "Adb",
    "DEEPSEEK": "DeepSeek",
    "PAUSE": "Pause",
    "SCREENSHOT": "Screenshot",
}


def default_asar() -> Path:
    local = os.getenv("LOCALAPPDATA")
    return Path(local or ".") / "Programs" / "GenFarmer" / "resources" / "app.asar"


def parser_instance() -> Parser:
    language = Language(tsjs.language())
    try:
        return Parser(language)
    except TypeError:
        parser = Parser()
        parser.language = language
        return parser


def walk(node: Any) -> Iterable[Any]:
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        try:
            stack.extend(reversed(cur.children))
        except Exception:
            pass


def text(src: bytes, node: Any) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def js_string(src: bytes, node: Any) -> str | None:
    if node.type not in {"string", "template_string"}:
        return None
    raw = text(src, node).strip()
    if len(raw) < 2 or raw[0] not in {'"', "'", '`'} or raw[-1] != raw[0] or "${" in raw:
        return None
    value = raw[1:-1]
    value = value.replace("\\'", "'").replace('\\"', '"').replace("\\`", "`")
    value = value.replace("\\n", " ").replace("\\r", " ").strip()
    if not value or len(value) > 120:
        return None
    if any(x in value for x in ("http://", "https://", "@", "data:")):
        return None
    return value


def key_name(src: bytes, node: Any) -> str | None:
    if node.type in {"identifier", "property_identifier"}:
        value = text(src, node)
        return value if IDENT_RE.fullmatch(value) else None
    value = js_string(src, node)
    return value if value and IDENT_RE.fullmatch(value) else None


def direct_object_pairs(src: bytes, obj: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for child in getattr(obj, "named_children", []):
        if child.type != "pair":
            continue
        key = child.child_by_field_name("key")
        value = child.child_by_field_name("value")
        if key is None or value is None:
            continue
        name = key_name(src, key)
        if name:
            out[name] = value
    return out


def scalar_action_expr(src: bytes, node: Any) -> tuple[str, str] | None:
    raw = text(src, node)
    m = MEMBER_RE.fullmatch(raw)
    if m:
        return m.group("ns"), m.group("key")
    return None


def discover_palette_constants(sources: list[tuple[str, bytes, Any]]) -> tuple[list[dict[str, str]], set[str]]:
    rows: list[dict[str, str]] = []
    constants: set[str] = set()
    seen: set[tuple[str, str]] = set()
    for path, src, root in sources:
        for node in walk(root):
            if node.type != "object":
                continue
            pairs = direct_object_pairs(src, node)
            if not {"label", "action", "icon"}.issubset(pairs):
                continue
            label = js_string(src, pairs["label"])
            action = scalar_action_expr(src, pairs["action"])
            if not label or not action:
                continue
            ns, key = action
            item_key = (label, f"{ns}.{key}")
            if item_key in seen:
                continue
            seen.add(item_key)
            constants.add(key)
            rows.append({"label": label, "namespace": ns, "constant": key, "expression": f"{ns}.{key}", "file": path})
    rows.sort(key=lambda r: r["label"].lower())
    return rows, constants


def assignment_member(src: bytes, node: Any) -> tuple[str | None, str | None]:
    """Return (owner, key) for simple member/subscript assignment LHS."""
    if node.type == "member_expression":
        obj = node.child_by_field_name("object")
        prop = node.child_by_field_name("property")
        if obj is not None and prop is not None:
            owner = text(src, obj)
            key = text(src, prop)
            if IDENT_RE.fullmatch(owner) and IDENT_RE.fullmatch(key):
                return owner, key
    if node.type == "subscript_expression":
        obj = node.child_by_field_name("object")
        index = node.child_by_field_name("index")
        if obj is not None and index is not None:
            owner = text(src, obj)
            key = js_string(src, index)
            if IDENT_RE.fullmatch(owner) and key and IDENT_RE.fullmatch(key):
                return owner, key
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve GenFarmer H.* palette action constants to string literals")
    ap.add_argument("--asar", type=Path, default=default_asar())
    ap.add_argument("--assets-prefix", default="dist/render/assets/")
    ap.add_argument("--max-file-mb", type=int, default=8)
    args = ap.parse_args()

    asar_path = args.asar.expanduser().resolve()
    if not asar_path.exists():
        print(f"ERROR: app.asar not found: {asar_path}", file=sys.stderr)
        return 2

    parser = parser_instance()
    max_bytes = max(1, args.max_file_mb) * 1024 * 1024

    try:
        ctx = AsarArchive(asar_path, mode="r")
    except TypeError:
        ctx = AsarArchive.open(str(asar_path))

    sources: list[tuple[str, bytes, Any]] = []
    with ctx as archive:
        for raw_path in archive.list():
            path = str(raw_path).replace("\\", "/")
            pp = Path(path)
            if not path.startswith(args.assets_prefix) or pp.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                try:
                    raw = archive.read(pp, follow_link=True)
                except TypeError:
                    raw = archive.read(pp)
            except Exception:
                continue
            src = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
            if len(src) > max_bytes:
                continue
            tree = parser.parse(src)
            sources.append((path, src, tree.root_node))

    palette_rows, constants = discover_palette_constants(sources)

    evidence: dict[str, list[dict[str, str]]] = defaultdict(list)
    object_groups: list[dict[str, Any]] = []

    for path, src, root in sources:
        for node in walk(root):
            if node.type == "object":
                pairs = direct_object_pairs(src, node)
                matched: list[tuple[str, str]] = []
                for key, value_node in pairs.items():
                    if key not in constants:
                        continue
                    literal = js_string(src, value_node)
                    if literal is None:
                        continue
                    evidence[key].append({"kind": "object-property", "literal": literal, "file": path})
                    matched.append((key, literal))
                if len(matched) >= 3:
                    object_groups.append({
                        "file": path,
                        "matched_constant_count": len(matched),
                        "mappings": [{"constant": k, "literal": v} for k, v in sorted(matched)],
                    })
            elif node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left is None or right is None:
                    continue
                owner, key = assignment_member(src, left)
                if not key or key not in constants:
                    continue
                literal = js_string(src, right)
                if literal is None:
                    continue
                evidence[key].append({
                    "kind": "member-assignment",
                    "literal": literal,
                    "file": path,
                    "owner": owner or "",
                })

    resolved: dict[str, dict[str, Any]] = {}
    for key in sorted(constants):
        items = evidence.get(key, [])
        counts = Counter(item["literal"] for item in items)
        literals = [{"literal": literal, "count": count} for literal, count in counts.most_common()]
        unique = literals[0]["literal"] if len(literals) == 1 else None
        validation = None
        if key in LIVE_VALIDATION:
            expected = LIVE_VALIDATION[key]
            if unique is None:
                validation = {"expected_live_literal": expected, "status": "unresolved"}
            else:
                validation = {
                    "expected_live_literal": expected,
                    "status": "match" if unique == expected else "mismatch",
                }
        resolved[key] = {
            "evidence_count": len(items),
            "candidate_literals": literals,
            "resolved_literal": unique,
            "validation": validation,
            "evidence_files": sorted({item["file"] for item in items}),
        }

    enriched_rows = []
    for row in palette_rows:
        info = resolved.get(row["constant"], {})
        enriched = dict(row)
        enriched["resolved_literal"] = info.get("resolved_literal")
        enriched["candidate_literals"] = info.get("candidate_literals", [])
        enriched_rows.append(enriched)

    object_groups.sort(key=lambda x: (-x["matched_constant_count"], x["file"]))
    resolved_count = sum(1 for v in resolved.values() if v.get("resolved_literal"))
    live_checks = [v["validation"] for v in resolved.values() if v.get("validation")]
    live_matches = sum(1 for v in live_checks if v and v.get("status") == "match")

    result = {
        "catalog_format": 1,
        "privacy": "shareable constant/literal mapping evidence only; no raw GenFarmer source snippets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "renderer_assets_parsed": len(sources),
        "palette_row_count": len(palette_rows),
        "palette_constants_discovered": len(constants),
        "resolved_constant_count": resolved_count,
        "live_validation_checks": len(live_checks),
        "live_validation_matches": live_matches,
        "palette_rows": enriched_rows,
        "constant_resolution": resolved,
        "strong_object_groups": object_groups[:20],
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-action-constant-resolver-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "action-constants.shareable.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER PALETTE ACTION CONSTANT RESOLVER")
    print("=" * 78)
    print(f"Renderer assets parsed: {len(sources)}")
    print(f"Palette rows discovered: {len(palette_rows)}")
    print(f"Palette constants discovered: {len(constants)}")
    print(f"Constants uniquely resolved: {resolved_count}/{len(constants)}")
    print(f"Live-known validation matches: {live_matches}/{len(live_checks)}")
    print("Resolved palette rows:")
    for row in enriched_rows:
        literal = row.get("resolved_literal") or "?"
        print(f" - {row['label']}: {row['expression']} -> {literal}")
    if object_groups:
        print("Strong constant-map object candidates:")
        for group in object_groups[:8]:
            print(f" - {group['file']}: {group['matched_constant_count']} matching constants")
    print(f"Shareable result: {out.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
