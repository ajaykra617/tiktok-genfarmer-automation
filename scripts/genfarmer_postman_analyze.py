#!/usr/bin/env python3
"""Analyze the official GenFarmer Postman collection without exposing secrets.

This tool is intentionally offline/read-only. It consumes a local copy of
``GenFarmer.postman_collection.json`` and emits a privacy-safe report containing:

- collection metadata (name/schema only);
- all request methods and normalized paths;
- query/header/auth *names* (never values);
- request/response JSON field/type shapes;
- collection variable names (never values);
- any real ``script.flow`` examples found in request/example bodies, reduced to
  privacy-safe node families, ``data.action`` values and option field/type shapes;
- endpoints present in the collection but not in the public GitBook baseline.

The raw Postman collection may contain IDs, example values or credentials. Keep it
under the git-ignored ``evidence/`` tree and share only the generated report.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

PUBLIC_BASELINE = {
    ("GET", "/backend/auth/me"),
    ("GET", "/automation/apps"),
    ("GET", "/automation/apps/:id"),
    ("PUT", "/automation/apps"),
    ("DELETE", "/automation/apps"),
    ("POST", "/automation/tasks"),
    ("PUT", "/automation/tasks/:id"),
    ("PUT", "/automation/tasks/:id/add-devices"),
    ("PUT", "/automation/tasks/:id/remove-devices"),
    ("DELETE", "/automation/tasks"),
    ("GET", "/automation/runs"),
    ("POST", "/automation/runs"),
    ("PUT", "/automation/runs/:id/run"),
    ("GET", "/automation/runs/:id/storages"),
}

SENSITIVE_NAME_RE = re.compile(
    r"(?i)(authorization|password|passwd|secret|token|cookie|credential|api[-_]?key|email|phone)"
)
SAFE_ACTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/-]{0,119}$")


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


def schema_paths(value: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            path = f"{prefix}.{key}" if prefix else key
            paths.add(f"{path}:{value_type(child)}")
            paths.update(schema_paths(child, path))
    elif isinstance(value, list):
        list_path = f"{prefix}[]" if prefix else "[]"
        for child in value[:50]:
            paths.add(f"{list_path}:{value_type(child)}")
            paths.update(schema_paths(child, list_path))
    return paths


def iter_items(items: Any, folders: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Mapping[str, Any]]]:
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, Mapping):
            continue
        children = item.get("item")
        name = str(item.get("name") or "<unnamed>")
        if isinstance(children, list):
            yield from iter_items(children, folders + (name,))
        elif isinstance(item.get("request"), Mapping):
            yield folders, item


def parse_raw_json(text: Any) -> Any | None:
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def body_json(body: Any) -> Any | None:
    if not isinstance(body, Mapping):
        return None
    mode = body.get("mode")
    if mode == "raw":
        return parse_raw_json(body.get("raw"))
    return None


def normalize_path(raw_url: Any) -> str:
    """Normalize Postman URL values to a host-free route path."""
    if isinstance(raw_url, Mapping):
        path = raw_url.get("path")
        if isinstance(path, list):
            parts = [str(x).strip("/") for x in path if str(x)]
            route = "/" + "/".join(parts)
        else:
            raw_url = raw_url.get("raw", "")
            route = normalize_path(raw_url)
            return route
    elif isinstance(raw_url, str):
        text = raw_url.strip()
        # Remove Postman variables such as {{baseUrl}} before parsing.
        text = re.sub(r"^\{\{[^}]+\}\}", "http://placeholder.invalid", text)
        parsed = urlparse(text if "://" in text else "http://placeholder.invalid/" + text.lstrip("/"))
        route = parsed.path or "/"
    else:
        return "/"

    route = re.sub(r"//+", "/", route)
    # Normalize concrete IDs to :id only when they appear after known resource segments.
    parts = route.split("/")
    for i in range(2, len(parts)):
        if parts[i - 1] in {"apps", "tasks", "runs"} and parts[i] not in {"add-devices", "remove-devices", "run", "storages"}:
            if parts[i] and not parts[i].startswith(":") and not parts[i].startswith("{{"):
                parts[i] = ":id"
    route = "/".join(parts)
    route = re.sub(r"\{\{[^}]+\}\}", ":id", route)
    return route or "/"


def names_from_key_value(items: Any) -> list[str]:
    names: set[str] = set()
    if isinstance(items, list):
        for item in items:
            if isinstance(item, Mapping):
                key = item.get("key")
                if isinstance(key, str) and key:
                    names.add(key)
    return sorted(names)


def auth_shape(auth: Any) -> dict[str, Any] | None:
    if not isinstance(auth, Mapping):
        return None
    auth_type = auth.get("type")
    result: dict[str, Any] = {"type": str(auth_type) if auth_type is not None else None}
    if isinstance(auth_type, str):
        result["field_names"] = names_from_key_value(auth.get(auth_type))
    return result


def find_flows(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        script = value.get("script")
        if isinstance(script, Mapping):
            flow = script.get("flow")
            if isinstance(flow, Mapping) and isinstance(flow.get("nodes"), list) and isinstance(flow.get("edges"), list):
                yield flow
        if isinstance(value.get("nodes"), list) and isinstance(value.get("edges"), list):
            yield value
        for child in value.values():
            yield from find_flows(child)
    elif isinstance(value, list):
        for child in value:
            yield from find_flows(child)


def flow_semantics(flow: Mapping[str, Any]) -> dict[str, Any]:
    node_counter: Counter[str] = Counter()
    option_shapes: dict[str, set[tuple[str, str]]] = {}
    edge_count = 0

    nodes = flow.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            family_raw = node.get("type")
            family = str(family_raw) if isinstance(family_raw, (str, int)) else "<unknown-family>"
            action = None
            data = node.get("data")
            if isinstance(data, Mapping):
                raw_action = data.get("action")
                if isinstance(raw_action, str) and SAFE_ACTION_RE.fullmatch(raw_action):
                    action = raw_action
            semantic = f"{family}:{action}" if action else family
            node_counter[semantic] += 1

            options: set[tuple[str, str]] = set()
            if isinstance(data, Mapping) and isinstance(data.get("options"), Mapping):
                options = {(str(k), value_type(v)) for k, v in data["options"].items()}
            option_shapes.setdefault(semantic, set()).update(options)

    edges = flow.get("edges")
    if isinstance(edges, list):
        edge_count = len(edges)

    return {
        "node_count": sum(node_counter.values()),
        "edge_count": edge_count,
        "semantic_nodes": [
            {
                "semantic_kind": kind,
                "count": count,
                "option_fields": [
                    {"name": name, "type": typ}
                    for name, typ in sorted(option_shapes.get(kind, set()))
                ],
            }
            for kind, count in sorted(node_counter.items())
        ],
    }


def response_bodies(item: Mapping[str, Any]) -> Iterable[Any]:
    responses = item.get("response")
    if not isinstance(responses, list):
        return
    for response in responses:
        if isinstance(response, Mapping):
            parsed = parse_raw_json(response.get("body"))
            if parsed is not None:
                yield parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze official GenFarmer Postman collection safely")
    parser.add_argument("collection", help="Path to GenFarmer.postman_collection.json")
    args = parser.parse_args()

    collection_path = Path(args.collection)
    try:
        collection = json.loads(collection_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read Postman collection: {exc}")
        return 2

    info = collection.get("info") if isinstance(collection, Mapping) else None
    collection_name = str(info.get("name")) if isinstance(info, Mapping) and info.get("name") else "<unknown>"
    schema = str(info.get("schema")) if isinstance(info, Mapping) and info.get("schema") else None

    variables = []
    for var in collection.get("variable", []) if isinstance(collection, Mapping) else []:
        if isinstance(var, Mapping) and isinstance(var.get("key"), str):
            variables.append(var["key"])

    requests: list[dict[str, Any]] = []
    endpoints: set[tuple[str, str]] = set()
    flow_examples: list[dict[str, Any]] = []

    for folders, item in iter_items(collection.get("item") if isinstance(collection, Mapping) else None):
        request = item["request"]
        method = str(request.get("method") or "GET").upper()
        path = normalize_path(request.get("url"))
        endpoints.add((method, path))

        url_obj = request.get("url")
        query_names = names_from_key_value(url_obj.get("query")) if isinstance(url_obj, Mapping) else []
        header_names = names_from_key_value(request.get("header"))
        parsed_body = body_json(request.get("body"))

        request_report = {
            "folder": list(folders),
            "name": str(item.get("name") or "<unnamed>"),
            "method": method,
            "path": path,
            "query_names": query_names,
            "header_names": header_names,
            "auth": auth_shape(request.get("auth")),
            "request_json_schema_paths": sorted(schema_paths(parsed_body)) if parsed_body is not None else [],
            "example_response_codes": sorted(
                {
                    int(resp.get("code"))
                    for resp in item.get("response", [])
                    if isinstance(resp, Mapping) and isinstance(resp.get("code"), int)
                }
            ),
        }

        response_shapes: set[str] = set()
        for parsed_response in response_bodies(item):
            response_shapes.update(schema_paths(parsed_response))
        request_report["response_json_schema_paths"] = sorted(response_shapes)
        requests.append(request_report)

        sources = []
        if parsed_body is not None:
            sources.append(("request", parsed_body))
        for parsed_response in response_bodies(item):
            sources.append(("response-example", parsed_response))
        for source_kind, payload in sources:
            for flow in find_flows(payload):
                flow_examples.append(
                    {
                        "request_method": method,
                        "request_path": path,
                        "source": source_kind,
                        **flow_semantics(flow),
                    }
                )

    collection_only = sorted(
        {endpoint for endpoint in endpoints if endpoint not in PUBLIC_BASELINE},
        key=lambda x: (x[1], x[0]),
    )
    baseline_missing = sorted(
        {endpoint for endpoint in PUBLIC_BASELINE if endpoint not in endpoints},
        key=lambda x: (x[1], x[0]),
    )

    report = {
        "report_format": 1,
        "privacy": "shareable Postman contract report: values removed; only names, paths, types, codes and safe flow action tokens retained",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "collection": {
            "name": collection_name,
            "schema": schema,
            "variable_names": sorted(set(variables)),
        },
        "request_count": len(requests),
        "unique_endpoint_count": len(endpoints),
        "requests": requests,
        "collection_only_endpoints_vs_public_gitbook_baseline": [
            {"method": method, "path": path} for method, path in collection_only
        ],
        "public_gitbook_baseline_missing_from_collection": [
            {"method": method, "path": path} for method, path in baseline_missing
        ],
        "script_flow_examples_found": flow_examples,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-postman-analysis-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "postman-contract.shareable.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 76)
    print("GENFARMER OFFICIAL POSTMAN COLLECTION ANALYSIS")
    print("=" * 76)
    print(f"Collection: {collection_name}")
    print(f"Requests: {len(requests)}")
    print(f"Unique endpoints: {len(endpoints)}")
    print(f"Collection-only endpoints vs public baseline: {len(collection_only)}")
    for method, path in collection_only:
        print(f" + {method:6s} {path}")
    print(f"Public baseline endpoints missing from collection: {len(baseline_missing)}")
    print(f"script.flow examples found: {len(flow_examples)}")
    for example in flow_examples:
        kinds = ", ".join(x["semantic_kind"] for x in example["semantic_nodes"])
        print(f" * {example['request_method']} {example['request_path']} [{example['source']}]: {kinds or '<empty flow>'}")
    print(f"Shareable result: {out_path.relative_to(ROOT)}")
    print("No request was sent to GenFarmer. Collection values were not copied to the report.")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
