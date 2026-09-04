"""Local-only template registry for verified GenFarmer ``script.flow`` nodes.

The raw corpus produced by ``scripts/genfarmer_flow_learn.py`` stays under the
ignored ``evidence/`` directory and may contain client-specific selectors/text.
This module loads that private corpus at runtime and indexes exact GenFarmer-
generated node templates by a semantic key derived from ``type`` +
``data.action``.

Nothing from the raw corpus is written to Git by this module.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class TemplateRegistryError(ValueError):
    """Raised when a template corpus is malformed or a template is missing."""


def semantic_kind(node: Mapping[str, Any]) -> str:
    """Return the most useful observed semantic identity for a GenFarmer node."""

    family_raw = node.get("type")
    family = str(family_raw) if isinstance(family_raw, (str, int)) else "<unknown-family>"
    data = node.get("data")
    action = None
    if isinstance(data, Mapping):
        raw = data.get("action")
        if isinstance(raw, (str, int)) and str(raw):
            action = str(raw)
    return f"{family}:{action}" if action else family


def structural_signature(value: Any) -> str:
    """Hash only field paths/types, never scalar values."""

    paths: list[str] = []

    def walk(item: Any, prefix: str = "") -> None:
        if isinstance(item, Mapping):
            for key in sorted(map(str, item.keys())):
                child = item[key]
                path = f"{prefix}.{key}" if prefix else key
                paths.append(f"{path}:{type_name(child)}")
                walk(child, path)
        elif isinstance(item, list):
            path = f"{prefix}[]" if prefix else "[]"
            for child in item[:20]:
                paths.append(f"{path}:{type_name(child)}")
                walk(child, path)

    walk(value)
    payload = "\n".join(sorted(set(paths))).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def type_name(value: Any) -> str:
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
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def deep_merge(target: dict[str, Any], patch: Mapping[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)


@dataclass(frozen=True)
class NodeTemplate:
    semantic_kind: str
    signature: str
    node: dict[str, Any]


class TemplateRegistry:
    """Index exact observed node templates from the local private corpus."""

    def __init__(self, templates: list[NodeTemplate]) -> None:
        self._by_kind: dict[str, list[NodeTemplate]] = {}
        seen: set[tuple[str, str]] = set()
        for template in templates:
            key = (template.semantic_kind, template.signature)
            if key in seen:
                continue
            seen.add(key)
            self._by_kind.setdefault(template.semantic_kind, []).append(template)
        for items in self._by_kind.values():
            items.sort(key=lambda item: item.signature)

    @classmethod
    def from_raw_corpus(cls, path: str | Path) -> "TemplateRegistry":
        corpus_path = Path(path)
        try:
            payload = json.loads(corpus_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TemplateRegistryError(f"cannot read raw flow corpus: {exc}") from exc
        if not isinstance(payload, list):
            raise TemplateRegistryError("raw corpus must be a list")

        templates: list[NodeTemplate] = []
        for app in payload:
            if not isinstance(app, Mapping):
                continue
            flow = app.get("flow")
            if not isinstance(flow, Mapping):
                continue
            nodes = flow.get("nodes")
            if not isinstance(nodes, list):
                continue
            for node in nodes:
                if not isinstance(node, Mapping):
                    continue
                copied = deepcopy(dict(node))
                templates.append(
                    NodeTemplate(
                        semantic_kind=semantic_kind(copied),
                        signature=structural_signature(copied),
                        node=copied,
                    )
                )
        if not templates:
            raise TemplateRegistryError("raw corpus contains no usable node templates")
        return cls(templates)

    def available_kinds(self) -> list[str]:
        return sorted(self._by_kind)

    def variants(self, kind: str) -> list[NodeTemplate]:
        return [
            NodeTemplate(item.semantic_kind, item.signature, deepcopy(item.node))
            for item in self._by_kind.get(kind, [])
        ]

    def clone(
        self,
        kind: str,
        *,
        new_id: str,
        variant: int = 0,
        patch: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        variants = self._by_kind.get(kind)
        if not variants:
            raise TemplateRegistryError(f"no observed template for semantic kind: {kind}")
        if variant < 0 or variant >= len(variants):
            raise TemplateRegistryError(
                f"variant {variant} out of range for {kind}; observed {len(variants)} variant(s)"
            )
        node = deepcopy(variants[variant].node)
        node["id"] = str(new_id)
        if patch:
            deep_merge(node, patch)
        return node
