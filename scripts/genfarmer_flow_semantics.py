#!/usr/bin/env python3
"""Build a privacy-safe semantic catalog for GenFarmer ``script.flow``.

The structural learner intentionally avoided scalar values, but GenFarmer uses
broad Vue Flow rendering families such as ``type=custom`` for many different
operations. The operation identity is commonly carried by ``data.action``.

This learner therefore exposes only a strict allowlist of internal semantic
values (for example node family, data.action, handle names and timeout mode)
while continuing to redact user-entered text, selectors, commands, IDs, labels,
credentials and app-specific values.

GET requests only. No GenFarmer state is modified.
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
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.flow import FlowDocument, find_flow  # noqa: E402
from genfarmer_automation.genfarmer_client import GenFarmerClient, GenFarmerError  # noqa: E402

SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,120}$")

# Scalar values from these exact paths are useful for reverse engineering and
# are not expected to contain account/client data. Everything else is type-only.
SAFE_SCALAR_PATHS = {
    "type",
    "sourcePosition",
    "targetPosition",
    "data.action",
    "data.options.breakpoint",
    "data.options.disabled",
    "data.options.timeoutType",
    "animated",
    "updatable",
    "sourceHandle",
    "targetHandle",
    "data.sourceHandle",
    "data.targetHandle",
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


def discover_user_id(data: Any) -> str | int | None:
    if isinstance(data, Mapping):
        for key in ("id", "userId", "user_id"):
            value = data.get(key)
            if isinstance(value, (str, int)):
                return value
        for key in ("user", "data", "result"):
            found = discover_user_id(data.get(key))
            if found is not None:
                return found
    return None


def iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def extract_app_records(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obj in iter_dicts(value):
        app_id = obj.get("id")
        if not isinstance(app_id, (str, int)):
            continue
        if not any(key in obj for key in ("name", "version", "script", "description", "updatedAt", "userId")):
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


def get_path(obj: Mapping[str, Any], path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def safe_scalar(path: str, value: Any) -> Any:
    if path not in SAFE_SCALAR_PATHS:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and SAFE_TOKEN_RE.fullmatch(value):
        return value
    return "<redacted-non-token>"


def option_shape(node: Mapping[str, Any]) -> dict[str, str]:
    data = node.get("data")
    if not isinstance(data, Mapping):
        return {}
    options = data.get("options")
    if not isinstance(options, Mapping):
        return {}
    return {str(k): value_type(v) for k, v in sorted(options.items(), key=lambda kv: str(kv[0]))}


def semantic_identity(node: Mapping[str, Any]) -> tuple[str, str | None, str]:
    family_raw = node.get("type")
    family = str(family_raw) if isinstance(family_raw, (str, int)) else "<unknown-family>"
    action_raw = get_path(node, "data.action")
    action: str | None = None
    if isinstance(action_raw, str) and SAFE_TOKEN_RE.fullmatch(action_raw):
        action = action_raw
    semantic = f"{family}:{action}" if action else family
    return family, action, semantic


def main() -> int:
    parser = argparse.ArgumentParser(description="GET-only semantic learner for GenFarmer script.flow")
    parser.add_argument("--app-id", action="append", default=[], help="Only inspect this app ID; repeatable")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    client = GenFarmerClient(base_url, timeout=12.0, allow_mutations=False)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = ROOT / "evidence" / f"genfarmer-flow-semantics-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    try:
        user_id = discover_user_id(client.get_current_user())
    except GenFarmerError as exc:
        print(f"ERROR: cannot read current user: {exc}", file=sys.stderr)
        return 1

    requested_ids = {str(x) for x in args.app_id}
    app_ids: set[str] = set(requested_ids)
    if not app_ids:
        for page in range(1, max(1, args.max_pages) + 1):
            try:
                payload = client.list_apps(user_id=user_id, page=page, limit=max(1, args.limit))
            except GenFarmerError as exc:
                print(f"ERROR listing apps page {page}: {exc}", file=sys.stderr)
                return 1
            records = extract_app_records(payload)
            before = len(app_ids)
            app_ids.update(str(r["id"]) for r in records)
            if not records or len(app_ids) == before or len(records) < max(1, args.limit):
                break

    semantic: dict[str, dict[str, Any]] = {}
    family_counts: Counter[str] = Counter()
    edge_shapes: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []
    total_nodes = 0
    total_edges = 0

    for app_id in sorted(app_ids):
        try:
            detail = client.get_app(app_id)
            flow = find_flow(detail)
            if flow is None:
                failures.append({"app_id": app_id, "reason": "no script.flow"})
                continue
            doc = FlowDocument.from_flow(flow)
        except (GenFarmerError, Exception) as exc:
            failures.append({"app_id": app_id, "reason": str(exc)})
            continue

        for node in doc.nodes:
            if not isinstance(node, Mapping):
                continue
            total_nodes += 1
            family, action, key = semantic_identity(node)
            family_counts[family] += 1
            entry = semantic.setdefault(
                key,
                {
                    "semantic_kind": key,
                    "family": family,
                    "action": action,
                    "count": 0,
                    "option_shapes": defaultdict(int),
                    "safe_scalars": defaultdict(Counter),
                },
            )
            entry["count"] += 1
            options = option_shape(node)
            option_sig = json.dumps(options, sort_keys=True, separators=(",", ":"))
            entry["option_shapes"][option_sig] += 1
            for path in SAFE_SCALAR_PATHS:
                value = safe_scalar(path, get_path(node, path))
                if value is not None:
                    entry["safe_scalars"][path][json.dumps(value, sort_keys=True)] += 1

        for edge in doc.edges:
            if not isinstance(edge, Mapping):
                continue
            total_edges += 1
            safe = {}
            for path in ("type", "animated", "updatable", "sourceHandle", "targetHandle", "data.sourceHandle", "data.targetHandle"):
                value = safe_scalar(path, get_path(edge, path))
                if value is not None:
                    safe[path] = value
            sig = json.dumps(safe, sort_keys=True, separators=(",", ":"))
            e = edge_shapes.setdefault(sig, {"count": 0, "safe_semantics": safe})
            e["count"] += 1

    serial_nodes: list[dict[str, Any]] = []
    for key in sorted(semantic):
        entry = semantic[key]
        serial_nodes.append(
            {
                "semantic_kind": entry["semantic_kind"],
                "family": entry["family"],
                "action": entry["action"],
                "count": entry["count"],
                "option_shapes": [
                    {"count": count, "options": json.loads(sig)}
                    for sig, count in sorted(entry["option_shapes"].items())
                ],
                "safe_scalars": {
                    path: [
                        {"value": json.loads(encoded), "count": count}
                        for encoded, count in sorted(counter.items())
                    ]
                    for path, counter in sorted(entry["safe_scalars"].items())
                },
            }
        )

    output = {
        "catalog_format": 1,
        "privacy": "shareable semantic catalog; only strict internal action/handle/enum tokens are retained",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "apps_requested": len(app_ids),
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "node_family_counts": dict(sorted(family_counts.items())),
        "distinct_semantic_kinds": len(serial_nodes),
        "semantic_nodes": serial_nodes,
        "edge_semantics": [edge_shapes[key] for key in sorted(edge_shapes)],
        "failures": failures,
    }

    out_path = evidence_dir / "flow-semantics.shareable.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 76)
    print("GENFARMER SCRIPT.FLOW SEMANTIC CATALOG")
    print("=" * 76)
    print(f"Apps inspected: {len(app_ids)}")
    print(f"Nodes observed: {total_nodes}")
    print(f"Edges observed: {total_edges}")
    print(f"Semantic node kinds: {len(serial_nodes)}")
    for item in serial_nodes:
        print(f" - {item['semantic_kind']}: count={item['count']} option-shapes={len(item['option_shapes'])}")
    print(f"Shareable result: {out_path.relative_to(ROOT)}")
    print("GET only; no GenFarmer state was modified.")
    print("=" * 76)
    return 0 if total_nodes else 1


if __name__ == "__main__":
    raise SystemExit(main())
