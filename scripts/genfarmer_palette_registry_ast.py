#!/usr/bin/env python3
"""Extract GenFarmer Automation palette registry rows from renderer JavaScript AST.

The previous AST probe showed that many ``action*`` tokens occur as ``icon``
values or unrelated property identifiers.  This probe targets the stronger
structure visible in the Automation editor: object literals containing direct
``label`` + ``action`` + ``icon`` properties.

For each such object it emits only privacy-safe structural values:
- visible label;
- action value kind/value (identifier or string literal);
- icon value kind/value;
- other direct property names;
- optional resolution of uppercase action constants when a simple local string
  binding can be proven.

It never emits raw bundled source snippets and never modifies GenFarmer.
"""
from __future__ import annotations

from collections import defaultdict
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
ACTION_TOKEN_RE = re.compile(r"^action[A-Z][A-Za-z0-9_]{1,80}$")
UPPER_ACTION_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,80}$")
IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]{0,100}$")
DOTTED_IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$.]{0,120}$")

KNOWN_LABELS = {
    "Press Back", "Press Home", "Press Menu", "Change device", "Start App", "Stop App",
    "Install App", "Uninstall App", "Is installed App", "Clear App Data", "Transfer File",
    "Device actions", "Toggle service", "Check activity", "Press key", "Type text",
    "Update field", "Get property", "Element exists", "Multi Element exists",
    "Get attribute", "Write file", "Save assets", "Set variable", "Insert data",
    "Open AI", "Case Path", "ADB shell command", "Sleep", "Screenshot", "DeepSeek",
    "Variables", "Context Menu", "Backup/Restore v2", "Check network", "Image search",
}


def default_asar() -> Path:
    local = os.getenv("LOCALAPPDATA")
    return Path(local or ".") / "Programs" / "GenFarmer" / "resources" / "app.asar"


def get_parser() -> Parser:
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
    raw = text(src, node).strip()
    if node.type not in {"string", "template_string"} or len(raw) < 2:
        return None
    if raw[0] not in {'"', "'", '`'} or raw[-1] != raw[0] or "${" in raw:
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
        val = text(src, node)
        return val if IDENT_RE.fullmatch(val) else None
    val = js_string(src, node)
    return val if val and IDENT_RE.fullmatch(val) else None


def scalar(src: bytes, node: Any) -> dict[str, str] | None:
    if node.type in {"string", "template_string"}:
        val = js_string(src, node)
        return {"kind": "string", "value": val} if val else None
    raw = text(src, node)
    if node.type in {"identifier", "property_identifier"} and IDENT_RE.fullmatch(raw):
        return {"kind": "identifier", "value": raw}
    if node.type in {"member_expression", "subscript_expression"} and DOTTED_IDENT_RE.fullmatch(raw):
        return {"kind": "expression", "value": raw}
    if node.type in {"true", "false", "null", "number"} and len(raw) <= 40:
        return {"kind": node.type, "value": raw}
    return None


def direct_pairs(src: bytes, obj: Any) -> dict[str, tuple[Any, dict[str, str] | None]]:
    out: dict[str, tuple[Any, dict[str, str] | None]] = {}
    for child in getattr(obj, "named_children", []):
        if child.type != "pair":
            continue
        key = child.child_by_field_name("key")
        val = child.child_by_field_name("value")
        if key is None or val is None:
            continue
        name = key_name(src, key)
        if name:
            out[name] = (val, scalar(src, val))
    return out


def human_label(value: str | None) -> bool:
    if not value:
        return False
    if value in KNOWN_LABELS:
        return True
    if not 2 <= len(value) <= 70 or " " not in value:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _/+&()\-]*", value))


def parent_container_hint(src: bytes, obj: Any) -> dict[str, str] | None:
    cur = obj
    for _ in range(4):
        p = getattr(cur, "parent", None)
        if p is None:
            return None
        if p.type == "pair":
            key = p.child_by_field_name("key")
            if key is not None:
                name = key_name(src, key)
                if name:
                    return {"kind": "pair-key", "value": name}
        cur = p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="AST extractor for GenFarmer palette label/action/icon registry rows")
    ap.add_argument("--asar", type=Path, default=default_asar())
    ap.add_argument("--assets-prefix", default="dist/render/assets/")
    ap.add_argument("--max-file-mb", type=int, default=8)
    args = ap.parse_args()

    asar_path = args.asar.expanduser().resolve()
    if not asar_path.exists():
        print(f"ERROR: app.asar not found: {asar_path}", file=sys.stderr)
        return 2

    parser = get_parser()
    max_bytes = max(1, args.max_file_mb) * 1024 * 1024
    bindings: dict[str, set[str]] = defaultdict(set)
    rows: list[dict[str, Any]] = []
    parsed = 0

    try:
        ctx = AsarArchive(asar_path, mode="r")
    except TypeError:
        ctx = AsarArchive.open(str(asar_path))

    with ctx as archive:
        entries = [str(x).replace("\\", "/") for x in archive.list()]
        sources: list[tuple[str, bytes, Any]] = []
        for path in entries:
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
            if b"label" not in src or b"action" not in src:
                continue
            tree = parser.parse(src)
            parsed += 1
            sources.append((path, src, tree.root_node))

        # Pass 1: simple identifier -> string bindings, useful for resolving
        # constants when the minified bundle defines them locally.
        for _, src, root in sources:
            for node in walk(root):
                if node.type == "variable_declarator":
                    name = node.child_by_field_name("name")
                    value = node.child_by_field_name("value")
                    if name is None or value is None or name.type != "identifier":
                        continue
                    ident = text(src, name)
                    sval = js_string(src, value)
                    if UPPER_ACTION_RE.fullmatch(ident) and sval:
                        bindings[ident].add(sval)
                elif node.type == "assignment_expression":
                    left = node.child_by_field_name("left")
                    right = node.child_by_field_name("right")
                    if left is None or right is None or left.type != "identifier":
                        continue
                    ident = text(src, left)
                    sval = js_string(src, right)
                    if UPPER_ACTION_RE.fullmatch(ident) and sval:
                        bindings[ident].add(sval)

        # Pass 2: exact object rows with direct label/action/icon properties.
        for path, src, root in sources:
            for node in walk(root):
                if node.type != "object":
                    continue
                pairs = direct_pairs(src, node)
                if not {"label", "action", "icon"}.issubset(pairs):
                    continue
                label = pairs["label"][1]
                action = pairs["action"][1]
                icon = pairs["icon"][1]
                if not label or not human_label(label.get("value")):
                    continue
                if not action or not icon:
                    continue
                record: dict[str, Any] = {
                    "file": path,
                    "label": label,
                    "action": action,
                    "icon": icon,
                    "direct_property_keys": sorted(pairs.keys()),
                }
                hint = parent_container_hint(src, node)
                if hint:
                    record["container_hint"] = hint
                if action.get("kind") == "identifier":
                    vals = sorted(bindings.get(action["value"], set()))
                    if len(vals) == 1:
                        record["resolved_action_literal"] = vals[0]
                if icon.get("kind") == "string" and ACTION_TOKEN_RE.fullmatch(icon.get("value", "")):
                    record["action_token_role"] = "icon-value"
                rows.append(record)

    # Deduplicate equivalent rows while preserving source evidence files.
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["label"]["value"], row["action"]["value"], row["icon"]["value"])
        if key not in grouped:
            grouped[key] = dict(row)
            grouped[key]["files"] = [row["file"]]
            grouped[key].pop("file", None)
        elif row["file"] not in grouped[key]["files"]:
            grouped[key]["files"].append(row["file"])

    catalog = sorted(grouped.values(), key=lambda r: (r["label"]["value"].lower(), r["action"]["value"]))
    action_token_icons = sum(1 for r in catalog if r.get("action_token_role") == "icon-value")

    result = {
        "catalog_format": 1,
        "privacy": "shareable AST palette registry rows only; no raw GenFarmer source snippets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "renderer_assets_parsed": parsed,
        "palette_rows": catalog,
        "palette_row_count": len(catalog),
        "rows_with_action_token_as_icon_value": action_token_icons,
        "simple_uppercase_bindings": {
            k: sorted(v) for k, v in sorted(bindings.items()) if len(v) == 1
        },
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-palette-registry-ast-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "palette-registry-ast.shareable.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER AST PALETTE REGISTRY EXTRACTOR")
    print("=" * 78)
    print(f"Renderer assets parsed: {parsed}")
    print(f"Palette registry rows: {len(catalog)}")
    print(f"Rows proving action* token is icon value: {action_token_icons}")
    print("Palette rows:")
    for row in catalog:
        resolved = f" resolved={row['resolved_action_literal']}" if row.get("resolved_action_literal") else ""
        role = " icon-token" if row.get("action_token_role") else ""
        print(f" - {row['label']['value']}: action={row['action']['value']} icon={row['icon']['value']}{resolved}{role}")
    print(f"Shareable result: {out.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
