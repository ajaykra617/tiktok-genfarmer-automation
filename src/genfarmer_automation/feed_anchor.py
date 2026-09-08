"""Validation helpers for the one-time TikTok feed-anchor qualification flow.

This lane exists only to capture a real GenFarmer ``ElementExists`` selector
configuration from the installed GenFarmer version.  The public source never
invents selector field names or values: it clones the observed GenFarmer node
shape, then the operator configures the selector once in GenFarmer's own UI.
"""
from __future__ import annotations

from typing import Any, Mapping

from .flow import FlowDocument

EXPECTED_FEED_ANCHOR_LAB_ROUTE = (
    "Start",
    "StartApp",
    "Pause",
    "ElementExists",
    "Screenshot",
    "Stop",
)


class FeedAnchorError(ValueError):
    pass


def _action_of(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, Mapping):
        value = data.get("action")
        if isinstance(value, str) and value:
            return value
    return None


def runtime_route_actions(flow: FlowDocument) -> tuple[str, ...]:
    warnings = flow.validate_basic()
    if warnings:
        raise FeedAnchorError("flow graph warnings: " + "; ".join(warnings))

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
        raise FeedAnchorError(f"expected exactly one Start node; found {len(starts)}")

    outgoing: dict[str, list[str]] = {}
    for edge in flow.edges:
        if not isinstance(edge, Mapping):
            continue
        source = edge.get("source")
        target = edge.get("target")
        if (
            isinstance(source, (str, int)) and not isinstance(source, bool)
            and isinstance(target, (str, int)) and not isinstance(target, bool)
        ):
            outgoing.setdefault(str(source), []).append(str(target))

    route: list[str] = []
    seen: set[str] = set()
    current = starts[0]
    for _ in range(len(nodes) + 1):
        if current in seen:
            raise FeedAnchorError("cycle encountered while following feed-anchor lab route")
        seen.add(current)
        node = nodes.get(current)
        if node is None:
            raise FeedAnchorError("feed-anchor lab route points to an unknown node")
        action = _action_of(node)
        if not action:
            raise FeedAnchorError("feed-anchor lab route contains a node without an action")
        route.append(action)
        if action == "Stop":
            return tuple(route)
        targets = outgoing.get(current, [])
        if len(targets) != 1:
            raise FeedAnchorError(
                f"runtime node {action!r} must have exactly one outgoing edge; found {len(targets)}"
            )
        current = targets[0]
    raise FeedAnchorError("feed-anchor lab route did not reach Stop")


def validate_feed_anchor_lab_flow(flow: FlowDocument) -> tuple[str, ...]:
    route = runtime_route_actions(flow)
    if route != EXPECTED_FEED_ANCHOR_LAB_ROUTE:
        raise FeedAnchorError(
            "flow is not the qualified feed-anchor lab module: " + " -> ".join(route)
        )
    return route
