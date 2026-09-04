"""Lossless helpers for GenFarmer ``script.flow`` documents.

The public GenFarmer API documents ``script.flow`` as a graph containing
``nodes`` and ``edges`` but does not publish the JSON schema for every node
kind.  This module therefore deliberately preserves unknown fields instead of
trying to coerce them into an incomplete model.

The design rule is simple: read first, round-trip exactly, then add semantic
helpers only after a node shape has been observed and verified against the
installed GenFarmer version.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


class FlowError(ValueError):
    """Raised when a payload does not contain a usable GenFarmer flow."""


def find_flow(value: Any) -> dict[str, Any] | None:
    """Find the first dict shaped like ``script.flow`` in an API payload.

    GenFarmer API responses can be wrapped in ``data``/``result`` objects, so
    callers should not have to know the response envelope in advance.
    """

    if isinstance(value, dict):
        script = value.get("script")
        if isinstance(script, dict):
            flow = script.get("flow")
            if isinstance(flow, dict) and isinstance(flow.get("nodes"), list) and isinstance(flow.get("edges"), list):
                return flow

        if isinstance(value.get("nodes"), list) and isinstance(value.get("edges"), list):
            return value

        for child in value.values():
            found = find_flow(child)
            if found is not None:
                return found

    elif isinstance(value, list):
        for child in value:
            found = find_flow(child)
            if found is not None:
                return found

    return None


def _deep_merge(target: dict[str, Any], patch: Mapping[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)


def _node_id(node: Mapping[str, Any]) -> str | None:
    value = node.get("id")
    return str(value) if isinstance(value, (str, int)) else None


def infer_node_kind(node: Mapping[str, Any]) -> tuple[str, str]:
    """Return ``(kind, source_path)`` using only type-like fields.

    We intentionally do not fall back to user-facing labels/names because those
    may contain app-specific or sensitive text. Unknown shapes receive a stable
    structural identifier instead.
    """

    candidates = (
        ("type", node.get("type")),
        ("nodeType", node.get("nodeType")),
        ("kind", node.get("kind")),
        ("component", node.get("component")),
    )
    for path, value in candidates:
        if isinstance(value, (str, int)) and str(value):
            return str(value), path

    data = node.get("data")
    if isinstance(data, Mapping):
        for key in ("type", "nodeType", "kind", "component", "actionType"):
            value = data.get(key)
            if isinstance(value, (str, int)) and str(value):
                return str(value), f"data.{key}"

    signature_source = json.dumps(sorted(_structural_paths(node)), separators=(",", ":"))
    digest = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()[:12]
    return f"<unknown:{digest}>", "structural-signature"


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _structural_paths(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for key in sorted(map(str, value.keys())):
            child = value[key]
            path = f"{prefix}.{key}" if prefix else key
            paths.append(f"{path}:{_value_type(child)}")
            paths.extend(_structural_paths(child, path))
    elif isinstance(value, list):
        item_prefix = f"{prefix}[]" if prefix else "[]"
        item_types = sorted({_value_type(item) for item in value})
        for item_type in item_types:
            paths.append(f"{item_prefix}:{item_type}")
        # Union item structure without retaining values.
        for item in value[:20]:
            paths.extend(_structural_paths(item, item_prefix))
    return sorted(set(paths))


@dataclass
class FlowDocument:
    """A lossless editable wrapper around a GenFarmer flow dict."""

    _flow: dict[str, Any]

    @classmethod
    def from_flow(cls, flow: Mapping[str, Any]) -> "FlowDocument":
        copied = deepcopy(dict(flow))
        if not isinstance(copied.get("nodes"), list) or not isinstance(copied.get("edges"), list):
            raise FlowError("flow must contain list fields 'nodes' and 'edges'")
        return cls(copied)

    @classmethod
    def from_app_payload(cls, payload: Any) -> "FlowDocument":
        flow = find_flow(payload)
        if flow is None:
            raise FlowError("no script.flow with nodes/edges found in app payload")
        return cls.from_flow(flow)

    @property
    def nodes(self) -> list[dict[str, Any]]:
        return self._flow["nodes"]

    @property
    def edges(self) -> list[dict[str, Any]]:
        return self._flow["edges"]

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._flow)

    def canonical_json(self) -> str:
        return json.dumps(self._flow, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def validate_basic(self) -> list[str]:
        """Return graph integrity warnings without assuming node-specific schema."""

        warnings: list[str] = []
        ids: list[str] = []
        for index, node in enumerate(self.nodes):
            if not isinstance(node, dict):
                warnings.append(f"node[{index}] is not an object")
                continue
            node_id = _node_id(node)
            if node_id is None:
                warnings.append(f"node[{index}] has no scalar id")
            else:
                ids.append(node_id)

        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            warnings.append("duplicate node ids: " + ", ".join(duplicates))

        known_ids = set(ids)
        for index, edge in enumerate(self.edges):
            if not isinstance(edge, dict):
                warnings.append(f"edge[{index}] is not an object")
                continue
            source = edge.get("source")
            target = edge.get("target")
            if source is not None and known_ids and str(source) not in known_ids:
                warnings.append(f"edge[{index}] source {source!r} does not match a known node id")
            if target is not None and known_ids and str(target) not in known_ids:
                warnings.append(f"edge[{index}] target {target!r} does not match a known node id")
        return warnings

    def node_kinds(self) -> list[tuple[str, str, str | None]]:
        return [(infer_node_kind(node)[0], infer_node_kind(node)[1], _node_id(node)) for node in self.nodes if isinstance(node, dict)]

    def find_nodes(self, kind: str) -> list[dict[str, Any]]:
        return [node for node in self.nodes if isinstance(node, dict) and infer_node_kind(node)[0] == kind]

    def get_node(self, node_id: str) -> dict[str, Any]:
        matches = [node for node in self.nodes if isinstance(node, dict) and _node_id(node) == str(node_id)]
        if not matches:
            raise FlowError(f"node id not found: {node_id}")
        if len(matches) > 1:
            raise FlowError(f"node id is not unique: {node_id}")
        return matches[0]

    def patch_node(self, node_id: str, patch: Mapping[str, Any]) -> dict[str, Any]:
        """Deep-merge a verified patch into one node while preserving all other fields."""

        node = self.get_node(node_id)
        _deep_merge(node, patch)
        return deepcopy(node)

    def clone_node(
        self,
        template_node_id: str,
        *,
        new_id: str,
        patch: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Clone an observed node template.

        This is the preferred way to create a node until its complete schema is
        known: clone a real GenFarmer-generated node of the same kind, then
        change only fields we have verified.
        """

        if any(isinstance(node, dict) and _node_id(node) == str(new_id) for node in self.nodes):
            raise FlowError(f"new node id already exists: {new_id}")
        clone = deepcopy(self.get_node(template_node_id))
        clone["id"] = new_id
        if patch:
            _deep_merge(clone, patch)
        self.nodes.append(clone)
        return deepcopy(clone)

    def remove_node(self, node_id: str, *, remove_incident_edges: bool = True) -> None:
        before = len(self.nodes)
        self._flow["nodes"] = [
            node for node in self.nodes
            if not (isinstance(node, dict) and _node_id(node) == str(node_id))
        ]
        if len(self.nodes) == before:
            raise FlowError(f"node id not found: {node_id}")
        if remove_incident_edges:
            self._flow["edges"] = [
                edge for edge in self.edges
                if not (
                    isinstance(edge, dict)
                    and (str(edge.get("source")) == str(node_id) or str(edge.get("target")) == str(node_id))
                )
            ]

    def add_edge(self, edge: Mapping[str, Any]) -> dict[str, Any]:
        copied = deepcopy(dict(edge))
        self.edges.append(copied)
        return deepcopy(copied)
