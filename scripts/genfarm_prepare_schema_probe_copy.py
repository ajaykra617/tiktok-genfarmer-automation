#!/usr/bin/env python3
"""Prepare an isolated GenFarmer import copy for ElementExists schema probing.

This helper avoids editing an ambiguous/live GenFarmer app just to learn how an
empty XPath field is serialized. It loads an already-exported feed-anchor lab
app, validates that it contains exactly one ElementExists node, clears the
known export identity/timestamp fields, assigns a unique lab name, and writes a
new .genfarm file for manual Import App.

No selector field is invented or changed. The imported copy should only be used
to enter the harmless schema-probe sentinel in GenFarmer's XPath editor, save,
and export again.
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

DEFAULT_NAME = "GF Lab - TikTok Feed Anchor SCHEMA PROBE"


def action_of(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, Mapping):
        value = data.get("action")
        if isinstance(value, str) and value:
            return value
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare an isolated GenFarmer schema-probe import copy")
    ap.add_argument("input", type=Path, help="existing feed-anchor qualification .genfarm export")
    ap.add_argument("--output", type=Path, required=True, help="new identity-cleared import copy")
    ap.add_argument("--name", default=DEFAULT_NAME, help="unique GenFarmer app name for the imported copy")
    args = ap.parse_args()

    try:
        doc = GenFarmDocument.load(args.input)
        nodes = [
            node
            for node in doc.flow.nodes
            if isinstance(node, Mapping) and action_of(node) == "ElementExists"
        ]
        if len(nodes) != 1:
            raise GenFarmFileError(f"expected exactly one ElementExists node; found {len(nodes)}")

        copy_doc = GenFarmDocument(doc.to_dict())
        copy_doc.clear_identity_for_copy()
        copy_doc.patch_metadata({"name": args.name})
        copy_doc.save(args.output)

        print("=" * 78)
        print("GENFARM ELEMENTEXISTS SCHEMA-PROBE IMPORT COPY")
        print("=" * 78)
        print(f"Input:              {args.input}")
        print(f"Output:             {args.output}")
        print(f"Import app name:    {args.name}")
        print("ElementExists:      exactly 1")
        print("Known identity:     CLEARED FOR COPY")
        print("Selector/schema:    UNCHANGED")
        print("Next: use GenFarmer 'Import App' with the output file.")
        print("Safety: if GenFarmer offers to overwrite/replace an existing app, CANCEL instead of accepting.")
        print("After import, edit only the ElementExists XPath field with the schema-probe sentinel, save, and export.")
        print("=" * 78)
        return 0
    except (GenFarmFileError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
