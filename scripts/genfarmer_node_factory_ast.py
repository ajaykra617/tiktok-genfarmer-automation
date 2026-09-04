#!/usr/bin/env python3
"""Read-only AST probe for GenFarmer node-construction/default-schema contexts.

Palette discovery now gives us 60 exact renderer rows of ``label + action + icon``
and 56 exact serialized action literals.  The next question is where GenFarmer
constructs the node ``data`` object and its default ``options``.

This probe uses the *palette action constants* (for example ``H.TYPE_TEXT`` and
``H.PAUSE``) as anchors and searches renderer JavaScript syntax trees for:

* non-palette object literals with ``action: H.<CONSTANT>``;
* switch/case branches keyed by a palette action constant;
* computed/object maps keyed by a palette action constant.

For object candidates it emits only field names/type shapes and nested key paths,
never raw source snippets or arbitrary literal values.  It scores candidates for
node-construction evidence such as ``options``, ``successNode``/``failNode`` and
known runtime fields.  Live-observed Adb/Pause/Screenshot option shapes are used
only as validation anchors.

No GenFarmer files are modified and no API/workflow mutation is performed.
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

RUNTIME_KEYS = {
    "action", "options", "successNode", "failNode", "nodeLog", "nodeSleep",
    "nodeTimeout", "timeoutAdbReconnect", "timeoutNextNode", "breakpoint",
    "disabled", "outputVariable", "casePaths", "timeout", "timeoutFrom",
    "timeoutTo", "timeoutType", "command",
}

EXPECTED_LIVE_PATHS = {
    "ADB": {
        "action", "options", "options.breakpoint", "options.command",
        "options.disabled", "options.nodeLog", "options.nodeSleep",
        "options.nodeTimeout", "options.outputVariable",
        "options.timeoutAdbReconnect", "options.timeoutNextNode",
    },
    "PAUSE": {
        "action", "options", "options.breakpoint", "options.disabled",
        "options.nodeLog", "options.nodeSleep", "options.nodeTimeout",
        "options.timeoutAdbReconnect", "options.timeoutNextNode",
        "options.timeout", "options.timeoutFrom", "options.timeoutTo",
        "options.timeoutType",
    },
    "SCREENSHOT": {
        "action", "options", "options.breakpoint", "options.disabled",
        "options.nodeLog", "options.nodeSleep", "options.nodeTimeout",
        "options.timeoutAdbReconnect", "options.timeoutNextNode",
    },
}


def default_asar() -> Path:
    local = os.getenv("LOCALAPPDATA")
    return Path(local or ".") / "Programs" / "GenFarmer" / "resources" / "app.asar"


def get_parser() -> Parser:
    language = Language(tsjs.language())
    try:
        return Parser(language)
    except TypeError:
        p = Parser()
        p.language = language
        return p


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
    return value


def key_name(src: bytes, node: Any) -> str | None:
    if node.type in {"identifier", "property_identifier"}:
        val = text(src, node)
        return val if IDENT_RE.fullmatch(val) else None
    val = js_string(src, node)
    return val if val and IDENT_RE.fullmatch(val) else None


def member_constant(src: bytes, node: Any) -> tuple[str, str] | None:
    raw = text(src, node)
    m = MEMBER_RE.fullmatch(raw)
    if not m:
        return None
    return m.group("ns"), m.group("key")


def direct_pairs(src: bytes, obj: Any) -> dict[str, Any]:
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


def scalar_type(node: Any) -> str:
    t = node.type
    if t in {"string", "template_string"}:
        return "string"
    if t in {"number"}:
        return "number"
    if t in {"true", "false"}:
        return "boolean"
    if t == "null":
        return "null"
    if t in {"object", "array"}:
        return t
    if t in {"identifier", "member_expression", "call_expression", "arrow_function", "function_expression"}:
        return t
    return t


def nested_shape(src: bytes, obj: Any, prefix: str = "", depth: int = 0, max_depth: int = 3) -> tuple[list[str], dict[str, str]]:
    paths: list[str] = []
    types: dict[str, str] = {}
    if depth > max_depth:
        return paths, types
    for name, value in direct_pairs(src, obj).items():
        path = f"{prefix}.{name}" if prefix else name
        paths.append(path)
        types[path] = scalar_type(value)
        if value.type == "object" and depth < max_depth:
            child_paths, child_types = nested_shape(src, value, path, depth + 1, max_depth)
            paths.extend(child_paths)
            types.update(child_types)
    return paths, types


def parent_pair_key(src: bytes, node: Any) -> str | None:
    p = getattr(node, "parent", None)
    if p is not None and p.type == "pair":
        key = p.child_by_field_name("key")
        if key is not None:
            return key_name(src, key)
    return None


def classify_object(paths: set[str], parent_key: str | None) -> tuple[str, int, list[str]]:
    score = 0
    reasons: list[str] = []
    if "action" in paths:
        score += 15
        reasons.append("direct-action")
    if "options" in paths:
        score += 12
        reasons.append("options-object")
    if "successNode" in paths:
        score += 6
        reasons.append("success-pointer")
    if "failNode" in paths:
        score += 6
        reasons.append("fail-pointer")
    runtime_hits = sorted(k for k in RUNTIME_KEYS if k in paths or f"options.{k}" in paths)
    score += min(15, len(runtime_hits) * 2)
    if runtime_hits:
        reasons.append(f"runtime-keys:{len(runtime_hits)}")
    if parent_key == "data":
        score += 10
        reasons.append("parent-key:data")
    elif parent_key == "options":
        score += 7
        reasons.append("parent-key:options")
    if any(p.startswith("options.") for p in paths):
        score += 5
        reasons.append("nested-options")
    if "label" in paths and "icon" in paths:
        score -= 40
        reasons.append("palette-row-penalty")

    if score >= 35:
        role = "strong-node-default-candidate"
    elif score >= 20:
        role = "node-default-candidate"
    elif score >= 10:
        role = "weak-action-object"
    else:
        role = "low-signal"
    return role, score, reasons


def discover_palette_rows(sources: list[tuple[str, bytes, Any]]) -> tuple[list[dict[str, str]], set[tuple[str, str]], dict[tuple[str, str], str]]:
    rows: list[dict[str, str]] = []
    constants: set[tuple[str, str]] = set()
    labels: dict[tuple[str, str], str] = {}
    seen: set[tuple[str, str]] = set()
    for path, src, root in sources:
        for node in walk(root):
            if node.type != "object":
                continue
            pairs = direct_pairs(src, node)
            if not {"label", "action", "icon"}.issubset(pairs):
                continue
            label = js_string(src, pairs["label"])
            action = member_constant(src, pairs["action"])
            if not label or not action:
                continue
            expr = f"{action[0]}.{action[1]}"
            key = (label, expr)
            if key in seen:
                continue
            seen.add(key)
            constants.add(action)
            labels[action] = label
            rows.append({"label": label, "namespace": action[0], "constant": action[1], "expression": expr, "file": path})
    rows.sort(key=lambda r: r["label"].lower())
    return rows, constants, labels


def switch_case_constant(src: bytes, node: Any) -> tuple[str, str] | None:
    if node.type != "switch_case":
        return None
    value = node.child_by_field_name("value")
    if value is None:
        named = getattr(node, "named_children", [])
        if named:
            value = named[0]
    return member_constant(src, value) if value is not None else None


def summarize_switch_case(src: bytes, node: Any) -> dict[str, Any]:
    keys = Counter()
    calls = Counter()
    for n in walk(node):
        if n.type == "pair":
            key = n.child_by_field_name("key")
            if key is not None:
                name = key_name(src, key)
                if name:
                    keys[name] += 1
        elif n.type == "call_expression":
            fn = n.child_by_field_name("function")
            if fn is not None:
                raw = text(src, fn)
                if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$.]{0,80}", raw):
                    calls[raw] += 1
    return {
        "property_keys": [k for k, _ in keys.most_common(50)],
        "call_callees": [k for k, _ in calls.most_common(30)],
        "bytes": node.end_byte - node.start_byte,
    }


def live_overlap(constant: str, paths: set[str]) -> dict[str, Any] | None:
    expected = EXPECTED_LIVE_PATHS.get(constant)
    if not expected:
        return None
    hits = sorted(expected & paths)
    missing = sorted(expected - paths)
    return {
        "expected_count": len(expected),
        "matched_count": len(hits),
        "coverage": round(len(hits) / len(expected), 3),
        "matched_paths": hits,
        "missing_paths": missing,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="AST probe for GenFarmer node defaults/factory contexts")
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
    sources: list[tuple[str, bytes, Any]] = []

    try:
        ctx = AsarArchive(asar_path, mode="r")
    except TypeError:
        ctx = AsarArchive.open(str(asar_path))

    with ctx as archive:
        for raw_path in archive.list():
            path = str(raw_path).replace("\\", "/")
            pp = Path(path)
            if not path.startswith(args.assets-prefix if False else args.assets_prefix) or pp.suffix.lower() not in TEXT_SUFFIXES:
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

    palette_rows, constants, labels = discover_palette_rows(sources)
    known = set(constants)
    by_constant: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"object_candidates": [], "switch_cases": [], "computed_map_hits": []}
    )

    for path, src, root in sources:
        for node in walk(root):
            if node.type == "object":
                pairs = direct_pairs(src, node)
                if not pairs:
                    continue

                # Strongest pattern: direct action: H.CONSTANT in a non-palette object.
                action_node = pairs.get("action")
                action = member_constant(src, action_node) if action_node is not None else None
                if action and action in known:
                    paths, types = nested_shape(src, node)
                    path_set = set(paths)
                    parent_key = parent_pair_key(src, node)
                    role, score, reasons = classify_object(path_set, parent_key)
                    if not ({"label", "icon"}.issubset(pairs.keys())):
                        item = {
                            "file": path,
                            "role": role,
                            "score": score,
                            "reasons": reasons,
                            "parent_pair_key": parent_key,
                            "direct_property_keys": sorted(pairs.keys()),
                            "nested_key_paths": sorted(paths),
                            "field_types": {k: types[k] for k in sorted(types)},
                            "bytes": node.end_byte - node.start_byte,
                        }
                        overlap = live_overlap(action[1], path_set)
                        if overlap:
                            item["live_shape_validation"] = overlap
                        by_constant[action]["object_candidates"].append(item)

                # Computed map entry like {[H.ACTION]: handler} is represented by
                # a pair whose key subtree contains the member expression.
                for child in getattr(node, "named_children", []):
                    if child.type != "pair":
                        continue
                    key_node = child.child_by_field_name("key")
                    value_node = child.child_by_field_name("value")
                    if key_node is None or value_node is None:
                        continue
                    found: set[tuple[str, str]] = set()
                    for kchild in walk(key_node):
                        mc = member_constant(src, kchild)
                        if mc and mc in known:
                            found.add(mc)
                    for mc in found:
                        by_constant[mc]["computed_map_hits"].append({
                            "file": path,
                            "value_type": value_node.type,
                            "object_direct_keys": sorted(pairs.keys()),
                            "bytes": child.end_byte - child.start_byte,
                        })

            elif node.type == "switch_case":
                mc = switch_case_constant(src, node)
                if mc and mc in known:
                    item = summarize_switch_case(src, node)
                    item["file"] = path
                    by_constant[mc]["switch_cases"].append(item)

    catalog = []
    strong_count = 0
    for ns, const in sorted(known, key=lambda x: labels.get(x, x[1]).lower()):
        bucket = by_constant[(ns, const)]
        objects = sorted(
            bucket["object_candidates"],
            key=lambda x: (-x.get("score", 0), x.get("bytes", 10**9), x.get("file", "")),
        )
        switches = sorted(bucket["switch_cases"], key=lambda x: (x.get("bytes", 10**9), x.get("file", "")))
        maps = sorted(bucket["computed_map_hits"], key=lambda x: (x.get("bytes", 10**9), x.get("file", "")))
        if objects and objects[0].get("score", 0) >= 20:
            strong_count += 1
        catalog.append({
            "label": labels.get((ns, const)),
            "namespace": ns,
            "constant": const,
            "expression": f"{ns}.{const}",
            "best_object_candidates": objects[:5],
            "switch_cases": switches[:5],
            "computed_map_hits": maps[:5],
        })

    result = {
        "catalog_format": 1,
        "privacy": "shareable AST field/type structure only; no raw GenFarmer source snippets or arbitrary values",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "renderer_assets_parsed": len(sources),
        "palette_rows": len(palette_rows),
        "palette_constants": len(known),
        "actions_with_node_default_candidate_score_20_plus": strong_count,
        "actions": catalog,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-node-factory-ast-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "node-factory-ast.shareable.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER NODE FACTORY / DEFAULT-SCHEMA AST PROBE")
    print("=" * 78)
    print(f"Renderer assets parsed: {len(sources)}")
    print(f"Palette rows/constants: {len(palette_rows)}/{len(known)}")
    print(f"Actions with candidate score >=20: {strong_count}/{len(known)}")
    print("Per-action best construction evidence:")
    for item in catalog:
        objs = item["best_object_candidates"]
        if objs:
            best = objs[0]
            paths = best.get("nested_key_paths", [])
            shown = ", ".join(paths[:16]) if paths else "-"
            validation = best.get("live_shape_validation")
            val = f" live-overlap={validation['matched_count']}/{validation['expected_count']}" if validation else ""
            print(f" - {item['label']}: score={best['score']} role={best['role']} paths=[{shown}]{val}")
        else:
            sw = len(item["switch_cases"])
            mp = len(item["computed_map_hits"])
            print(f" - {item['label']}: no direct action-object candidate; switch={sw} map={mp}")
    print(f"Shareable result: {out.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
