"""Helpers for finalizing a live GenFarmer feed-anchor app by sentinel.

The one-time schema probe puts a known harmless sentinel into ElementExists.
These helpers locate that exact scalar only inside ElementExists ``data`` and
replace it in-place.  No undocumented field name or path is invented.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .flow import find_flow
from .structure_paths import find_scalar_value_paths, set_existing_path


class LiveFeedAnchorError(ValueError):
    pass


def _action_of(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, Mapping):
        action = data.get("action")
        if isinstance(action, str) and action:
            return action
    return None


def sentinel_locations(app_payload: Any, sentinel: str) -> list[tuple[int, tuple[str | int, ...]]]:
    """Return ``(flow_node_index, data_relative_path)`` sentinel locations.

    Only ElementExists node ``data`` objects are considered.  A sentinel that
    appears elsewhere in the app cannot accidentally identify or patch a node.
    """
    flow = find_flow(app_payload)
    if flow is None:
        return []
    nodes = flow.get("nodes")
    if not isinstance(nodes, list):
        return []

    out: list[tuple[int, tuple[str | int, ...]]] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping) or _action_of(node) != "ElementExists":
            continue
        data = node.get("data")
        if not isinstance(data, dict):
            continue
        for path in find_scalar_value_paths(data, sentinel):
            out.append((index, path))
    return out


def unique_sentinel_location(app_payload: Any, sentinel: str) -> tuple[int, tuple[str | int, ...]]:
    locations = sentinel_locations(app_payload, sentinel)
    if len(locations) != 1:
        raise LiveFeedAnchorError(
            f"expected exactly one ElementExists schema sentinel; found {len(locations)}"
        )
    return locations[0]


def patch_script_by_sentinel(
    app_payload: Mapping[str, Any],
    *,
    sentinel: str,
    replacement: str,
) -> tuple[dict[str, Any], tuple[str | int, ...]]:
    """Return a copied ``script`` with the exact sentinel replaced in-place."""
    if not isinstance(replacement, str) or not replacement.strip():
        raise LiveFeedAnchorError("replacement XPath must be a non-empty string")
    script = app_payload.get("script")
    if not isinstance(script, Mapping):
        raise LiveFeedAnchorError("app payload has no script object")

    node_index, data_path = unique_sentinel_location(app_payload, sentinel)
    copied_script = deepcopy(dict(script))
    flow = copied_script.get("flow")
    if not isinstance(flow, dict) or not isinstance(flow.get("nodes"), list):
        raise LiveFeedAnchorError("copied script has no usable flow")
    nodes = flow["nodes"]
    if not (0 <= node_index < len(nodes)) or not isinstance(nodes[node_index], dict):
        raise LiveFeedAnchorError("ElementExists node moved while copying script")
    data = nodes[node_index].get("data")
    if not isinstance(data, dict):
        raise LiveFeedAnchorError("ElementExists node has no mutable data object")
    set_existing_path(data, data_path, replacement)
    return copied_script, data_path
