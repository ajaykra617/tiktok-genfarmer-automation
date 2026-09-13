#!/usr/bin/env python3
"""Patch one learned private XPath into a GenFarmer ElementExists node.

The script never invents undocumented fields. It first searches the captured
ElementExists ``data`` structure recursively for exactly one existing key that
normalizes to ``xpath``. If an empty GenFarmer template omits the selector field,
a one-time configured schema-probe export can be used instead: place the known
sentinel XPath in GenFarmer, export it, then this script locates that exact
scalar value and replaces only that already-serialized field.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.genfarm_file import GenFarmDocument, GenFarmFileError  # noqa: E402
from genfarmer_automation.structure_paths import (  # noqa: E402
    find_key_paths,
    find_scalar_value_paths,
    set_existing_path,
)

DEFAULT_SCHEMA_SENTINEL = "//*[@resource-id='__GF_SCHEMA_PROBE__']"


def action_of(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, Mapping):
        value = data.get("action")
        if isinstance(value, str) and value:
            return value
    return None


def printable_path(path: tuple[str | int, ...]) -> str:
    out = "$"
    for part in path:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}"
    return out


def resolve_xpath_path(data: dict[str, Any], sentinel: str) -> tuple[tuple[str | int, ...], str]:
    """Resolve one already-serialized XPath field without guessing schema."""
    xpath_paths = find_key_paths(data, "xpath")
    if len(xpath_paths) == 1:
        return xpath_paths[0], "verified XPath key"
    if len(xpath_paths) > 1:
        visible = ", ".join(printable_path(path) for path in xpath_paths)
        raise GenFarmFileError(
            "ElementExists captured data exposes multiple XPath keys; refusing ambiguous patch: " + visible
        )

    sentinel_paths = find_scalar_value_paths(data, sentinel)
    if len(sentinel_paths) == 1:
        return sentinel_paths[0], "exact schema-probe sentinel"
    if len(sentinel_paths) > 1:
        visible = ", ".join(printable_path(path) for path in sentinel_paths)
        raise GenFarmFileError(
            "schema-probe sentinel appears in multiple ElementExists fields; refusing ambiguous patch: " + visible
        )
    raise GenFarmFileError(
        "ElementExists captured data contains neither one existing XPath key nor the schema-probe sentinel. "
        "Use a GenFarmer export where the ElementExists XPath field was saved with the exact schema-probe sentinel."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Patch a learned private XPath into ElementExists")
    ap.add_argument("input", type=Path, help="configured feed-anchor .genfarm export")
    ap.add_argument("candidates", type=Path, help="private candidate/ranked-candidate JSON")
    ap.add_argument("--candidate", type=int, default=1, help="1-based candidate index")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument(
        "--sentinel",
        default=DEFAULT_SCHEMA_SENTINEL,
        help="exact one-time schema-probe XPath value used in GenFarmer when an empty template omits the field",
    )
    args = ap.parse_args()
    if args.candidate < 1:
        print("ERROR: --candidate must be >= 1", file=sys.stderr)
        return 2

    try:
        doc = GenFarmDocument.load(args.input)
        nodes = [
            node for node in doc.flow.nodes
            if isinstance(node, Mapping) and action_of(node) == "ElementExists"
        ]
        if len(nodes) != 1:
            raise GenFarmFileError(f"expected exactly one ElementExists node; found {len(nodes)}")
        node = nodes[0]
        data = node.get("data")
        if not isinstance(data, dict):
            raise GenFarmFileError("ElementExists node has no mutable data object")

        xpath_path, resolution_basis = resolve_xpath_path(data, args.sentinel)

        raw_candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
        if not isinstance(raw_candidates, list) or len(raw_candidates) < args.candidate:
            raise GenFarmFileError("candidate file does not contain the requested selector")
        selected = raw_candidates[args.candidate - 1]
        xpath = selected.get("xpath") if isinstance(selected, Mapping) else None
        if not isinstance(xpath, str) or not xpath.strip():
            raise GenFarmFileError("selected candidate has no XPath string")

        payload = doc.to_dict()
        copied = GenFarmDocument(deepcopy(payload))
        target_nodes = [
            n for n in copied.flow.nodes
            if isinstance(n, Mapping) and action_of(n) == "ElementExists"
        ]
        target_data = target_nodes[0].get("data")
        if not isinstance(target_data, dict):
            raise GenFarmFileError("copied ElementExists node has no mutable data object")
        set_existing_path(target_data, xpath_path, xpath)
        copied.save(args.output)

        print("=" * 78)
        print("GENFARM ELEMENTEXISTS XPATH PATCH")
        print("=" * 78)
        print(f"Input:          {args.input}")
        print(f"Candidate:      {args.candidate}")
        print(f"Selector kind:  {selected.get('kind', '<unknown>') if isinstance(selected, Mapping) else '<unknown>'}")
        print(f"XPath field:    {printable_path(xpath_path)}")
        print(f"Resolved by:    {resolution_basis}")
        print(f"Output:         {args.output}")
        print("XPath value intentionally not printed; exact value remains local/private.")
        print("Next: use genfarm_apply_to_app.py dry-run, then --apply after review.")
        print("=" * 78)
        return 0
    except (GenFarmFileError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
