#!/usr/bin/env python3
"""AST-based, read-only probe for GenFarmer Automation editor action/registry code.

Regex/proximity probes established that the minified renderer contains many
`action*` tokens and palette labels, but shared editor infrastructure made
per-action settings attribution noisy. This probe parses only renderer assets
that contain `action*` tokens and inspects the JavaScript syntax tree around
each occurrence.

Goals:
- distinguish identifiers from string/i18n keys;
- classify how each action token is used (call argument, object key/value, etc.);
- collect the *smallest syntactic contexts* around each occurrence;
- recover only structural metadata: object keys, safe string literals,
  identifier tokens, and candidate labels/internal action literals;
- never emit raw GenFarmer source snippets.

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
    print(
        'ERROR: missing tree-sitter dependencies; run: python -m pip install -e ".[dev]"',
        file=sys.stderr,
    )
    raise SystemExit(2)

ACTION_TOKEN_RE = re.compile(r"\baction[A-Z][A-Za-z0-9_]{1,80}\b")
TEXT_SUFFIXES = {".js", ".mjs", ".cjs"}
LIVE_ACTION_LITERALS = {"Start", "Variables", "ContextMenu", "Adb", "DeepSeek", "Pause", "Screenshot"}
KNOWN_LABELS = {
    "Press Back", "Press Home", "Press Menu", "Change device", "Start App", "Stop App",
    "Install App", "Uninstall App", "Is installed App", "Clear App Data", "Transfer File",
    "Device actions", "Toggle service", "Check activity", "Press key", "Type text",
    "Update field", "Get property", "Element exists", "Multi Element exists",
    "Get attribute", "Write file", "Save assets", "Set variable", "Insert data",
    "Open AI", "Case Path", "ADB shell command", "Sleep", "Screenshot", "DeepSeek",
    "Variables", "Context Menu",
}

INTERESTING_CONTEXT_TYPES = {
    "pair",
    "object",
    "array",
    "arguments",
    "call_expression",
    "variable_declarator",
    "lexical_declaration",
    "assignment_expression",
    "parenthesized_expression",
    "conditional_expression",
    "return_statement",
}

GENERIC_IDENTIFIERS = {
    "const", "let", "var", "true", "false", "null", "undefined", "return", "function",
    "Object", "Array", "String", "Number", "Boolean", "Math", "JSON", "console",
    "length", "value", "data", "props", "style", "className", "children", "default",
}


def default_asar() -> Path:
    local = os.getenv("LOCALAPPDATA")
    return Path(local or ".") / "Programs" / "GenFarmer" / "resources" / "app.asar"


def decode(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    return bytes(raw).decode("utf-8", errors="ignore")


def get_parser() -> Parser:
    language = Language(tsjs.language())
    try:
        return Parser(language)
    except TypeError:
        parser = Parser()
        parser.language = language
        return parser


def node_text(source: bytes, node: Any) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def strip_js_string(raw: str) -> str | None:
    raw = raw.strip()
    if len(raw) < 2 or raw[0] not in ('"', "'", "`") or raw[-1] != raw[0]:
        return None
    value = raw[1:-1]
    if "${" in value:
        return None
    value = value.replace("\\'", "'").replace('\\"', '"').replace("\\`", "`")
    value = value.replace("\\n", " ").replace("\\r", " ").strip()
    return value or None


def safe_literal(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not (1 <= len(value) <= 100):
        return None
    if any(x in value for x in ("\n", "\r", "http://", "https://", "@", "data:")):
        return None
    if not re.fullmatch(r"[A-Za-z0-9 _./:+()#%&,'!?\-]+", value):
        return None
    return value


def looks_label(value: str) -> bool:
    if value in KNOWN_LABELS:
        return True
    if not 2 <= len(value) <= 60:
        return False
    if " " not in value:
        return False
    words = value.split()
    if not 1 <= len(words) <= 7:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _/+&()\-]*", value))


def looks_internal_action_literal(value: str) -> bool:
    if value in LIVE_ACTION_LITERALS:
        return True
    if value.startswith("action"):
        return False
    return bool(re.fullmatch(r"[A-Z][A-Za-z0-9]{2,50}", value))


def walk(node: Any) -> Iterable[Any]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        try:
            children = current.children
        except Exception:
            children = []
        stack.extend(reversed(children))


def nearest_interesting_context(node: Any, max_bytes: int = 4500) -> Any:
    current = node
    best = node
    for _ in range(12):
        parent = getattr(current, "parent", None)
        if parent is None:
            break
        if parent.end_byte - parent.start_byte <= max_bytes:
            best = parent
            if parent.type in INTERESTING_CONTEXT_TYPES:
                # Keep climbing a little to capture the whole pair/object entry,
                # but never accept giant shared registry structures.
                current = parent
                continue
        break
    return best


def classify_usage(source: bytes, node: Any) -> dict[str, Any]:
    usage: dict[str, Any] = {"node_type": node.type}
    parent = getattr(node, "parent", None)
    if parent is not None:
        usage["parent_type"] = parent.type
    grand = getattr(parent, "parent", None) if parent is not None else None
    if grand is not None:
        usage["grandparent_type"] = grand.type

    # Determine whether this is a call argument and record only the callee token.
    current = node
    for _ in range(5):
        p = getattr(current, "parent", None)
        if p is None:
            break
        if p.type == "call_expression":
            fn = p.child_by_field_name("function")
            if fn is not None:
                callee = node_text(source, fn)
                if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$.]{0,80}", callee):
                    usage["call_callee"] = callee
            break
        current = p

    # Pair role is very useful for distinguishing translation keys from real
    # object/action values.
    current = node
    for _ in range(5):
        p = getattr(current, "parent", None)
        if p is None:
            break
        if p.type == "pair":
            key = p.child_by_field_name("key")
            value = p.child_by_field_name("value")
            if key is not None:
                key_text = node_text(source, key).strip("'\"`")
                if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]{0,80}", key_text):
                    usage["pair_key"] = key_text
            if key is not None and key.start_byte <= node.start_byte < key.end_byte:
                usage["pair_role"] = "key"
            elif value is not None and value.start_byte <= node.start_byte < value.end_byte:
                usage["pair_role"] = "value"
            break
        current = p
    return usage


def summarize_context(source: bytes, context: Any) -> dict[str, Any]:
    property_keys: Counter[str] = Counter()
    string_literals: Counter[str] = Counter()
    identifiers: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    internal_actions: Counter[str] = Counter()
    action_tokens: Counter[str] = Counter()

    for n in walk(context):
        if n.type in {"identifier", "property_identifier", "shorthand_property_identifier_pattern"}:
            text = node_text(source, n)
            if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]{1,80}", text):
                if n.type == "property_identifier":
                    property_keys[text] += 1
                if text not in GENERIC_IDENTIFIERS and len(text) >= 3:
                    identifiers[text] += 1
                if ACTION_TOKEN_RE.fullmatch(text):
                    action_tokens[text] += 1
        elif n.type in {"string", "template_string"}:
            value = safe_literal(strip_js_string(node_text(source, n)))
            if value:
                string_literals[value] += 1
                if looks_label(value):
                    labels[value] += 1
                if looks_internal_action_literal(value):
                    internal_actions[value] += 1
                if ACTION_TOKEN_RE.fullmatch(value):
                    action_tokens[value] += 1
        elif n.type == "pair":
            key = n.child_by_field_name("key")
            if key is not None:
                raw = node_text(source, key).strip("'\"`")
                if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]{1,80}", raw):
                    property_keys[raw] += 1

    return {
        "context_type": context.type,
        "context_bytes": context.end_byte - context.start_byte,
        "property_keys": [k for k, _ in property_keys.most_common(40)],
        "candidate_labels": [v for v, _ in labels.most_common(30)],
        "candidate_internal_action_literals": [v for v, _ in internal_actions.most_common(30)],
        "action_tokens_in_context": [v for v, _ in action_tokens.most_common(30)],
        "identifier_tokens": [v for v, _ in identifiers.most_common(50)],
        "safe_string_literals": [v for v, _ in string_literals.most_common(60)],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="AST-based GenFarmer Automation action/registry probe")
    p.add_argument("--asar", type=Path, default=default_asar())
    p.add_argument("--assets-prefix", default="dist/render/assets/")
    p.add_argument("--max-file-mb", type=int, default=8)
    args = p.parse_args()

    asar_path = args.asar.expanduser().resolve()
    if not asar_path.exists():
        print(f"ERROR: app.asar not found: {asar_path}", file=sys.stderr)
        return 2

    parser = get_parser()
    max_bytes = max(1, args.max_file_mb) * 1024 * 1024

    try:
        ctx = AsarArchive(asar_path, mode="r")
    except TypeError:
        ctx = AsarArchive.open(str(asar_path))

    action_records: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "files": set(),
            "usage_shapes": Counter(),
            "call_callees": Counter(),
            "pair_keys": Counter(),
            "pair_roles": Counter(),
            "contexts": [],
        }
    )
    parsed_files = 0
    candidate_files = 0
    parse_error_files = 0

    with ctx as archive:
        entries = [str(x).replace("\\", "/") for x in archive.list()]
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
            if isinstance(raw, str):
                source = raw.encode("utf-8")
            else:
                source = bytes(raw)
            if len(source) > max_bytes:
                continue
            text = source.decode("utf-8", errors="ignore")
            tokens_here = sorted(set(ACTION_TOKEN_RE.findall(text)))
            if not tokens_here:
                continue
            candidate_files += 1

            tree = parser.parse(source)
            parsed_files += 1
            if getattr(tree.root_node, "has_error", False):
                parse_error_files += 1

            wanted = set(tokens_here)
            for node in walk(tree.root_node):
                if node.type not in {"identifier", "property_identifier", "string", "template_string"}:
                    continue
                raw_text = node_text(source, node)
                if node.type in {"string", "template_string"}:
                    value = strip_js_string(raw_text)
                else:
                    value = raw_text
                if value not in wanted:
                    continue

                record = action_records[value]
                record["files"].add(path)
                usage = classify_usage(source, node)
                shape = "/".join(x for x in (
                    usage.get("node_type"), usage.get("parent_type"), usage.get("grandparent_type")
                ) if x)
                record["usage_shapes"][shape] += 1
                if usage.get("call_callee"):
                    record["call_callees"][usage["call_callee"]] += 1
                if usage.get("pair_key"):
                    record["pair_keys"][usage["pair_key"]] += 1
                if usage.get("pair_role"):
                    record["pair_roles"][usage["pair_role"]] += 1

                context = nearest_interesting_context(node)
                summary = summarize_context(source, context)
                summary["file"] = path
                summary["usage"] = usage
                record["contexts"].append(summary)

    serial_actions = []
    for action, record in sorted(action_records.items()):
        # Smallest contexts are usually the most useful in minified bundles.
        contexts = sorted(
            record["contexts"],
            key=lambda c: (c.get("context_bytes", 10**9), c.get("file", "")),
        )
        # Deduplicate equivalent structural contexts.
        dedup = []
        seen = set()
        for c in contexts:
            key = (
                c.get("file"), c.get("context_type"), tuple(c.get("property_keys", [])),
                tuple(c.get("candidate_labels", [])), tuple(c.get("candidate_internal_action_literals", [])),
                c.get("usage", {}).get("node_type"), c.get("usage", {}).get("call_callee"),
                c.get("usage", {}).get("pair_key"), c.get("usage", {}).get("pair_role"),
            )
            if key in seen:
                continue
            seen.add(key)
            dedup.append(c)
            if len(dedup) >= 8:
                break
        serial_actions.append({
            "action_token": action,
            "files": sorted(record["files"]),
            "usage_shapes": dict(record["usage_shapes"].most_common()),
            "call_callees": dict(record["call_callees"].most_common()),
            "pair_keys": dict(record["pair_keys"].most_common()),
            "pair_roles": dict(record["pair_roles"].most_common()),
            "smallest_structural_contexts": dedup,
        })

    # Global classification helps answer a critical question: are action* names
    # mostly translation/i18n strings or true runtime identifiers?
    global_node_types = Counter()
    global_callees = Counter()
    for item in serial_actions:
        for shape, count in item["usage_shapes"].items():
            head = shape.split("/", 1)[0]
            global_node_types[head] += count
        for callee, count in item["call_callees"].items():
            global_callees[callee] += count

    result = {
        "catalog_format": 1,
        "privacy": "shareable AST structure only; no raw GenFarmer source snippets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "genfarmer_package": "resources/app.asar",
        "renderer_candidate_files": candidate_files,
        "renderer_files_parsed": parsed_files,
        "renderer_files_with_parse_errors": parse_error_files,
        "action_token_count": len(serial_actions),
        "global_action_token_node_types": dict(global_node_types.most_common()),
        "global_action_token_call_callees": dict(global_callees.most_common()),
        "actions": serial_actions,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-ast-registry-probe-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "ast-registry.shareable.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER AST REGISTRY / ACTION-USAGE PROBE")
    print("=" * 78)
    print(f"Renderer assets containing action* tokens: {candidate_files}")
    print(f"Renderer assets parsed: {parsed_files} (parse-error roots: {parse_error_files})")
    print(f"Action tokens classified: {len(serial_actions)}")
    print("Global action-token AST node types:")
    for key, count in global_node_types.most_common(12):
        print(f" - {key}: {count}")
    if global_callees:
        print("Top call callees receiving action tokens:")
        for key, count in global_callees.most_common(12):
            print(f" - {key}: {count}")
    print("Per-action smallest structural evidence:")
    for item in serial_actions:
        first = item["smallest_structural_contexts"][0] if item["smallest_structural_contexts"] else {}
        usage = first.get("usage", {})
        labels = first.get("candidate_labels", [])[:4]
        internals = first.get("candidate_internal_action_literals", [])[:4]
        keys = first.get("property_keys", [])[:8]
        print(
            f" - {item['action_token']}: node={usage.get('node_type','-')} "
            f"callee={usage.get('call_callee','-')} pair={usage.get('pair_key','-')}/{usage.get('pair_role','-')} "
            f"labels=[{', '.join(labels) if labels else '-'}] "
            f"internal=[{', '.join(internals) if internals else '-'}] "
            f"keys=[{', '.join(keys) if keys else '-'}]"
        )
    print(f"Shareable result: {out.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
