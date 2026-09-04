#!/usr/bin/env python3
"""Produce a privacy-safe diff between two exact GenFarmer flow snapshots.

Use with ``scripts/genfarmer_flow_snapshot.py`` before and after changing exactly
one field in the GenFarmer UI. Raw values are shown only for a small allowlist of
internal enum/timing/boolean paths; text/selectors/commands and other strings are
masked with type/length/hash information.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,120}$")
SAFE_VALUE_SUFFIXES = (
    ".type",
    ".sourcePosition",
    ".targetPosition",
    ".data.action",
    ".data.options.breakpoint",
    ".data.options.disabled",
    ".data.options.timeoutType",
    ".data.options.timeout",
    ".data.options.timeoutFrom",
    ".data.options.timeoutTo",
    ".data.options.nodeSleep",
    ".data.options.nodeTimeout",
    ".data.options.timeoutAdbReconnect",
    ".data.options.timeoutNextNode",
    ".animated",
    ".updatable",
    ".sourceHandle",
    ".targetHandle",
    ".data.sourceHandle",
    ".data.targetHandle",
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def display_value(path: str, value: Any) -> Any:
    safe_path = any(path.endswith(suffix) for suffix in SAFE_VALUE_SUFFIXES)
    if value is None or isinstance(value, (bool, int, float)):
        return value if safe_path else {"type": type(value).__name__}
    if isinstance(value, str):
        if safe_path and SAFE_TOKEN_RE.fullmatch(value):
            return value
        return {"type": "str", "length": len(value), "sha256_10": digest(value)}
    if isinstance(value, list):
        return {"type": "list", "length": len(value)}
    if isinstance(value, dict):
        return {"type": "object", "keys": sorted(map(str, value.keys()))}
    return {"type": type(value).__name__}


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, Mapping):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(child, (dict, list)):
                out.update(flatten(child, path))
            else:
                out[path] = child
    elif isinstance(value, list):
        for i, child in enumerate(value):
            path = f"{prefix}[{i}]"
            if isinstance(child, (dict, list)):
                out.update(flatten(child, path))
            else:
                out[path] = child
    return out


def node_map(flow: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for node in flow.get("nodes", []):
        if isinstance(node, Mapping) and isinstance(node.get("id"), (str, int)):
            out[str(node["id"])] = node
    return out


def edge_map(flow: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for edge in flow.get("edges", []):
        if isinstance(edge, Mapping) and isinstance(edge.get("id"), (str, int)):
            out[str(edge["id"])] = edge
    return out


def compare_object(kind: str, obj_id: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    a = flatten(before, f"{kind}[{obj_id}]")
    b = flatten(after, f"{kind}[{obj_id}]")
    changes: list[dict[str, Any]] = []
    for path in sorted(set(a) | set(b)):
        av = a.get(path, "<missing>")
        bv = b.get(path, "<missing>")
        if av == bv:
            continue
        changes.append(
            {
                "path": path,
                "before": "<missing>" if av == "<missing>" else display_value(path, av),
                "after": "<missing>" if bv == "<missing>" else display_value(path, bv),
            }
        )
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Privacy-safe before/after diff for exact GenFarmer flow snapshots")
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise SystemExit("Both inputs must be flow JSON objects")

    before_nodes = node_map(before)
    after_nodes = node_map(after)
    before_edges = edge_map(before)
    after_edges = edge_map(after)

    report: dict[str, Any] = {
        "privacy": "shareable differential report; user-entered strings are masked",
        "nodes_added": sorted(set(after_nodes) - set(before_nodes)),
        "nodes_removed": sorted(set(before_nodes) - set(after_nodes)),
        "edges_added": sorted(set(after_edges) - set(before_edges)),
        "edges_removed": sorted(set(before_edges) - set(after_edges)),
        "node_changes": [],
        "edge_changes": [],
    }

    for obj_id in sorted(set(before_nodes) & set(after_nodes)):
        changes = compare_object("node", obj_id, before_nodes[obj_id], after_nodes[obj_id])
        if changes:
            report["node_changes"].append({"id_hash": digest(obj_id), "changes": changes})

    for obj_id in sorted(set(before_edges) & set(after_edges)):
        changes = compare_object("edge", obj_id, before_edges[obj_id], after_edges[obj_id])
        if changes:
            report["edge_changes"].append({"id_hash": digest(obj_id), "changes": changes})

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote shareable diff: {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
