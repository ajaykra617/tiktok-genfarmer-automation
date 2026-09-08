#!/usr/bin/env python3
"""Compile a one-time TikTok feed-anchor selector qualification app.

Runtime route:
    Start -> StartApp -> Pause -> ElementExists -> Screenshot -> Stop

The ElementExists node is cloned from the exact locally captured GenFarmer
palette template.  This script deliberately does not invent selector option
fields.  Open the generated file in GenFarmer, configure that one node with the
native inspector against a stable feed-specific element, save/export, then
extract its exact ``data.options`` into ignored local evidence.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarm_build_tiktok_warmup import (  # noqa: E402
    BuildError,
    HELPER_ACTIONS,
    TIKTOK_PACKAGE,
    action_of,
    clone_with_new_id,
    edge_templates,
    latest_template_flow,
    new_id,
    node_by_action,
    package_from,
    patch_options,
    reset_route,
    resolve_kind,
    retarget_edge,
    set_position,
)
from genfarmer_automation.feed_anchor import validate_feed_anchor_lab_flow  # noqa: E402
from genfarmer_automation.flow import FlowDocument  # noqa: E402
from genfarmer_automation.flow_registry import TemplateRegistry, TemplateRegistryError  # noqa: E402
from genfarmer_automation.genfarm_file import GenFarmDocument, GenFarmFileError  # noqa: E402

DEFAULT_NAME = "GF Lab - TikTok Feed Anchor Qualification"


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile one-time TikTok ElementExists selector qualification flow")
    ap.add_argument("base", type=Path, help="known-good TikTok .genfarm lifecycle export")
    ap.add_argument("--output", type=Path, help="output .genfarm path")
    ap.add_argument("--name", default=DEFAULT_NAME)
    ap.add_argument("--startup-pause", type=int, default=2)
    ap.add_argument("--template-flow", type=Path, help="private exact flow.raw.json; defaults to latest capture")
    args = ap.parse_args()

    if not 1 <= args.startup_pause <= 60:
        print("ERROR: --startup-pause must be 1..60 seconds", file=sys.stderr)
        return 2

    try:
        base_doc = GenFarmDocument.load(args.base)
        base_flow = base_doc.flow
        start = node_by_action(base_flow, "Start")
        start_app = node_by_action(base_flow, "StartApp")
        pause_template = node_by_action(base_flow, "Pause")
        screenshot = node_by_action(base_flow, "Screenshot")
        stop_app = node_by_action(base_flow, "StopApp")
        stop = node_by_action(base_flow, "Stop")
        if package_from(start_app) != TIKTOK_PACKAGE or package_from(stop_app) != TIKTOK_PACKAGE:
            raise BuildError("base export is not the qualified TikTok lifecycle")

        template_path = args.template_flow or latest_template_flow()
        registry = TemplateRegistry.from_raw_corpus(template_path)
        exists_kind = resolve_kind(registry, "ElementExists")

        helpers = [
            deepcopy(dict(node))
            for node in base_flow.nodes
            if isinstance(node, Mapping) and action_of(node) in HELPER_ACTIONS
        ]

        start = clone_with_new_id(start, "start")
        start_app = clone_with_new_id(start_app, "startapp")
        pause = clone_with_new_id(pause_template, "pause")
        exists = registry.clone(exists_kind, new_id=new_id("elementexists"))
        screenshot = clone_with_new_id(screenshot, "screenshot")
        stop = clone_with_new_id(stop, "stop")
        patch_options(pause, {"timeoutType": "fixed", "timeout": str(args.startup_pause)})

        runtime: list[dict[str, Any]] = [start, start_app, pause, exists, screenshot, stop]
        for index, node in enumerate(runtime):
            set_position(node, 0.0, index * 125.0)
        for index, node in enumerate(helpers):
            set_position(node, -320.0, 120.0 + index * 110.0)

        start_edge, middle_edge, stop_edge = edge_templates(base_flow)
        edges: list[dict[str, Any]] = []
        for index, (source, target) in enumerate(zip(runtime, runtime[1:])):
            template = start_edge if index == 0 else (stop_edge if action_of(target) == "Stop" else middle_edge)
            reset_route(source, str(target["id"]))
            edges.append(retarget_edge(template, source, target))
        reset_route(runtime[-1], None)

        built = FlowDocument.from_flow({
            **{key: deepcopy(value) for key, value in base_flow.to_dict().items() if key not in {"nodes", "edges"}},
            "nodes": helpers + runtime,
            "edges": edges,
        })
        warnings = built.validate_basic()
        if warnings:
            raise BuildError("compiled graph failed validation: " + "; ".join(warnings))
        validate_feed_anchor_lab_flow(built)

        out_doc = GenFarmDocument(base_doc.to_dict())
        out_doc.replace_flow(built)
        out_doc.patch_metadata({"name": args.name})
        output = args.output or args.base.with_name(f"{args.base.stem} - Feed Anchor Qualification.genfarm")
        out_doc.save(output)

        print("=" * 78)
        print("TIKTOK FEED-ANCHOR QUALIFICATION COMPILER")
        print("=" * 78)
        print(f"Base:      {args.base}")
        print(f"Templates: {template_path}")
        print(f"Output:    {output}")
        print("Route:     Start -> StartApp -> Pause -> ElementExists -> Screenshot -> Stop")
        print("Graph validation: PASS")
        print("Selector state: UNCONFIGURED exact GenFarmer template")
        print("Next: open the ElementExists node in GenFarmer and configure one stable feed-specific selector with the native inspector.")
        print("Do not invent coordinates or selector field names; save/export after GenFarmer serializes the configuration.")
        print("=" * 78)
        return 0
    except (BuildError, GenFarmFileError, TemplateRegistryError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
