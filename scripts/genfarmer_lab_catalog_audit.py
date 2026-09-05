#!/usr/bin/env python3
"""Audit live GenFarmer lab-flow coverage against the 2.6.1 palette catalog.

This is the pivot from renderer-source discovery to exact saved-template learning.
The script is GET-only.  It reads a dedicated lab Automation App (default name
``GF Lab - Node Catalog``), extracts privacy-safe ``data.action`` and field/type
shapes, and compares them with the 60 source-proven palette rows.

Raw node IDs, user-entered labels/text/selectors/commands and app-specific scalar
values are never written to the shareable report.
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
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.flow import FlowDocument, find_flow  # noqa: E402
from genfarmer_automation.genfarmer_client import GenFarmerClient, GenFarmerError  # noqa: E402
from genfarmer_automation.palette_catalog_261 import (  # noqa: E402
    PALETTE_261,
    RESOLVED_ACTIONS_261,
    SPECIAL_LIVE_NODES_261,
    UNRESOLVED_PALETTE_261,
    by_action,
)

SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,120}$")
SAFE_OPTION_VALUE_KEYS = {"breakpoint", "disabled", "timeoutType"}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def discover_user_id(value: Any) -> str | int | None:
    if isinstance(value, Mapping):
        for key in ("id", "userId", "user_id"):
            candidate = value.get(key)
            if isinstance(candidate, (str, int)):
                return candidate
        for key in ("user", "data", "result"):
            found = discover_user_id(value.get(key))
            if found is not None:
                return found
    return None


def extract_app_records(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obj in iter_dicts(value):
        app_id = obj.get("id")
        name = obj.get("name")
        if not isinstance(app_id, (str, int)) or not isinstance(name, str):
            continue
        key = str(app_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(obj)
    return out


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def safe_action(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if not isinstance(data, Mapping):
        return None
    value = data.get("action")
    if isinstance(value, str) and SAFE_TOKEN_RE.fullmatch(value):
        return value
    return None


def option_shape(node: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    data = node.get("data")
    if not isinstance(data, Mapping):
        return {}, {}
    options = data.get("options")
    if not isinstance(options, Mapping):
        return {}, {}
    shape = {str(k): value_type(v) for k, v in sorted(options.items(), key=lambda kv: str(kv[0]))}
    safe_values: dict[str, Any] = {}
    for key in SAFE_OPTION_VALUE_KEYS:
        value = options.get(key)
        if value is None or isinstance(value, (bool, int, float)):
            if key in options:
                safe_values[key] = value
        elif isinstance(value, str) and SAFE_TOKEN_RE.fullmatch(value):
            safe_values[key] = value
    return shape, safe_values


def data_shape(node: Mapping[str, Any]) -> dict[str, str]:
    data = node.get("data")
    if not isinstance(data, Mapping):
        return {}
    return {str(k): value_type(v) for k, v in sorted(data.items(), key=lambda kv: str(kv[0]))}


def select_app(client: GenFarmerClient, user_id: str | int | None, app_id: str | None, app_name: str) -> tuple[Any, str]:
    if app_id:
        return client.get_app(app_id), "app-id"

    matches: list[dict[str, Any]] = []
    for page in range(1, 21):
        payload = client.list_apps(user_id=user_id, page=page, limit=100)
        records = extract_app_records(payload)
        matches.extend(r for r in records if r.get("name") == app_name)
        if not records or len(records) < 100:
            break
    # Deduplicate IDs in case nested response structures repeated a record.
    unique = {str(r["id"]): r for r in matches}
    if not unique:
        raise GenFarmerError(
            f'lab app not found by exact name {app_name!r}; create it in GenFarmer or pass --app-id'
        )
    if len(unique) != 1:
        raise GenFarmerError(
            f'found {len(unique)} apps named {app_name!r}; pass --app-id to select one explicitly'
        )
    selected_id = next(iter(unique))
    return client.get_app(selected_id), "exact-name"


def main() -> int:
    ap = argparse.ArgumentParser(description="GET-only coverage audit for GF Lab - Node Catalog")
    ap.add_argument("--app-id", help="Explicit lab Automation App ID")
    ap.add_argument("--app-name", default="GF Lab - Node Catalog")
    ap.add_argument("--batch-size", type=int, default=15, help="Print this many next-missing labels")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    client = GenFarmerClient(base_url, timeout=12.0, allow_mutations=False)
    try:
        user_id = discover_user_id(client.get_current_user())
        detail, selected_by = select_app(client, user_id, args.app_id, args.app_name)
        flow = find_flow(detail)
        if flow is None:
            raise GenFarmerError("selected lab app has no script.flow")
        doc = FlowDocument.from_flow(flow)
    except (GenFarmerError, Exception) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    observed_counts: Counter[str] = Counter()
    families: dict[str, Counter[str]] = defaultdict(Counter)
    option_shapes: dict[str, Counter[str]] = defaultdict(Counter)
    data_shapes: dict[str, Counter[str]] = defaultdict(Counter)
    safe_option_values: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    nodes_without_safe_action = 0

    for node in doc.nodes:
        if not isinstance(node, Mapping):
            continue
        action = safe_action(node)
        if not action:
            nodes_without_safe_action += 1
            continue
        observed_counts[action] += 1
        family = node.get("type")
        family_token = str(family) if isinstance(family, (str, int)) and SAFE_TOKEN_RE.fullmatch(str(family)) else "<unknown>"
        families[action][family_token] += 1
        opts, safe_values = option_shape(node)
        option_shapes[action][json.dumps(opts, sort_keys=True, separators=(",", ":"))] += 1
        data_shapes[action][json.dumps(data_shape(node), sort_keys=True, separators=(",", ":"))] += 1
        for key, value in safe_values.items():
            safe_option_values[action][key][json.dumps(value, sort_keys=True)] += 1

    observed = set(observed_counts)
    expected = set(RESOLVED_ACTIONS_261)
    specials = set(SPECIAL_LIVE_NODES_261)
    captured = expected & observed
    missing = expected - observed
    unexpected = observed - expected - specials

    missing_rows = []
    for item in PALETTE_261:
        if item.action and item.action in missing:
            missing_rows.append({
                "label": item.label,
                "constant": item.constant,
                "action": item.action,
                "provenance": item.provenance,
            })

    captured_rows = []
    for action in sorted(captured):
        item = by_action(action)
        if item:
            captured_rows.append({
                "label": item.label,
                "constant": item.constant,
                "action": action,
                "count": observed_counts[action],
            })

    semantic_shapes = []
    for action in sorted(observed_counts):
        item = by_action(action)
        semantic_shapes.append({
            "action": action,
            "palette_label": item.label if item else None,
            "count": observed_counts[action],
            "families": dict(sorted(families[action].items())),
            "data_shapes": [
                {"count": count, "fields": json.loads(sig)}
                for sig, count in sorted(data_shapes[action].items())
            ],
            "option_shapes": [
                {"count": count, "options": json.loads(sig)}
                for sig, count in sorted(option_shapes[action].items())
            ],
            "safe_option_values": {
                key: [
                    {"value": json.loads(encoded), "count": count}
                    for encoded, count in sorted(counter.items())
                ]
                for key, counter in sorted(safe_option_values[action].items())
            },
        })

    unresolved_source_rows = [
        {"label": item.label, "constant": item.constant, "provenance": item.provenance}
        for item in UNRESOLVED_PALETTE_261
    ]

    result = {
        "catalog_format": 1,
        "privacy": "shareable live lab coverage/field-type shapes only; raw node IDs and user-entered values omitted",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "selected_by": selected_by,
        "requested_lab_name": args.app_name if selected_by == "exact-name" else None,
        "source_palette_rows": len(PALETTE_261),
        "source_resolved_actions": len(expected),
        "source_unresolved_actions": len(UNRESOLVED_PALETTE_261),
        "flow_node_count": len(doc.nodes),
        "flow_edge_count": len(doc.edges),
        "nodes_without_safe_action": nodes_without_safe_action,
        "captured_resolved_actions": len(captured),
        "missing_resolved_actions": len(missing),
        "coverage_ratio": round(len(captured) / len(expected), 4) if expected else 0.0,
        "captured_palette_rows": captured_rows,
        "missing_palette_rows": missing_rows,
        "unresolved_source_rows": unresolved_source_rows,
        "unmatched_observed_actions": [
            {"action": action, "count": observed_counts[action]} for action in sorted(unexpected)
        ],
        "special_live_nodes_observed": [
            {"action": action, "count": observed_counts[action]}
            for action in SPECIAL_LIVE_NODES_261 if action in observed_counts
        ],
        "semantic_shapes": semantic_shapes,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-lab-catalog-audit-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "lab-catalog-audit.shareable.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER GF LAB NODE CATALOG AUDIT")
    print("=" * 78)
    print(f"Source palette rows: {len(PALETTE_261)}")
    print(f"Resolved source actions: {len(expected)}; unresolved source rows: {len(UNRESOLVED_PALETTE_261)}")
    print(f"Lab flow: nodes={len(doc.nodes)} edges={len(doc.edges)}")
    print(f"Captured resolved actions: {len(captured)}/{len(expected)} ({result['coverage_ratio'] * 100:.1f}%)")
    print(f"Missing resolved actions: {len(missing)}")
    if unexpected:
        print("Unmatched observed actions (important for resolving source ambiguity):")
        for action in sorted(unexpected):
            print(f" - {action}: count={observed_counts[action]}")
    print("Still source-unresolved palette rows:")
    for item in UNRESOLVED_PALETTE_261:
        print(f" - {item.label}: {item.constant}")
    if missing_rows:
        n = max(1, args.batch_size)
        print(f"Next missing palette labels (up to {n}):")
        for row in missing_rows[:n]:
            print(f" - {row['label']} -> {row['action']}")
    print(f"Shareable result: {out.relative_to(ROOT)}")
    print("GET only; no GenFarmer state was modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
