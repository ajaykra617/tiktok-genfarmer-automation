#!/usr/bin/env python3
"""Analyze GenFarmer script.flow routing semantics from the local private corpus.

This tool reads the exact raw corpus produced by ``genfarmer_flow_learn.py`` but
emits only aggregate routing metadata. It never writes raw node IDs, labels,
selectors, commands, app names, or user-entered values to the shareable output.

The immediate goal is to prove relationships such as:

- whether ``data.successNode`` equals an outgoing edge target;
- whether ``data.failNode`` equals a failure-edge target when present;
- which source/target handles are used by each semantic node kind;
- whether Start uses a generated source handle while normal actions use
  ``successNode``.

No GenFarmer API request is made and no GenFarmer state is modified.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.flow_registry import semantic_kind  # noqa: E402


def newest_private_corpus() -> Path | None:
    candidates = list(
        (ROOT / "evidence").glob("genfarmer-flow-learn-*/private/app-flows.raw.json")
    )
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def scalar_id(value: Any) -> str | None:
    if isinstance(value, (str, int)):
        return str(value)
    return None


def counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Privacy-safe routing analyzer for a local GenFarmer raw-flow corpus"
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        help="Path to private app-flows.raw.json; defaults to newest local learner corpus",
    )
    args = parser.parse_args()

    corpus_path = args.corpus or newest_private_corpus()
    if corpus_path is None:
        print(
            "ERROR: no private flow corpus found. Run python scripts/genfarmer_flow_learn.py first.",
            file=sys.stderr,
        )
        return 2
    if not corpus_path.is_absolute():
        corpus_path = (ROOT / corpus_path).resolve()

    try:
        payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read corpus: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, list):
        print("ERROR: raw corpus must be a list", file=sys.stderr)
        return 2

    by_kind: dict[str, dict[str, Any]] = {}
    edge_patterns: Counter[str] = Counter()
    total_nodes = 0
    total_edges = 0
    total_success_pointers = 0
    total_success_matches = 0
    total_fail_pointers = 0
    total_fail_matches = 0
    apps_with_flows = 0

    for app in payload:
        if not isinstance(app, Mapping):
            continue
        flow = app.get("flow")
        if not isinstance(flow, Mapping):
            continue
        nodes = flow.get("nodes")
        edges = flow.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            continue
        apps_with_flows += 1

        node_by_id: dict[str, Mapping[str, Any]] = {}
        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            node_id = scalar_id(node.get("id"))
            if node_id is not None:
                node_by_id[node_id] = node

        normalized_edges: list[Mapping[str, Any]] = [
            edge for edge in edges if isinstance(edge, Mapping)
        ]
        total_edges += len(normalized_edges)

        for edge in normalized_edges:
            source_id = scalar_id(edge.get("source"))
            source_handle = edge.get("sourceHandle")
            target_handle = edge.get("targetHandle")
            source_node = node_by_id.get(source_id or "")
            source_kind = semantic_kind(source_node) if source_node is not None else "<unknown>"
            source_token = str(source_handle) if isinstance(source_handle, (str, int)) else "<none>"
            target_token = str(target_handle) if isinstance(target_handle, (str, int)) else "<none>"
            # Deliberately do not include target semantic kind: preserving only handle behavior
            # avoids exposing the app's actual business-logic sequence.
            edge_patterns[
                json.dumps(
                    {
                        "source_semantic_kind": source_kind,
                        "source_handle": source_token,
                        "target_handle": target_token,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ] += 1

        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            node_id = scalar_id(node.get("id"))
            if node_id is None:
                continue
            total_nodes += 1
            kind = semantic_kind(node)
            entry = by_kind.setdefault(
                kind,
                {
                    "semantic_kind": kind,
                    "node_count": 0,
                    "success_pointer_present": 0,
                    "success_pointer_null": 0,
                    "success_pointer_target_match": 0,
                    "success_pointer_target_mismatch": 0,
                    "fail_pointer_present": 0,
                    "fail_pointer_null": 0,
                    "fail_pointer_target_match": 0,
                    "fail_pointer_target_mismatch": 0,
                    "outgoing_edge_counts": Counter(),
                    "outgoing_source_handles": Counter(),
                    "outgoing_target_handles": Counter(),
                },
            )
            entry["node_count"] += 1

            outgoing = [
                edge for edge in normalized_edges if scalar_id(edge.get("source")) == node_id
            ]
            entry["outgoing_edge_counts"][str(len(outgoing))] += 1
            for edge in outgoing:
                source_handle = edge.get("sourceHandle")
                target_handle = edge.get("targetHandle")
                entry["outgoing_source_handles"][
                    str(source_handle) if isinstance(source_handle, (str, int)) else "<none>"
                ] += 1
                entry["outgoing_target_handles"][
                    str(target_handle) if isinstance(target_handle, (str, int)) else "<none>"
                ] += 1

            data = node.get("data")
            if not isinstance(data, Mapping):
                data = {}

            success_id = scalar_id(data.get("successNode"))
            if success_id is None:
                entry["success_pointer_null"] += 1
            else:
                entry["success_pointer_present"] += 1
                total_success_pointers += 1
                any_target_match = any(
                    scalar_id(edge.get("target")) == success_id for edge in outgoing
                )
                if any_target_match:
                    entry["success_pointer_target_match"] += 1
                    total_success_matches += 1
                else:
                    entry["success_pointer_target_mismatch"] += 1

            fail_id = scalar_id(data.get("failNode"))
            if fail_id is None:
                entry["fail_pointer_null"] += 1
            else:
                entry["fail_pointer_present"] += 1
                total_fail_pointers += 1
                any_target_match = any(
                    scalar_id(edge.get("target")) == fail_id for edge in outgoing
                )
                if any_target_match:
                    entry["fail_pointer_target_match"] += 1
                    total_fail_matches += 1
                else:
                    entry["fail_pointer_target_mismatch"] += 1

    serial_kinds: list[dict[str, Any]] = []
    for kind in sorted(by_kind):
        entry = by_kind[kind]
        serial_kinds.append(
            {
                "semantic_kind": kind,
                "node_count": entry["node_count"],
                "success_pointer_present": entry["success_pointer_present"],
                "success_pointer_null": entry["success_pointer_null"],
                "success_pointer_target_match": entry["success_pointer_target_match"],
                "success_pointer_target_mismatch": entry["success_pointer_target_mismatch"],
                "fail_pointer_present": entry["fail_pointer_present"],
                "fail_pointer_null": entry["fail_pointer_null"],
                "fail_pointer_target_match": entry["fail_pointer_target_match"],
                "fail_pointer_target_mismatch": entry["fail_pointer_target_mismatch"],
                "outgoing_edge_counts": counter_dict(entry["outgoing_edge_counts"]),
                "outgoing_source_handles": counter_dict(entry["outgoing_source_handles"]),
                "outgoing_target_handles": counter_dict(entry["outgoing_target_handles"]),
            }
        )

    output = {
        "catalog_format": 1,
        "privacy": "shareable aggregate routing semantics; no node IDs, app names, selectors, commands, labels, or flow sequence targets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "apps_with_flows": apps_with_flows,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "success_pointer_summary": {
            "present": total_success_pointers,
            "matching_outgoing_edge_target": total_success_matches,
            "all_present_pointers_match_an_outgoing_edge_target": (
                total_success_pointers > 0 and total_success_pointers == total_success_matches
            ),
        },
        "fail_pointer_summary": {
            "present": total_fail_pointers,
            "matching_outgoing_edge_target": total_fail_matches,
            "all_present_pointers_match_an_outgoing_edge_target": (
                total_fail_pointers > 0 and total_fail_pointers == total_fail_matches
            ),
        },
        "semantic_kinds": serial_kinds,
        "edge_handle_patterns": [
            {**json.loads(encoded), "count": count}
            for encoded, count in sorted(edge_patterns.items())
        ],
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-flow-route-analysis-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "flow-routing.shareable.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 76)
    print("GENFARMER SCRIPT.FLOW ROUTING ANALYSIS")
    print("=" * 76)
    print(f"Private corpus: {corpus_path}")
    print(f"Apps with flows: {apps_with_flows}")
    print(f"Nodes analyzed: {total_nodes}")
    print(f"Edges analyzed: {total_edges}")
    print(
        "successNode pointers matching an outgoing edge target: "
        f"{total_success_matches}/{total_success_pointers}"
    )
    print(
        "failNode pointers matching an outgoing edge target: "
        f"{total_fail_matches}/{total_fail_pointers}"
    )
    print(f"Shareable result: {out_path.relative_to(ROOT)}")
    print("No GenFarmer API request was made. No GenFarmer state was modified.")
    print("=" * 76)
    return 0 if total_nodes else 1


if __name__ == "__main__":
    raise SystemExit(main())
