#!/usr/bin/env python3
"""Capture exact GenFarmer lab templates privately and emit a shareable inventory.

GET-only. The exact ``script.flow`` from ``GF Lab - Node Catalog`` is written
under an ignored ``evidence/.../private`` directory so it can feed the local
TemplateRegistry without publishing user/client values. A separate shareable
report contains only semantic action names, node families, field/type shapes,
safe runtime enum/default values, and structural fingerprints for nodes that do
not expose ``data.action`` (important for Group Node and editor helper nodes).
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
from genfarmer_automation.palette_catalog_261 import PALETTE_261, by_action  # noqa: E402

SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,120}$")
SAFE_OPTION_KEYS = {"breakpoint", "disabled", "timeoutType"}
SAFE_NODE_KEYS = {"type", "sourcePosition", "targetPosition", "extent"}


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
    selected_id = next(iter(matches))
    return client.get_app(selected_id), "exact-name"


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


def shape(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): value_type(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}


def safe_action(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if not isinstance(data, Mapping):
        return None
    action = data.get("action")
    if isinstance(action, str) and SAFE_TOKEN_RE.fullmatch(action):
        return action
    return None


def safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and SAFE_TOKEN_RE.fullmatch(value):
        return value
    return None


def semantic_record(node: Mapping[str, Any]) -> dict[str, Any]:
    action = safe_action(node)
    data = node.get("data") if isinstance(node.get("data"), Mapping) else {}
    options = data.get("options") if isinstance(data.get("options"), Mapping) else {}
    family = node.get("type")
    family_safe = family if isinstance(family, str) and SAFE_TOKEN_RE.fullmatch(family) else "<unknown>"

    safe_node_values: dict[str, Any] = {}
    for key in SAFE_NODE_KEYS:
        if key in node:
            value = safe_scalar(node.get(key))
            if value is not None:
                safe_node_values[key] = value

    safe_option_values: dict[str, Any] = {}
    for key in SAFE_OPTION_KEYS:
        if key in options:
            value = safe_scalar(options.get(key))
            if value is not None:
                safe_option_values[key] = value

    palette = by_action(action) if action else None
    return {
        "action": action,
        "palette_label": palette.label if palette else None,
        "family": family_safe,
        "top_level_shape": shape(node),
        "data_shape": shape(data),
        "options_shape": shape(options),
        "safe_node_values": safe_node_values,
        "safe_option_values": safe_option_values,
    }


def fingerprint(record: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "action": record.get("action"),
            "family": record.get("family"),
            "top": record.get("top_level_shape"),
            "data": record.get("data_shape"),
            "options": record.get("options_shape"),
            "safe_node": record.get("safe_node_values"),
            "safe_options": record.get("safe_option_values"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="GET-only private template capture for GF Lab - Node Catalog")
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

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-lab-template-capture-{stamp}"
    private_dir = out_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)

    # Exact raw flow is intentionally local-only/ignored. This is the source of
    # truth for TemplateRegistry cloning and later one-field differential tests.
    raw_path = private_dir / "flow.raw.json"
    raw_path.write_text(json.dumps(flow, ensure_ascii=False, indent=2), encoding="utf-8")

    grouped: dict[str, dict[str, Any]] = {}
    action_counts: Counter[str] = Counter()
    no_action_count = 0

    for node in doc.nodes:
        if not isinstance(node, Mapping):
            continue
        rec = semantic_record(node)
        fp = fingerprint(rec)
        entry = grouped.setdefault(fp, {"count": 0, "record": rec})
        entry["count"] += 1
        if rec.get("action"):
            action_counts[str(rec["action"])] += 1
        else:
            no_action_count += 1

    inventory = [
        {"count": item["count"], **item["record"]}
        for item in sorted(
            grouped.values(),
            key=lambda x: (
                str(x["record"].get("action") or ""),
                str(x["record"].get("family") or ""),
                json.dumps(x["record"].get("data_shape", {}), sort_keys=True),
            ),
        )
    ]

    observed_actions = set(action_counts)
    palette_actions = {item.action for item in PALETTE_261 if item.action}
    missing_palette_actions = sorted(palette_actions - observed_actions)
    unexpected_actions = sorted(observed_actions - palette_actions - {"Start", "Variables", "ContextMenu"})

    result = {
        "catalog_format": 1,
        "privacy": "shareable structural inventory only; exact flow stored separately under ignored private evidence",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "selected_by": selected_by,
        "flow_node_count": len(doc.nodes),
        "flow_edge_count": len(doc.edges),
        "distinct_node_fingerprints": len(inventory),
        "nodes_without_safe_action": no_action_count,
        "observed_action_count": len(observed_actions),
        "missing_palette_actions": missing_palette_actions,
        "unexpected_actions": unexpected_actions,
        "node_inventory": inventory,
    }

    shareable = out_dir / "template-inventory.shareable.json"
    shareable.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER LAB TEMPLATE CAPTURE")
    print("=" * 78)
    print(f"Lab flow: nodes={len(doc.nodes)} edges={len(doc.edges)}")
    print(f"Observed distinct actions: {len(observed_actions)}")
    print(f"Distinct structural fingerprints: {len(inventory)}")
    print(f"Nodes without safe data.action: {no_action_count}")
    if missing_palette_actions:
        print("Palette actions not represented by data.action:")
        for action in missing_palette_actions:
            print(f" - {action}")
    if unexpected_actions:
        print("Unexpected actions:")
        for action in unexpected_actions:
            print(f" - {action}")
    print("No-action structural fingerprints:")
    for item in inventory:
        if item.get("action") is not None:
            continue
        print(
            " - family={family} count={count} data=[{data}] options=[{options}]".format(
                family=item.get("family"),
                count=item.get("count"),
                data=", ".join(item.get("data_shape", {}).keys()) or "-",
                options=", ".join(item.get("options_shape", {}).keys()) or "-",
            )
        )
    print(f"Private exact flow: {raw_path.relative_to(ROOT)}")
    print(f"Shareable inventory: {shareable.relative_to(ROOT)}")
    print("GET only; no GenFarmer state was modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
