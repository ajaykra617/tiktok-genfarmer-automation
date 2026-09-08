#!/usr/bin/env python3
"""Patch one learned private XPath into a GenFarmer ElementExists node.

The script never guesses undocumented option fields.  It accepts only an
ElementExists node whose existing options expose exactly one key normalized to
`xpath`; otherwise it fails closed and prints only available key names.
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


def action_of(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, Mapping):
        value = data.get("action")
        if isinstance(value, str) and value:
            return value
    return None


def normalized_key(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def xpath_option_key(options: Mapping[str, Any]) -> str:
    matches = [str(key) for key in options if normalized_key(str(key)) == "xpath"]
    if len(matches) != 1:
        keys = ", ".join(sorted(map(str, options.keys()))) or "<none>"
        raise GenFarmFileError(
            "ElementExists options do not expose exactly one verified XPath key; "
            f"available keys: {keys}"
        )
    return matches[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Patch a learned private XPath into ElementExists")
    ap.add_argument("input", type=Path, help="feed-anchor qualification .genfarm")
    ap.add_argument("candidates", type=Path, help="private candidates.private.json from tiktok_ui_xml_selector_probe.py")
    ap.add_argument("--candidate", type=int, default=1, help="1-based candidate index")
    ap.add_argument("--output", type=Path, required=True)
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
        options = data.get("options") if isinstance(data, Mapping) else None
        if not isinstance(options, dict):
            raise GenFarmFileError("ElementExists node has no mutable data.options object")
        key = xpath_option_key(options)

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
        target_data = target_nodes[0]["data"]
        target_data["options"][key] = xpath
        copied.save(args.output)

        print("=" * 78)
        print("GENFARM ELEMENTEXISTS XPATH PATCH")
        print("=" * 78)
        print(f"Input:          {args.input}")
        print(f"Candidate:      {args.candidate}")
        print(f"Selector kind:  {selected.get('kind', '<unknown>') if isinstance(selected, Mapping) else '<unknown>'}")
        print(f"XPath option:   {key}")
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
