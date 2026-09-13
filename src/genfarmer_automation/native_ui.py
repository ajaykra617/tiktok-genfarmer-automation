"""Runtime semantic locator for Android UIAutomator hierarchy XML.

Targets are selected from fresh hierarchy evidence. The module never invents
fixed coordinates; tap points are derived from the matched node bounds.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable
import xml.etree.ElementTree as ET

from .ui_xml import parse_ui_xml


class NativeUiError(RuntimeError):
    pass


class NativeUiNotFound(NativeUiError):
    pass


class NativeUiAmbiguous(NativeUiError):
    pass


_BOUNDS_RE = re.compile(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$")


@dataclass(frozen=True)
class UiNode:
    text: str
    content_desc: str
    resource_id: str
    class_name: str
    package: str
    bounds: tuple[int, int, int, int]
    clickable: bool
    enabled: bool

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.bounds
        return max(0, x2 - x1) * max(0, y2 - y1)


def parse_bounds(value: str) -> tuple[int, int, int, int] | None:
    match = _BOUNDS_RE.match((value or "").strip())
    if not match:
        return None
    x1, y1, x2, y2 = (int(item) for item in match.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def collect_nodes(xml: str, *, package: str | None = None) -> list[UiNode]:
    root = parse_ui_xml(xml)
    out: list[UiNode] = []
    for raw in root.iter("node"):
        pkg = raw.attrib.get("package", "")
        if package and pkg and pkg != package:
            continue
        bounds = parse_bounds(raw.attrib.get("bounds", ""))
        if bounds is None:
            continue
        out.append(
            UiNode(
                text=(raw.attrib.get("text") or "").strip(),
                content_desc=(raw.attrib.get("content-desc") or "").strip(),
                resource_id=(raw.attrib.get("resource-id") or "").strip(),
                class_name=(raw.attrib.get("class") or "").strip(),
                package=pkg,
                bounds=bounds,
                clickable=(raw.attrib.get("clickable") == "true"),
                enabled=(raw.attrib.get("enabled") != "false"),
            )
        )
    return out


def _norm(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())


def _score(node: UiNode, terms: Iterable[str]) -> int:
    fields = (
        (node.text, 120),
        (node.content_desc, 115),
        (node.resource_id.rsplit("/", 1)[-1], 75),
    )
    best = 0
    for term_raw in terms:
        term = _norm(term_raw)
        if not term:
            continue
        for value_raw, base in fields:
            value = _norm(value_raw)
            if not value:
                continue
            if value == term:
                best = max(best, base)
            elif value.startswith(term) or term.startswith(value):
                best = max(best, base - 15)
            elif term in value:
                best = max(best, base - 30)
    if best:
        if node.clickable:
            best += 12
        if node.enabled:
            best += 4
    return best


def find_semantic_node(
    xml: str,
    terms: Iterable[str],
    *,
    package: str | None = None,
    required_class_suffix: str | None = None,
) -> UiNode:
    candidates: list[tuple[int, int, UiNode]] = []
    for node in collect_nodes(xml, package=package):
        if required_class_suffix and not node.class_name.endswith(required_class_suffix):
            continue
        score = _score(node, terms)
        if score <= 0:
            continue
        # Prefer smaller controls when semantic confidence is otherwise equal.
        candidates.append((score, -node.area, node))
    if not candidates:
        raise NativeUiNotFound("no runtime UI node matched the requested semantic terms")
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    top_score, top_area, top = candidates[0]
    tied = [item for item in candidates if item[0] == top_score and item[1] == top_area]
    centers = {item[2].center for item in tied}
    if len(centers) > 1:
        raise NativeUiAmbiguous("multiple runtime UI nodes tied for the best semantic match")
    return top


def find_editable_node(xml: str, *, package: str | None = None, hints: Iterable[str] = ()) -> UiNode:
    nodes = [
        node for node in collect_nodes(xml, package=package)
        if node.enabled and node.class_name.endswith("EditText")
    ]
    if not nodes:
        raise NativeUiNotFound("no enabled EditText exists in the current hierarchy")
    hint_terms = tuple(hints)
    if hint_terms:
        scored = [(_score(node, hint_terms), -node.area, node) for node in nodes]
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if scored[0][0] > 0:
            top = scored[0]
            tied = [item for item in scored if item[0] == top[0] and item[1] == top[1]]
            if len({item[2].center for item in tied}) > 1:
                raise NativeUiAmbiguous("multiple editable nodes tied for the requested hints")
            return top[2]
    if len(nodes) == 1:
        return nodes[0]
    raise NativeUiAmbiguous("multiple enabled EditText nodes exist without a unique semantic hint")


def contains_semantic_term(xml: str, terms: Iterable[str], *, package: str | None = None) -> bool:
    try:
        find_semantic_node(xml, terms, package=package)
    except NativeUiError:
        return False
    return True
