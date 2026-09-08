#!/usr/bin/env python3
"""Privacy-conscious structural inspector for a local .genfarm export."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.genfarm_file import GenFarmDocument, GenFarmFileError  # noqa: E402


def action_of(node: Mapping[str, object]) -> str:
    data = node.get("data")
    if isinstance(data, Mapping):
        action = data.get("action")
        if isinstance(action, str) and action:
            return action
    family = node.get("type")
    return f"<{family}>" if isinstance(family, str) else "<unknown>"


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect a GenFarmer .genfarm export without printing private option values")
    ap.add_argument("path")
    args = ap.parse_args()

    try:
        doc = GenFarmDocument.load(args.path)
        flow = doc.flow
    except GenFarmFileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    counts: Counter[str] = Counter()
    id_to_action: dict[str, str] = {}
    option_keys: dict[str, set[str]] = {}
    for node in flow.nodes:
        if not isinstance(node, Mapping):
            continue
        action = action_of(node)
        counts[action] += 1
        node_id = node.get("id")
        if isinstance(node_id, (str, int)):
            id_to_action[str(node_id)] = action
        data = node.get("data")
        if isinstance(data, Mapping):
            options = data.get("options")
            if isinstance(options, Mapping):
                option_keys.setdefault(action, set()).update(map(str, options.keys()))

    print("=" * 78)
    print("GENFARM EXPORT STRUCTURE")
    print("=" * 78)
    print(f"File: {Path(args.path).name}")
    print(f"Nodes: {len(flow.nodes)}")
    print(f"Edges: {len(flow.edges)}")
    print("Actions:")
    for action, count in sorted(counts.items()):
        keys = ", ".join(sorted(option_keys.get(action, set()))) or "<none>"
        print(f" - {action}: {count} | option keys: {keys}")
    print("Routing:")
    for edge in flow.edges:
        if not isinstance(edge, Mapping):
            continue
        source = edge.get("source")
        target = edge.get("target")
        if isinstance(source, (str, int)) and isinstance(target, (str, int)):
            print(f" - {id_to_action.get(str(source), '<unknown>')} -> {id_to_action.get(str(target), '<unknown>')}")
    warnings = flow.validate_basic()
    print(f"Graph warnings: {len(warnings)}")
    for warning in warnings:
        print(f" - {warning}")
    print("Privacy: scalar option values and app/account identifiers are not printed.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
