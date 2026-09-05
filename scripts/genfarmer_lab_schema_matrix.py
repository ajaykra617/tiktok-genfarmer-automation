#!/usr/bin/env python3
"""Build a privacy-safe settings/default-schema matrix from the full GF Lab flow.

GET-only. The dedicated ``GF Lab - Node Catalog`` now contains one live-saved
instance of every ordinary GenFarmer 2.6.1 action node plus the three special
editor nodes. This script turns that exact live corpus into a per-action schema:

- node family/type;
- top-level field/type paths;
- ``data`` field/type paths;
- complete nested ``data.options`` field/type paths;
- action-specific option fields after separating common runtime controls;
- safe primitive defaults (bool/number/null and allowlisted enum strings);
- palette label/provenance when known.

It never writes node IDs or arbitrary string values to the shareable report.
Exact raw values remain available only in the ignored private template capture.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import json
import math
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
    EDITOR_STRUCTURAL_ROWS_261,
    LIVE_NODE_ACTIONS_261,
    SPECIAL_LIVE_NODES_261,
    by_action,
)

SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,120}$")
SAFE_STRING_DEFAULT_KEYS = {"timeoutType"}
KNOWN_RUNTIME_OPTIONS = {
    "breakpoint",
    "disabled",
    "nodeLog",
    "nodeSleep",
    "nodeTimeout",
    "timeoutAdbReconnect",
    "timeoutNextNode",
}


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


def select_app(client: GenFarmerClient, user_id: str | int | None, app_id: str | None, app_name: str) -> tuple[Any, str]:
    if app_id:
        return client.get_app(app_id), "app-id"
    matches: dict[str, dict[str, Any]] = {}
    for page in range(1, 21):
        payload = client.list_apps(user_id=user_id, page=page, limit=100)
        records = extract_app_records(payload)
        for record in records:
            if record.get("name") == app_name:
                matches[str(record["id"])] = record
        if not records or len(records) < 100:
            break
    if not matches:
        raise GenFarmerError(f"lab app not found by exact name {app_name!r}")
    if len(matches) != 1:
        raise GenFarmerError(f"found {len(matches)} apps named {app_name!r}; pass --app-id")
    return client.get_app(next(iter(matches))), "exact-name"


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
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def flatten_shape(value: Any, prefix: str = "", depth: int = 0, max_depth: int = 4) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(value, Mapping) or depth > max_depth:
        return out
    for raw_key, child in sorted(value.items(), key=lambda kv: str(kv[0])):
        key = str(raw_key)
        path = f"{prefix}.{key}" if prefix else key
        out[path] = value_type(child)
        if isinstance(child, Mapping) and depth < max_depth:
            out.update(flatten_shape(child, path, depth + 1, max_depth))
    return out


def safe_action(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if not isinstance(data, Mapping):
        return None
    action = data.get("action")
    return action if isinstance(action, str) and SAFE_TOKEN_RE.fullmatch(action) else None


def safe_defaults(options: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_key, value in options.items():
        key = str(raw_key)
        if value is None or isinstance(value, (bool, int, float)):
            out[key] = value
        elif key in SAFE_STRING_DEFAULT_KEYS and isinstance(value, str) and SAFE_TOKEN_RE.fullmatch(value):
            out[key] = value
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="GET-only full settings schema matrix for GF Lab - Node Catalog")
    ap.add_argument("--app-id")
    ap.add_argument("--app-name", default="GF Lab - Node Catalog")
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

    records: list[dict[str, Any]] = []
    option_presence: Counter[str] = Counter()
    top_option_presence: Counter[str] = Counter()

    for node in doc.nodes:
        if not isinstance(node, Mapping):
            continue
        action = safe_action(node)
        if not action:
            continue
        data = node.get("data") if isinstance(node.get("data"), Mapping) else {}
        options = data.get("options") if isinstance(data.get("options"), Mapping) else {}
        option_shape = flatten_shape(options)
        for path in option_shape:
            option_presence[path] += 1
        for key in options:
            top_option_presence[str(key)] += 1

        family = node.get("type")
        family_safe = str(family) if isinstance(family, (str, int)) else "<unknown>"
        palette = by_action(action)
        record = {
            "action": action,
            "palette_label": palette.label if palette and palette.role == "action-node" else None,
            "palette_provenance": palette.provenance if palette and palette.role == "action-node" else None,
            "special_editor_node": action in SPECIAL_LIVE_NODES_261,
            "family": family_safe,
            "top_level_shape": flatten_shape(node),
            "data_shape": flatten_shape(data),
            "options_shape": option_shape,
            "safe_option_defaults": safe_defaults(options),
        }
        records.append(record)

    action_count = len(records)
    # Derived common keys are informational only. The explicit runtime set stays
    # authoritative for separating known runtime controls from action settings.
    derived_threshold = max(3, math.ceil(action_count * 0.50))
    derived_common = sorted(k for k, count in top_option_presence.items() if count >= derived_threshold)

    for record in records:
        top_options = {
            path: typ for path, typ in record["options_shape"].items() if "." not in path
        }
        record["runtime_option_fields"] = {
            key: top_options[key] for key in sorted(top_options) if key in KNOWN_RUNTIME_OPTIONS
        }
        record["action_specific_option_fields"] = {
            key: top_options[key] for key in sorted(top_options) if key not in KNOWN_RUNTIME_OPTIONS
        }
        data_top = {
            path: typ for path, typ in record["data_shape"].items() if "." not in path
        }
        record["action_specific_data_fields"] = {
            key: data_top[key]
            for key in sorted(data_top)
            if key not in {"action", "options", "successNode", "failNode"}
        }

    records.sort(key=lambda r: (str(r.get("palette_label") or r["action"]).lower(), r["action"]))
    observed = {r["action"] for r in records}
    expected = set(LIVE_NODE_ACTIONS_261)
    specials = set(SPECIAL_LIVE_NODES_261)

    result = {
        "catalog_format": 1,
        "privacy": "shareable field/type schema; arbitrary strings and node IDs omitted",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "selected_by": selected_by,
        "flow_node_count": len(doc.nodes),
        "flow_edge_count": len(doc.edges),
        "schema_action_count": len(records),
        "expected_palette_action_nodes": len(expected),
        "captured_palette_action_nodes": len(expected & observed),
        "special_editor_nodes_expected": list(SPECIAL_LIVE_NODES_261),
        "special_editor_nodes_captured": [x for x in SPECIAL_LIVE_NODES_261 if x in observed],
        "editor_structural_rows_not_serialized_as_action_nodes": [
            {"label": row.label, "constant": row.constant, "source_action": row.action}
            for row in EDITOR_STRUCTURAL_ROWS_261
        ],
        "known_runtime_option_keys": sorted(KNOWN_RUNTIME_OPTIONS),
        "derived_common_top_option_keys": derived_common,
        "top_option_key_frequency": dict(sorted(top_option_presence.items(), key=lambda kv: (-kv[1], kv[0]))),
        "nested_option_path_frequency": dict(sorted(option_presence.items(), key=lambda kv: (-kv[1], kv[0]))),
        "actions": records,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-lab-schema-matrix-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "schema-matrix.shareable.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER FULL LIVE NODE SETTINGS SCHEMA MATRIX")
    print("=" * 78)
    print(f"Lab flow: nodes={len(doc.nodes)} edges={len(doc.edges)}")
    print(f"Action schemas captured: {len(records)}")
    print(f"Palette action templates: {len(expected & observed)}/{len(expected)}")
    print(f"Special editor nodes: {len(specials & observed)}/{len(specials)}")
    print("Known common runtime option keys:")
    print(" - " + ", ".join(sorted(KNOWN_RUNTIME_OPTIONS)))
    if derived_common:
        print("Derived >=50% common option keys:")
        print(" - " + ", ".join(derived_common))
    print("Per-action settings summary:")
    for record in records:
        label = record.get("palette_label") or record["action"]
        specific = record.get("action_specific_option_fields", {})
        data_extra = record.get("action_specific_data_fields", {})
        specific_text = ", ".join(f"{k}:{v}" for k, v in specific.items()) or "-"
        data_text = ", ".join(f"{k}:{v}" for k, v in data_extra.items()) or "-"
        print(
            f" - {label} [{record['action']}]: family={record['family']} "
            f"options={len(record['options_shape'])} specific=[{specific_text}] data-extra=[{data_text}]"
        )
    print("Editor-structural source rows not expected as standalone data.action nodes:")
    for row in EDITOR_STRUCTURAL_ROWS_261:
        print(f" - {row.label}: {row.constant} source-action={row.action}")
    print(f"Shareable result: {out.relative_to(ROOT)}")
    print("GET only; no GenFarmer state was modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
