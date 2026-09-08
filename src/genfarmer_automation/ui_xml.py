"""Android UI XML parsing and conservative selector learning.

This module is intentionally independent of GenFarmer's partially-documented
node schema.  Python can capture Android UIAutomator XML over ADB, learn stable
selectors from repeated snapshots, and later patch only a verified GenFarmer
XPath option key.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable
import xml.etree.ElementTree as ET


class UiXmlError(ValueError):
    pass


@dataclass(frozen=True)
class SelectorCandidate:
    kind: str
    xpath: str
    class_name: str | None
    occurrences: tuple[int, ...]
    present_in_all: bool
    unique_in_all: bool
    score: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    pieces: list[str] = []
    for index, part in enumerate(parts):
        if part:
            pieces.append(f"'{part}'")
        if index + 1 < len(parts):
            pieces.append('"\'"')
    return "concat(" + ",".join(pieces) + ")"


def parse_ui_xml(text: str) -> ET.Element:
    if not isinstance(text, str) or not text.strip():
        raise UiXmlError("UI XML is empty")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise UiXmlError(f"invalid UI XML: {exc}") from exc
    if root.tag not in {"hierarchy", "node"}:
        raise UiXmlError(f"unexpected UI XML root: {root.tag!r}")
    return root


def _nodes(root: ET.Element, package: str | None) -> list[ET.Element]:
    out = list(root.iter("node"))
    if package:
        scoped = [node for node in out if node.attrib.get("package") == package]
        if scoped:
            return scoped
    return out


def _dynamic_text(value: str) -> bool:
    value = value.strip()
    if not value or len(value) > 80:
        return True
    if value.startswith("@"):  # usernames are content-specific
        return True
    if "#" in value or "http" in value.lower():
        return True
    if sum(ch.isdigit() for ch in value) >= 3:
        return True
    return False


def _count_attr(root: ET.Element, *, package: str | None, key: str, value: str, class_name: str | None) -> int:
    count = 0
    for node in _nodes(root, package):
        if node.attrib.get(key) != value:
            continue
        if class_name and node.attrib.get("class") != class_name:
            continue
        count += 1
    return count


def _xpath_for(key: str, value: str, class_name: str | None) -> str:
    test = f"@{key}={_xpath_literal(value)}"
    if class_name:
        return f"//{class_name}[{test}]"
    return f"//*[{test}]"


def learn_selector_candidates(
    xml_snapshots: Iterable[str],
    *,
    package: str | None = None,
    include_text: bool = False,
) -> list[SelectorCandidate]:
    roots = [parse_ui_xml(text) for text in xml_snapshots]
    if len(roots) < 2:
        raise UiXmlError("at least two UI XML snapshots are required")

    seed_nodes = _nodes(roots[0], package)
    raw: dict[tuple[str, str, str | None], None] = {}
    for node in seed_nodes:
        class_name = node.attrib.get("class") or None
        resource_id = (node.attrib.get("resource-id") or "").strip()
        content_desc = (node.attrib.get("content-desc") or "").strip()
        text = (node.attrib.get("text") or "").strip()
        if resource_id:
            raw[("resource-id", resource_id, class_name)] = None
        if content_desc and not _dynamic_text(content_desc):
            raw[("content-desc", content_desc, class_name)] = None
        if include_text and text and not _dynamic_text(text):
            raw[("text", text, class_name)] = None

    result: list[SelectorCandidate] = []
    base_score = {"resource-id": 100, "content-desc": 75, "text": 35}
    for (key, value, class_name) in raw:
        counts = tuple(
            _count_attr(root, package=package, key=key, value=value, class_name=class_name)
            for root in roots
        )
        present = all(count > 0 for count in counts)
        if not present:
            continue
        unique = all(count == 1 for count in counts)
        score = base_score[key] + (25 if unique else 0) - max(0, max(counts) - 1) * 5
        result.append(
            SelectorCandidate(
                kind=key,
                xpath=_xpath_for(key, value, class_name),
                class_name=class_name,
                occurrences=counts,
                present_in_all=present,
                unique_in_all=unique,
                score=score,
            )
        )

    result.sort(key=lambda item: (-item.score, item.kind, item.xpath))
    return result


def filter_against_negative_xml(
    candidates: Iterable[SelectorCandidate],
    negative_snapshots: Iterable[str],
    *,
    package: str | None = None,
) -> list[SelectorCandidate]:
    roots = [parse_ui_xml(text) for text in negative_snapshots]
    if not roots:
        raise UiXmlError("at least one negative UI XML snapshot is required")

    kept: list[SelectorCandidate] = []
    attr_re = re.compile(r"@(?P<key>resource-id|content-desc|text)=(?P<quote>['\"])(?P<value>.*?)(?P=quote)")
    for candidate in candidates:
        match = attr_re.search(candidate.xpath)
        if not match:
            continue
        key = match.group("key")
        value = match.group("value")
        if any(_count_attr(root, package=package, key=key, value=value, class_name=candidate.class_name) for root in roots):
            continue
        kept.append(candidate)
    return kept
