#!/usr/bin/env python3
"""Compile one intentionally-small passive TikTok browse module for GenFarmer.

Runtime route:
    Start -> StartApp -> Pause -> Swipe -> Pause -> Screenshot -> Stop

Important: there is deliberately no StopApp node.  The Python supervisor must be
able to observe TikTok after GenFarmer finishes so it can prove the intended
screen transition rather than trusting the node log alone.
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

# Reuse already-qualified cloning/edge helpers instead of creating a second
# interpretation of GenFarmer's partially-undocumented node schema.
from genfarm_build_tiktok_warmup import (  # noqa: E402
    BuildError,
    HELPER_ACTIONS,
    TIKTOK_PACKAGE,
    action_of,
    clone_with_new_id,
    edge_templates,
    latest_template_flow,
    load_options,
    new_id,
    node_by_action,
    package_from,
    patch_options,
    reset_route,
    resolve_kind,
    retarget_edge,
    set_position,
)
from genfarmer_automation.browse_one import validate_browse_one_flow  # noqa: E402
from genfarmer_automation.flow import FlowDocument  # noqa: E402
from genfarmer_automation.flow_registry import TemplateRegistry, TemplateRegistryError  # noqa: E402
from genfarmer_automation.genfarm_file import GenFarmDocument, GenFarmFileError  # noqa: E402

DEFAULT_NAME = "GF Lab - TikTok Browse One"


def _pause_seconds(value: int, label: str) -> int:
    if not 1 <= value <= 60:
        raise BuildError(f"{label} must be 1..60 seconds")
    return value


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile one supervised TikTok browse-one .genfarm module")
    ap.add_argument("base", type=Path, help="known-good TikTok .genfarm export")
    ap.add_argument("--output", type=Path, help="output .genfarm path")
    ap.add_argument("--name", default=DEFAULT_NAME)
    ap.add_argument("--startup-pause", type=int, default=1)
    ap.add_argument("--after-pause", type=int, default=1)
    ap.add_argument("--template-flow", type=Path, help="private exact flow.raw.json; defaults to latest capture")
    ap.add_argument("--swipe-options", type=Path, required=True, help="verified local Swipe data.options JSON")
    args = ap.parse_args()

    try:
        startup_pause = _pause_seconds(args.startup_pause, "--startup-pause")
        after_pause = _pause_seconds(args.after_pause, "--after-pause")
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
        swipe_kind = resolve_kind(registry, "Swipe")
        swipe_options = load_options(args.swipe_options)
        if swipe_options is None:
            raise BuildError("verified Swipe options are required")

        helpers = [
            deepcopy(dict(node))
            for node in base_flow.nodes
            if isinstance(node, Mapping) and action_of(node) in HELPER_ACTIONS
        ]

        start = clone_with_new_id(start, "start")
        start_app = clone_with_new_id(start_app, "startapp")
        pause_before = clone_with_new_id(pause_template, "pause-before")
        swipe = registry.clone(swipe_kind, new_id=new_id("swipe"))
        pause_after = clone_with_new_id(pause_template, "pause-after")
        screenshot = clone_with_new_id(screenshot, "screenshot")
        stop = clone_with_new_id(stop, "stop")

        patch_options(pause_before, {"timeoutType": "fixed", "timeout": str(startup_pause)})
        patch_options(swipe, swipe_options)
        patch_options(pause_after, {"timeoutType": "fixed", "timeout": str(after_pause)})

        runtime: list[dict[str, Any]] = [
            start,
            start_app,
            pause_before,
            swipe,
            pause_after,
            screenshot,
            stop,
        ]

        for index, node in enumerate(runtime):
            set_position(node, 0.0, index * 115.0)
        for index, node in enumerate(helpers):
            set_position(node, -300.0, 120.0 + index * 110.0)

        start_edge, middle_edge, stop_edge = edge_templates(base_flow)
        edges: list[dict[str, Any]] = []
        for index, (source, target) in enumerate(zip(runtime, runtime[1:])):
            template = start_edge if index == 0 else (stop_edge if action_of(target) == "Stop" else middle_edge)
            reset_route(source, str(target["id"]))
            edges.append(retarget_edge(template, source, target))
        reset_route(runtime[-1], None)

        built_flow = FlowDocument.from_flow(
            {
                **{
                    key: deepcopy(value)
                    for key, value in base_flow.to_dict().items()
                    if key not in {"nodes", "edges"}
                },
                "nodes": helpers + runtime,
                "edges": edges,
            }
        )
        warnings = built_flow.validate_basic()
        if warnings:
            raise BuildError("compiled graph failed validation: " + "; ".join(warnings))
        validate_browse_one_flow(built_flow)

        output_doc = GenFarmDocument(base_doc.to_dict())
        output_doc.replace_flow(built_flow)
        output_doc.patch_metadata({"name": args.name})
        output = args.output or args.base.with_name(f"{args.base.stem} - Browse One.genfarm")
        output_doc.save(output)

        print("=" * 78)
        print("TIKTOK BROWSE_ONE .GENFARM COMPILER")
        print("=" * 78)
        print(f"Base:      {args.base}")
        print(f"Templates: {template_path}")
        print(f"Output:    {output}")
        print(f"Startup pause: {startup_pause}s")
        print(f"After pause:   {after_pause}s")
        print(f"Nodes: {len(built_flow.nodes)}")
        print(f"Edges: {len(built_flow.edges)}")
        print("Graph validation: PASS")
        print("Browse-one route validation: PASS")
        print("Runtime: Start -> StartApp -> Pause -> Swipe -> Pause -> Screenshot -> Stop")
        print("TikTok remains open after the module so Python can verify the postcondition.")
        print("Scope: one passive browse transition only.")
        print("=" * 78)
        return 0
    except (BuildError, GenFarmFileError, TemplateRegistryError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
