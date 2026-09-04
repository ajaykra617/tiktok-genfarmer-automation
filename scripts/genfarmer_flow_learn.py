#!/usr/bin/env python3
"""Learn GenFarmer ``script.flow`` structure from existing Automation Apps.

Safety properties:
- GET requests only.
- No app/task/run is created, updated, deleted, or executed.
- Exact raw flows are written only under local git-ignored ``evidence/``.
- A separate shareable catalog contains structure/types, not selector/text values.

The goal is exhaustive, version-specific learning: observe real GenFarmer-generated
flows first, then build Python generators from verified node templates instead of
guessing undocumented node JSON.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.flow import FlowDocument, FlowError, find_flow, infer_node_kind  # noqa: E402
from genfarmer_automation.genfarmer_client import GenFarmerClient, GenFarmerError  # noqa: E402


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
            nested = data.get(key)
            found = discover_user_id(nested)
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
    """Extract likely app records without depending on the response envelope."""

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obj in iter_dicts(value):
        app_id = obj.get("id")
        if not isinstance(app_id, (str, int)):
            continue
        # Avoid treating arbitrary metadata objects as apps.
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


def schema_paths(value: Any, prefix: str = "") -> set[str]:
    """Describe structure recursively without retaining scalar values."""

    paths: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            key = str(key)
            path = f"{prefix}.{key}" if prefix else key
            paths.add(f"{path}:{value_type(child)}")
            paths.update(schema_paths(child, path))
    elif isinstance(value, list):
        list_path = f"{prefix}[]" if prefix else "[]"
        for child in value[:50]:
            paths.add(f"{list_path}:{value_type(child)}")
            paths.update(schema_paths(child, list_path))
    return paths


def structural_signature(value: Any) -> str:
    text = "\n".join(sorted(schema_paths(value)))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def short_app_name(record: Mapping[str, Any]) -> str:
    value = record.get("name")
    if isinstance(value, str) and value.strip():
        # Local console only. The shareable catalog does not contain app names.
        return value.strip()[:80]
    return "<unnamed>"


def build_catalog(app_flows: list[dict[str, Any]]) -> dict[str, Any]:
    kinds: dict[str, dict[str, Any]] = {}
    edge_variants: dict[str, dict[str, Any]] = {}
    total_nodes = 0
    total_edges = 0

    for item in app_flows:
        flow = item["flow"]
        for node in flow.get("nodes", []):
            if not isinstance(node, dict):
                continue
            total_nodes += 1
            kind, source = infer_node_kind(node)
            variant = structural_signature(node)
            entry = kinds.setdefault(
                kind,
                {
                    "kind": kind,
                    "kind_source_paths": Counter(),
                    "count": 0,
                    "variants": {},
                    "observed_app_count": 0,
                    "_apps": set(),
                },
            )
            entry["count"] += 1
            entry["kind_source_paths"][source] += 1
            entry["_apps"].add(item["app_id"])
            v = entry["variants"].setdefault(
                variant,
                {
                    "signature": variant,
                    "count": 0,
                    "schema_paths": set(),
                },
            )
            v["count"] += 1
            v["schema_paths"].update(schema_paths(node))

        for edge in flow.get("edges", []):
            if not isinstance(edge, dict):
                continue
            total_edges += 1
            variant = structural_signature(edge)
            v = edge_variants.setdefault(
                variant,
                {
                    "signature": variant,
                    "count": 0,
                    "schema_paths": set(),
                },
            )
            v["count"] += 1
            v["schema_paths"].update(schema_paths(edge))

    serializable_kinds: list[dict[str, Any]] = []
    for kind in sorted(kinds):
        entry = kinds[kind]
        serializable_kinds.append(
            {
                "kind": kind,
                "count": entry["count"],
                "observed_app_count": len(entry["_apps"]),
                "kind_source_paths": dict(sorted(entry["kind_source_paths"].items())),
                "variants": [
                    {
                        "signature": v["signature"],
                        "count": v["count"],
                        "schema_paths": sorted(v["schema_paths"]),
                    }
                    for _, v in sorted(entry["variants"].items())
                ],
            }
        )

    return {
        "catalog_format": 1,
        "privacy": "shareable structural catalog: no app names, selector values, text values, credentials, or raw node payloads",
        "apps_with_flows": len(app_flows),
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "distinct_node_kinds": len(serializable_kinds),
        "node_kinds": serializable_kinds,
        "edge_variants": [
            {
                "signature": v["signature"],
                "count": v["count"],
                "schema_paths": sorted(v["schema_paths"]),
            }
            for _, v in sorted(edge_variants.items())
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only learner for GenFarmer script.flow node/edge schemas")
    parser.add_argument("--app-id", action="append", default=[], help="Only inspect this app ID; repeatable")
    parser.add_argument("--limit", type=int, default=100, help="Apps per list request")
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    client = GenFarmerClient(base_url, timeout=12.0, allow_mutations=False)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = ROOT / "evidence" / f"genfarmer-flow-learn-{stamp}"
    private_dir = evidence_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 76)
    print("GENFARMER SCRIPT.FLOW READ-ONLY LEARNER")
    print("=" * 76)
    print(f"Base URL: {base_url}")
    print("HTTP methods: GET only")
    print(f"Evidence: {evidence_dir.relative_to(ROOT)}")

    try:
        me = client.get_current_user()
        user_id = discover_user_id(me)
    except GenFarmerError as exc:
        print(f"ERROR: cannot read current user: {exc}", file=sys.stderr)
        return 1

    print(f"Current user ID discovered: {user_id if user_id is not None else 'not found'}")

    requested_ids = {str(x) for x in args.app_id}
    app_records: dict[str, dict[str, Any]] = {}

    if requested_ids:
        for app_id in sorted(requested_ids):
            app_records[app_id] = {"id": app_id}
    else:
        for page in range(1, max(1, args.max_pages) + 1):
            try:
                payload = client.list_apps(user_id=user_id, page=page, limit=max(1, args.limit))
            except GenFarmerError as exc:
                print(f"ERROR listing apps page {page}: {exc}", file=sys.stderr)
                return 1
            records = extract_app_records(payload)
            new_count = 0
            for record in records:
                app_id = str(record["id"])
                if app_id not in app_records:
                    app_records[app_id] = record
                    new_count += 1
            print(f"List Apps page {page}: records={len(records)}, new={new_count}")
            if not records or new_count == 0 or len(records) < max(1, args.limit):
                break

    print(f"Unique Automation Apps to inspect: {len(app_records)}")

    exact_private: list[dict[str, Any]] = []
    app_flows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for index, (app_id, record) in enumerate(sorted(app_records.items()), start=1):
        name = short_app_name(record)
        try:
            detail = client.get_app(app_id)
            flow = find_flow(detail)
            if flow is None:
                print(f"[{index:03d}] {app_id} {name!r}: no script.flow")
                failures.append({"app_id": app_id, "reason": "no script.flow found"})
                continue

            doc = FlowDocument.from_flow(flow)
            warnings = doc.validate_basic()
            kinds = Counter(kind for kind, _, _ in doc.node_kinds())
            print(
                f"[{index:03d}] {app_id} {name!r}: "
                f"nodes={len(doc.nodes)} edges={len(doc.edges)} kinds={len(kinds)} warnings={len(warnings)}"
            )

            exact_private.append(
                {
                    "app_id": app_id,
                    "app_name": name,
                    "flow_sha256": doc.sha256(),
                    "flow": deepcopy(flow),
                    "warnings": warnings,
                }
            )
            app_flows.append({"app_id": app_id, "flow": deepcopy(flow)})
        except (GenFarmerError, FlowError) as exc:
            print(f"[{index:03d}] {app_id} {name!r}: ERROR {exc}")
            failures.append({"app_id": app_id, "reason": str(exc)})

    catalog = build_catalog(app_flows)
    catalog.update(
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "genfarmer_base_url_redacted": "localhost-local-api",
            "apps_requested": len(app_records),
            "failures": failures,
        }
    )

    private_path = private_dir / "app-flows.raw.json"
    private_path.write_text(json.dumps(exact_private, ensure_ascii=False, indent=2), encoding="utf-8")

    catalog_path = evidence_dir / "flow-catalog.shareable.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")

    print("-" * 76)
    print(f"Apps with usable flows: {catalog['apps_with_flows']}")
    print(f"Observed nodes: {catalog['total_nodes']}")
    print(f"Observed edges: {catalog['total_edges']}")
    print(f"Distinct node kinds: {catalog['distinct_node_kinds']}")
    print("Observed node kinds:")
    for item in catalog["node_kinds"]:
        print(
            f" - {item['kind']}: count={item['count']} "
            f"apps={item['observed_app_count']} variants={len(item['variants'])}"
        )

    print("\nLOCAL PRIVATE exact-flow corpus (do not share/commit):")
    print(f"  {private_path.relative_to(ROOT)}")
    print("SHAREABLE structural catalog (safe to upload here):")
    print(f"  {catalog_path.relative_to(ROOT)}")
    print("No GenFarmer state was modified.")
    print("=" * 76)
    return 0 if app_flows else 1


if __name__ == "__main__":
    raise SystemExit(main())
