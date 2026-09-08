#!/usr/bin/env python3
"""Extract one configured node's data.options from a local .genfarm file.

The output is intended to remain local/private and be fed back into compiler
scripts such as genfarm_build_tiktok_warmup.py. It is not automatically added
to Git.
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
        action = data.get("action")
        if isinstance(action, str) and action:
            return action
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract one configured GenFarmer node's data.options JSON")
    ap.add_argument("path", type=Path)
    ap.add_argument("--action", required=True)
    ap.add_argument("--index", type=int, default=1, help="1-based occurrence of the action; default: 1")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    if args.index < 1:
        print("ERROR: --index must be >= 1", file=sys.stderr)
        return 2

    try:
        doc = GenFarmDocument.load(args.path)
        matches = [
            node for node in doc.flow.nodes
            if isinstance(node, Mapping) and action_of(node) == args.action
        ]
        if len(matches) < args.index:
            raise GenFarmFileError(
                f"requested {args.action} occurrence {args.index}, but file contains {len(matches)}"
            )
        node = matches[args.index - 1]
        data = node.get("data")
        options = data.get("options") if isinstance(data, Mapping) else None
        if not isinstance(options, Mapping):
            raise GenFarmFileError(f"selected {args.action} node has no data.options object")
        payload = deepcopy(dict(options))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        print("=" * 78)
        print("GENFARM ACTION OPTIONS EXTRACT")
        print("=" * 78)
        print(f"File:   {args.path}")
        print(f"Action: {args.action}")
        print(f"Index:  {args.index}")
        print(f"Keys:   {', '.join(sorted(map(str, payload.keys()))) or '<none>'}")
        print(f"Output: {args.output}")
        print("Treat the output as local/private configuration; do not commit account- or selector-specific values.")
        print("=" * 78)
        return 0
    except (GenFarmFileError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
