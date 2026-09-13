#!/usr/bin/env python3
"""Print ElementExists structure paths without printing private scalar values.

Useful when a captured GenFarmer palette template does not expose an obvious
XPath field where expected. This probe is read-only and prints only JSON paths,
container sizes, and scalar types for the single ElementExists node.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.genfarm_file import GenFarmDocument, GenFarmFileError  # noqa: E402
from genfarmer_automation.structure_paths import find_key_paths, structure_paths  # noqa: E402


def action_of(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, Mapping):
        value = data.get("action")
        if isinstance(value, str) and value:
            return value
    return None


def printable(path: tuple[str | int, ...]) -> str:
    out = "$"
    for part in path:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only structural probe for one GenFarmer ElementExists node")
    ap.add_argument("input", type=Path)
    ap.add_argument("--max-depth", type=int, default=8)
    args = ap.parse_args()
    if not 1 <= args.max_depth <= 16:
        print("ERROR: --max-depth must be 1..16", file=sys.stderr)
        return 2

    try:
        doc = GenFarmDocument.load(args.input)
        nodes = [n for n in doc.flow.nodes if isinstance(n, Mapping) and action_of(n) == "ElementExists"]
        if len(nodes) != 1:
            raise GenFarmFileError(f"expected exactly one ElementExists node; found {len(nodes)}")
        data = nodes[0].get("data")
        if not isinstance(data, Mapping):
            raise GenFarmFileError("ElementExists node has no data object")

        xpath_paths = find_key_paths(data, "xpath")
        print("=" * 78)
        print("GENFARM ELEMENTEXISTS STRUCTURE PROBE")
        print("=" * 78)
        print(f"Input: {args.input}")
        print(f"Exact XPath-key paths found: {len(xpath_paths)}")
        for path in xpath_paths:
            print(f"XPath key path: {printable(path)}")
        print("------------------------------------------------------------------------------")
        print("ElementExists data structure (paths/types only; scalar values hidden):")
        for row in structure_paths(data, max_depth=args.max_depth):
            print(row)
        print("------------------------------------------------------------------------------")
        print("No file or GenFarmer state was modified.")
        print("=" * 78)
        return 0
    except (GenFarmFileError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
