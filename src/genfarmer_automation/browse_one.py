"""Fail-closed helpers for one supervised passive TikTok browse action.

The production executor is GenFarmer.  This module only validates that the
compiled flow is the intentionally-small browse-one graph, that a previously
observed GenFarmer device binding exactly matches the ADB target we intend to
supervise, and that visual control evidence is strong enough before mutation.
"""
from __future__ import annotations

from typing import Any, Mapping

from .flow import FlowDocument
from .run_binding import RunBinding, extract_run_bindings
from .screen_transition import TransitionDecision, TransitionReport

EXPECTED_BROWSE_ONE_ROUTE = (
    "Start",
    "StartApp",
    "Pause",
    "Swipe",
    "Pause",
    "Screenshot",
    "Stop",
)


class BrowseOneError(ValueError):
    pass


def _action_of(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, Mapping):
        action = data.get("action")
        if isinstance(action, str) and action:
            return action
    return None


def runtime_route_actions(flow: FlowDocument) -> tuple[str, ...]:
    warnings = flow.validate_basic()
    if warnings:
        raise BrowseOneError("flow graph warnings: " + "; ".join(warnings))

    nodes: dict[str, Mapping[str, Any]] = {}
    starts: list[str] = []
    for node in flow.nodes:
        if not isinstance(node, Mapping):
            continue
        raw_id = node.get("id")
        if not isinstance(raw_id, (str, int)) or isinstance(raw_id, bool):
            continue
        node_id = str(raw_id)
        nodes[node_id] = node
        if _action_of(node) == "Start":
            starts.append(node_id)
    if len(starts) != 1:
        raise BrowseOneError(f"expected exactly one Start node; found {len(starts)}")

    outgoing: dict[str, list[str]] = {}
    for edge in flow.edges:
        if not isinstance(edge, Mapping):
            continue
        source = edge.get("source")
        target = edge.get("target")
        if isinstance(source, (str, int)) and not isinstance(source, bool) and isinstance(target, (str, int)) and not isinstance(target, bool):
            outgoing.setdefault(str(source), []).append(str(target))

    route: list[str] = []
    seen: set[str] = set()
    current = starts[0]
    for _ in range(len(nodes) + 1):
        if current in seen:
            raise BrowseOneError("cycle encountered while following runtime route")
        seen.add(current)
        node = nodes.get(current)
        if node is None:
            raise BrowseOneError("runtime route points to an unknown node")
        action = _action_of(node)
        if not action:
            raise BrowseOneError("runtime route contains a node without a verified action")
        route.append(action)
        if action == "Stop":
            return tuple(route)
        targets = outgoing.get(current, [])
        if len(targets) != 1:
            raise BrowseOneError(
                f"runtime node {action!r} must have exactly one outgoing edge; found {len(targets)}"
            )
        current = targets[0]
    raise BrowseOneError("runtime route did not reach Stop within the bounded traversal")


def validate_browse_one_flow(flow: FlowDocument) -> tuple[str, ...]:
    route = runtime_route_actions(flow)
    if route != EXPECTED_BROWSE_ONE_ROUTE:
        raise BrowseOneError(
            "compiled flow is not the qualified browse-one module: "
            + " -> ".join(route)
        )
    return route


def exact_bound_device_id(binding: RunBinding, adb_target: str) -> str | None:
    """Return the GenFarmer device id only for an exact ADB-target match.

    We intentionally do not use fuzzy matching on names, serial substrings, IP
    prefixes, or device order.  Ambiguous bindings therefore fail closed.
    """
    if not isinstance(adb_target, str) or not adb_target:
        return None
    matches = [device_id for device_id in binding.device_ids if device_id == adb_target]
    return matches[0] if len(matches) == 1 else None


def created_run_binding(payload: Any, *, app_id: str, task_id: str) -> RunBinding | None:
    matches = [
        item
        for item in extract_run_bindings(payload)
        if item.app_id == str(app_id) and item.task_id == str(task_id)
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def control_window_is_safe(report: TransitionReport) -> bool:
    """Return True only when the no-action control window is trustworthy and quiet.

    ``assess_visual_transition`` has three outcomes.  For a control window, only
    ``INCONCLUSIVE_CHANGE`` is acceptable: it means enough of the baseline was
    temporally stable to evaluate, but no distributed transition was proven.

    ``INCONCLUSIVE_BASELINE`` must *not* be treated as quiet.  It means there was
    too little stable screen area to trust the comparison at all.  Allowing a
    mutation in that state creates a false-ready risk.
    """
    return report.decision is TransitionDecision.INCONCLUSIVE_CHANGE
