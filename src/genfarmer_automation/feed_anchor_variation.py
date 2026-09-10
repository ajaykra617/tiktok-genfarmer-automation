"""Positive-variation qualification for TikTok feed-anchor candidates.

Candidates that survive negative screens are not necessarily robust across
multiple feed items.  This module rechecks those exact selectors against a set
of positive feed snapshots and keeps only selectors that remain unique in every
snapshot.  Exact selector values stay in local private evidence.
"""
from __future__ import annotations

import re
from typing import Iterable

from .ui_xml import SelectorCandidate, UiXmlError, parse_ui_xml


class FeedAnchorVariationError(ValueError):
    pass


_ATTR_RE = re.compile(
    r"@(?P<key>resource-id|content-desc|text)=(?P<quote>['\"])(?P<value>.*?)(?P=quote)"
)


def _identity(candidate: SelectorCandidate) -> tuple[str, str]:
    match = _ATTR_RE.search(candidate.xpath)
    if not match:
        raise FeedAnchorVariationError("candidate XPath is not a supported attribute selector")
    return match.group("key"), match.group("value")


def _nodes(root, package: str | None):
    nodes = list(root.iter("node"))
    if package:
        scoped = [node for node in nodes if node.attrib.get("package") == package]
        if scoped:
            return scoped
    return nodes


def candidate_counts(
    candidate: SelectorCandidate,
    xml_snapshots: Iterable[str],
    *,
    package: str | None = None,
) -> tuple[int, ...]:
    key, value = _identity(candidate)
    counts: list[int] = []
    for text in xml_snapshots:
        root = parse_ui_xml(text)
        count = 0
        for node in _nodes(root, package):
            if node.attrib.get(key) != value:
                continue
            if candidate.class_name and node.attrib.get("class") != candidate.class_name:
                continue
            count += 1
        counts.append(count)
    return tuple(counts)


def unique_presence_ratio(
    candidates: Iterable[SelectorCandidate],
    xml_snapshot: str,
    *,
    package: str | None = None,
) -> float:
    items = list(candidates)
    if not items:
        raise FeedAnchorVariationError("no selector candidates were supplied")
    unique = 0
    for candidate in items:
        try:
            counts = candidate_counts(candidate, [xml_snapshot], package=package)
        except (FeedAnchorVariationError, UiXmlError):
            continue
        if counts == (1,):
            unique += 1
    return unique / len(items)


def qualify_across_feed_variants(
    candidates: Iterable[SelectorCandidate],
    positive_snapshots: Iterable[str],
    *,
    package: str | None = None,
) -> list[SelectorCandidate]:
    """Keep selectors that are present exactly once in every feed snapshot."""
    items = list(candidates)
    if not items:
        raise FeedAnchorVariationError("no selector candidates were supplied")
    snapshots = list(positive_snapshots)
    if len(snapshots) < 2:
        raise FeedAnchorVariationError("at least two positive feed snapshots are required")

    qualified: list[SelectorCandidate] = []
    for candidate in items:
        try:
            counts = candidate_counts(candidate, snapshots, package=package)
        except (FeedAnchorVariationError, UiXmlError):
            continue
        if counts and all(count == 1 for count in counts):
            qualified.append(
                SelectorCandidate(
                    kind=candidate.kind,
                    xpath=candidate.xpath,
                    class_name=candidate.class_name,
                    occurrences=counts,
                    present_in_all=True,
                    unique_in_all=True,
                    score=candidate.score,
                )
            )
    qualified.sort(key=lambda item: (-item.score, item.kind, item.xpath))
    return qualified
