#!/usr/bin/env python3
"""Capture one configured GenFarmer action without exposing selector values.

The configured node's exact ``data.options`` is written only to the requested
local output path (normally under ignored evidence/private).  Console output
reports key names and changed JSON paths relative to the exact captured palette
template, never scalar values.  This lets us prove that GenFarmer serialized a
real configuration without committing private selectors.
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

from genfarm_build_tiktok_warmup import latest_template_flow, resolve_kind  # noqa: E402
from genfarmer_automation.flow_registry import TemplateRegistry, TemplateRegistryError  # noqa: E402
from genfarmer_automation.genfarm_file import GenFarmDocument, GenFarmFileError  # noqa: E402


def action_of(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, Mapping):
        value = data.get("action")
        if isinstance(value, str) and value:
            return value
    return None


def options_of(node: Mapping[str, Any]) -> dict[str, Any]:
    data = node.get("data")
    options = data.get("options") if isinstance(data, Mapping) else None
    if not isinstance(options, Mapping):
        raise GenFarmFileError("selected action node has no data.options object")
    return deepcopy(dict(options))


def diff_paths(a: Any, b: Any, path: str = "$") -> list[str]:
    out: list[str] = []
    if type(a) is not type(b):
        return [f"{path} [type]"]
    if isinstance(a, Mapping):
        keys = sorted(set(map(str, a.keys())) | set(map(str, b.keys())))
        for key in keys:
            if key not in a or key not in b:
                out.append(f"{path}.{key} [missing]")
            else:
                out.extend(diff_paths(a[key], b[key], f"{path}.{key}"))
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path} [length]")
        for index, (left, right) in enumerate(zip(a, b)):
            out.extend(diff_paths(left, right, f"{path}[{index}]"))
        return out
    if a != b:
        out.append(path)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture one configured GenFarmer action options object privately")
    ap.add_argument("path", type=Path, help="configured/exported .genfarm file")
    ap.add_argument("--action", required=True)
    ap.add_argument("--index", type=int, default=1)
    ap.add_argument("--template-flow", type=Path, help="exact private flow.raw.json; defaults to latest capture")
    ap.add_argument("--output", type=Path, required=True, help="private exact options JSON output")
    ap.add_argument("--require-change", action="store_true", help="fail if configured options equal the raw palette template")
    args = ap.parse_args()
    if args.index < 1:
        print("ERROR: --index must be >= 1", file=sys.stderr)
        return 2

    try:
        doc = GenFarmDocument.load(args.path)
        matches = [node for node in doc.flow.nodes if isinstance(node, Mapping) and action_of(node) == args.action]
        if len(matches) < args.index:
            raise GenFarmFileError(
                f"requested {args.action} occurrence {args.index}, but file contains {len(matches)}"
            )
        configured = options_of(matches[args.index - 1])

        template_path = args.template_flow or latest_template_flow()
        registry = TemplateRegistry.from_raw_corpus(template_path)
        kind = resolve_kind(registry, args.action)
        baseline_node = registry.clone(kind, new_id="structural-baseline")
        baseline = options_of(baseline_node)
        changed = diff_paths(baseline, configured)
        if args.require_change and not changed:
            raise GenFarmFileError(
                f"{args.action} options are identical to the raw palette template; GenFarmer configuration change was not proven"
            )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(configured, ensure_ascii=False, indent=2), encoding="utf-8")

        print("=" * 78)
        print("GENFARM CONFIGURED ACTION CAPTURE")
        print("=" * 78)
        print(f"File:          {args.path}")
        print(f"Action:        {args.action}")
        print(f"Index:         {args.index}")
        print(f"Option keys:   {', '.join(sorted(map(str, configured.keys()))) or '<none>'}")
        print(f"Changed paths: {len(changed)}")
        for item in changed[:25]:
            print(f" - {item}")
        if len(changed) > 25:
            print(f" - ... {len(changed) - 25} more paths hidden")
        print(f"Private output: {args.output}")
        print("Values intentionally not printed. Keep this file local/ignored.")
        print("=" * 78)
        return 0
    except (GenFarmFileError, TemplateRegistryError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
