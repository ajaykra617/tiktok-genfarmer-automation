#!/usr/bin/env python3
"""Compile a passive TikTok warm-up GenFarmer app entirely with Python.

The compiler starts from a known-good TikTok .genfarm export, clones only exact
GenFarmer-generated node templates from local ignored evidence, rewires a fresh
linear runtime chain, validates it, and writes a new .genfarm file for review or
import.

Current scope is deliberately passive/read-only warm-up qualification:
- launch TikTok;
- bounded feed browsing with Swipe + Pause cycles;
- screenshot evidence;
- stop TikTok cleanly.

It does NOT add likes, follows, replies, DMs, account creation/login/reset,
captcha handling, or cross-account engagement.

Action-specific Swipe options can be supplied from a local JSON file after one
Swipe node has been configured once in GenFarmer. Until then the compiler still
creates and connects exact default Swipe templates and clearly reports that
Swipe needs configuration before runtime qualification.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any, Mapping
import uuid

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.flow import FlowDocument  # noqa: E402
from genfarmer_automation.flow_registry import (  # noqa: E402
    TemplateRegistry,
    TemplateRegistryError,
)
from genfarmer_automation.genfarm_file import (  # noqa: E402
    GenFarmDocument,
    GenFarmFileError,
)

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"
DEFAULT_NAME = "GF Lab - TikTok Warmup Python"
RUNTIME_ACTIONS = {"Start", "StartApp", "Pause", "Swipe", "Screenshot", "StopApp", "Stop"}
HELPER_ACTIONS = {"Variables", "ContextMenu"}


class BuildError(ValueError):
    pass


def action_of(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, Mapping):
        action = data.get("action")
        if isinstance(action, str) and action:
            return action
    return None


def node_by_action(flow: FlowDocument, action: str) -> dict[str, Any]:
    matches = [n for n in flow.nodes if isinstance(n, Mapping) and action_of(n) == action]
    if len(matches) != 1:
        raise BuildError(f"base flow must contain exactly one {action!r} node; found {len(matches)}")
    return deepcopy(dict(matches[0]))


def package_from(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if not isinstance(data, Mapping):
        return None
    options = data.get("options")
    if not isinstance(options, Mapping):
        return None
    value = options.get("packageName")
    return value if isinstance(value, str) and value else None


def latest_template_flow() -> Path:
    patterns = (
        "evidence/genfarmer-lab-template-capture-*/private/flow.raw.json",
        "evidence/genfarmer-lab-schema-matrix-*/private/flow.raw.json",
    )
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(ROOT.glob(pattern))
    paths = [p for p in paths if p.is_file()]
    if not paths:
        raise TemplateRegistryError(
            "no private template flow found under evidence; pass --template-flow explicitly"
        )
    return max(paths, key=lambda p: p.stat().st_mtime_ns)


def resolve_kind(registry: TemplateRegistry, action: str) -> str:
    matches = [kind for kind in registry.available_kinds() if kind.endswith(f":{action}")]
    if len(matches) != 1:
        raise TemplateRegistryError(
            f"expected one exact live template for {action!r}; found {matches}"
        )
    return matches[0]


def load_options(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"cannot read options JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BuildError("options JSON must be one JSON object containing data.options fields")
    return value


def patch_options(node: dict[str, Any], patch: Mapping[str, Any]) -> None:
    data = node.get("data")
    if not isinstance(data, dict):
        raise BuildError(f"node {node.get('id')} has no data object")
    options = data.get("options")
    if not isinstance(options, dict):
        raise BuildError(f"node {node.get('id')} has no data.options object")
    for key, value in patch.items():
        options[str(key)] = deepcopy(value)


def reset_route(node: dict[str, Any], next_id: str | None) -> None:
    data = node.get("data")
    if isinstance(data, dict):
        if "successNode" in data or next_id is not None:
            data["successNode"] = next_id
        if "failNode" in data:
            data["failNode"] = None


def set_position(node: dict[str, Any], x: float, y: float) -> None:
    position = node.get("position")
    if not isinstance(position, dict):
        position = {}
        node["position"] = position
    position["x"] = x
    position["y"] = y


def new_id(prefix: str) -> str:
    return f"py-{prefix.lower()}-{uuid.uuid4().hex[:8]}"


def clone_with_new_id(node: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    copied = deepcopy(dict(node))
    copied["id"] = new_id(prefix)
    return copied


def edge_templates(base: FlowDocument) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    id_to_action = {
        str(n.get("id")): action_of(n)
        for n in base.nodes
        if isinstance(n, Mapping) and isinstance(n.get("id"), (str, int))
    }
    start_edge = None
    middle_edge = None
    stop_edge = None
    for raw in base.edges:
        if not isinstance(raw, Mapping):
            continue
        source = str(raw.get("source"))
        target = str(raw.get("target"))
        sa = id_to_action.get(source)
        ta = id_to_action.get(target)
        if sa == "Start" and ta == "StartApp" and start_edge is None:
            start_edge = deepcopy(dict(raw))
        elif sa == "StopApp" and ta == "Stop" and stop_edge is None:
            stop_edge = deepcopy(dict(raw))
        elif sa not in {None, "Start"} and ta not in {None, "Stop"} and middle_edge is None:
            middle_edge = deepcopy(dict(raw))
    if start_edge is None or middle_edge is None or stop_edge is None:
        raise BuildError("base export does not contain the three required observed edge shapes")
    return start_edge, middle_edge, stop_edge


def retarget_edge(
    template: Mapping[str, Any],
    source: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    edge = deepcopy(dict(template))
    source_id = str(source["id"])
    target_id = str(target["id"])
    source_action = action_of(source)
    target_action = action_of(target)

    source_handle = f"{source_id}__handle-right" if source_action == "Start" else "successNode"
    target_handle = f"{target_id}__handle-left" if target_action == "Stop" else "successNode"

    edge["id"] = f"vueflow__edge-{source_id}{source_handle}-{target_id}{target_handle}"
    edge["source"] = source_id
    edge["target"] = target_id
    edge["sourceHandle"] = source_handle
    edge["targetHandle"] = target_handle
    edge["class"] = f"source-{source_id} target-{target_id}"
    edge["data"] = {
        "sourceHandle": source_handle,
        "targetHandle": target_handle,
    }
    # These are editor-render cache coordinates. Removing them lets GenFarmer
    # recompute geometry for the new node positions instead of inheriting stale
    # coordinates from the template edge.
    for key in ("sourceX", "sourceY", "targetX", "targetY"):
        edge.pop(key, None)
    return edge


def parse_pauses(text: str, cycles: int) -> list[int]:
    try:
        values = [int(part.strip()) for part in text.split(",") if part.strip()]
    except ValueError as exc:
        raise BuildError("--pauses must be comma-separated integer seconds") from exc
    expected = cycles + 1
    if len(values) != expected:
        raise BuildError(f"--pauses needs exactly {expected} values for {cycles} swipe cycles")
    if any(value < 1 or value > 3600 for value in values):
        raise BuildError("each pause must be between 1 and 3600 seconds")
    return values


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile a passive TikTok warm-up .genfarm file")
    ap.add_argument("base", type=Path, help="known-good TikTok .genfarm export")
    ap.add_argument("--output", type=Path, help="output .genfarm path")
    ap.add_argument("--name", default=DEFAULT_NAME)
    ap.add_argument("--cycles", type=int, default=3, help="number of feed swipe cycles (default: 3)")
    ap.add_argument(
        "--pauses",
        default="5,8,10,7",
        help="comma-separated seconds: startup pause plus one pause after each swipe",
    )
    ap.add_argument("--template-flow", type=Path, help="private exact flow.raw.json; defaults to latest local capture")
    ap.add_argument(
        "--swipe-options",
        type=Path,
        help="local JSON object containing verified Swipe data.options fields",
    )
    ap.add_argument(
        "--clear-identity",
        action="store_true",
        help="remove app identity/timestamps when intentionally preparing a copy for import",
    )
    args = ap.parse_args()

    if args.cycles < 1 or args.cycles > 100:
        print("ERROR: --cycles must be between 1 and 100", file=sys.stderr)
        return 2

    try:
        pauses = parse_pauses(args.pauses, args.cycles)
        base_doc = GenFarmDocument.load(args.base)
        base_flow = base_doc.flow

        start = node_by_action(base_flow, "Start")
        start_app = node_by_action(base_flow, "StartApp")
        pause_template = node_by_action(base_flow, "Pause")
        screenshot = node_by_action(base_flow, "Screenshot")
        stop_app = node_by_action(base_flow, "StopApp")
        stop = node_by_action(base_flow, "Stop")

        if package_from(start_app) != TIKTOK_PACKAGE or package_from(stop_app) != TIKTOK_PACKAGE:
            raise BuildError(
                "base export is not the qualified TikTok lifecycle: StartApp/StopApp packageName mismatch"
            )

        template_path = args.template_flow or latest_template_flow()
        registry = TemplateRegistry.from_raw_corpus(template_path)
        swipe_kind = resolve_kind(registry, "Swipe")
        swipe_options = load_options(args.swipe_options)

        # Preserve only editor helper nodes from the base. Runtime nodes are
        # reconstructed into a clean linear chain below.
        helpers = [
            deepcopy(dict(node))
            for node in base_flow.nodes
            if isinstance(node, Mapping) and action_of(node) in HELPER_ACTIONS
        ]

        runtime: list[dict[str, Any]] = []
        start = clone_with_new_id(start, "start")
        start_app = clone_with_new_id(start_app, "startapp")
        screenshot = clone_with_new_id(screenshot, "screenshot")
        stop_app = clone_with_new_id(stop_app, "stopapp")
        stop = clone_with_new_id(stop, "stop")

        runtime.extend([start, start_app])

        for index in range(args.cycles + 1):
            pause = clone_with_new_id(pause_template, f"pause{index + 1}")
            patch_options(
                pause,
                {
                    "timeoutType": "fixed",
                    "timeout": str(pauses[index]),
                },
            )
            runtime.append(pause)
            if index < args.cycles:
                swipe = registry.clone(swipe_kind, new_id=new_id(f"swipe{index + 1}"))
                if swipe_options is not None:
                    patch_options(swipe, swipe_options)
                runtime.append(swipe)

        runtime.extend([screenshot, stop_app, stop])

        # Lay out one clean vertical route that remains readable when opened in
        # GenFarmer. Helpers stay off to the left.
        x = 0.0
        y = 0.0
        for index, node in enumerate(runtime):
            set_position(node, x, y + index * 115.0)
        for index, node in enumerate(helpers):
            set_position(node, -300.0, 120.0 + index * 110.0)

        start_edge, middle_edge, stop_edge = edge_templates(base_flow)
        edges: list[dict[str, Any]] = []
        for index, (source, target) in enumerate(zip(runtime, runtime[1:])):
            if index == 0:
                template = start_edge
            elif action_of(target) == "Stop":
                template = stop_edge
            else:
                template = middle_edge
            reset_route(source, str(target["id"]))
            edges.append(retarget_edge(template, source, target))
        reset_route(runtime[-1], None)

        built_flow = FlowDocument.from_flow({
            **{
                key: deepcopy(value)
                for key, value in base_flow.to_dict().items()
                if key not in {"nodes", "edges"}
            },
            "nodes": helpers + runtime,
            "edges": edges,
        })
        warnings = built_flow.validate_basic()
        if warnings:
            raise BuildError("compiled graph failed validation: " + "; ".join(warnings))

        output_doc = GenFarmDocument(base_doc.to_dict())
        output_doc.replace_flow(built_flow)
        output_doc.patch_metadata({"name": args.name})
        if args.clear_identity:
            output_doc.clear_identity_for_copy()

        output = args.output or args.base.with_name(f"{args.base.stem} - Warmup Python.genfarm")
        output_doc.save(output)

        print("=" * 78)
        print("TIKTOK WARM-UP .GENFARM COMPILER")
        print("=" * 78)
        print(f"Base:      {args.base}")
        print(f"Templates: {template_path}")
        print(f"Output:    {output}")
        print(f"Swipe cycles: {args.cycles}")
        print("Pauses: " + ", ".join(f"{value}s" for value in pauses))
        print(f"Nodes: {len(built_flow.nodes)}")
        print(f"Edges: {len(built_flow.edges)}")
        print("Graph validation: PASS")
        print("Runtime route:")
        for node in runtime:
            print(f" - {action_of(node)}")
        if swipe_options is None:
            print("Swipe configuration: DEFAULT TEMPLATE ONLY - open the file in GenFarmer and configure Swipe before runtime use.")
            print("After one verified Swipe configuration, export its data.options to a local JSON file and rerun with --swipe-options.")
        else:
            print("Swipe configuration: verified local options patch supplied")
        if args.clear_identity:
            print("Identity: cleared for an intentional import-as-copy experiment")
        else:
            print("Identity: preserved from base export; do not import as a copy unless you understand GenFarmer's import behavior")
        print("Scope: passive browsing only; no like/follow/reply/DM/account actions were generated.")
        print("=" * 78)
        return 0

    except (BuildError, GenFarmFileError, TemplateRegistryError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
