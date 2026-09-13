"""Rank already-qualified TikTok feed-anchor selectors without exposing values.

This stage is deliberately downstream of both negative-screen qualification and
positive feed-variation qualification.  It does not decide whether a selector is
safe by itself; it only orders selectors that have already survived those gates.

Ranking favors selectors that remain unique, cover a meaningful central portion
of the screen across feed states, and have stable geometry.  Small action-rail or
navigation controls are penalized.  Exact resource-id/content-desc values remain
inside the private candidate payload and are never required in shareable output.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from statistics import median
from typing import Iterable

from .ui_xml import SelectorCandidate, parse_ui_xml


class FeedAnchorRankingError(ValueError):
    pass


_ATTR_RE = re.compile(
    r"@(?P<key>resource-id|content-desc|text)=(?P<quote>['\"])(?P<value>.*?)(?P=quote)"
)
_BOUNDS_RE = re.compile(r"^\[(?P<x1>-?\d+),(?P<y1>-?\d+)\]\[(?P<x2>-?\d+),(?P<y2>-?\d+)\]$")

_POSITIVE_TOKENS = {
    "feed": 12.0,
    "video": 10.0,
    "player": 9.0,
    "pager": 8.0,
    "aweme": 8.0,
    "item": 5.0,
    "surface": 5.0,
    "container": 4.0,
}
_NEGATIVE_TOKENS = {
    "like": -8.0,
    "comment": -10.0,
    "share": -8.0,
    "profile": -10.0,
    "search": -10.0,
    "tab": -7.0,
    "nav": -7.0,
    "button": -5.0,
    "avatar": -7.0,
    "count": -6.0,
    "music": -5.0,
    "sound": -5.0,
    "caption": -5.0,
    "follow": -7.0,
    "inbox": -7.0,
    "create": -7.0,
}


@dataclass(frozen=True)
class RankedFeedAnchor:
    candidate: SelectorCandidate
    rank_score: float
    median_area_ratio: float
    center_coverage_ratio: float
    geometry_stability: float
    semantic_adjustment: float

    def to_private_dict(self) -> dict[str, object]:
        value = self.candidate.to_dict()
        value.update(
            {
                "rank_score": round(self.rank_score, 6),
                "median_area_ratio": round(self.median_area_ratio, 6),
                "center_coverage_ratio": round(self.center_coverage_ratio, 6),
                "geometry_stability": round(self.geometry_stability, 6),
                "semantic_adjustment": round(self.semantic_adjustment, 6),
            }
        )
        return value


def _identity(candidate: SelectorCandidate) -> tuple[str, str]:
    match = _ATTR_RE.search(candidate.xpath)
    if not match:
        raise FeedAnchorRankingError("candidate XPath is not a supported attribute selector")
    return match.group("key"), match.group("value")


def _bounds(value: str | None) -> tuple[int, int, int, int] | None:
    if not value:
        return None
    match = _BOUNDS_RE.match(value.strip())
    if not match:
        return None
    x1, y1, x2, y2 = (int(match.group(name)) for name in ("x1", "y1", "x2", "y2"))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _scoped_nodes(root, package: str | None):
    nodes = list(root.iter("node"))
    if package:
        scoped = [node for node in nodes if node.attrib.get("package") == package]
        if scoped:
            return scoped
    return nodes


def _screen_extent(nodes) -> tuple[int, int]:
    max_x = 0
    max_y = 0
    for node in nodes:
        box = _bounds(node.attrib.get("bounds"))
        if box is None:
            continue
        max_x = max(max_x, box[2])
        max_y = max(max_y, box[3])
    return max_x, max_y


def _semantic_adjustment(value: str) -> float:
    text = value.lower()
    score = 0.0
    for token, weight in _POSITIVE_TOKENS.items():
        if token in text:
            score += weight
    for token, weight in _NEGATIVE_TOKENS.items():
        if token in text:
            score += weight
    return score


def rank_feed_anchor_candidates(
    candidates: Iterable[SelectorCandidate],
    xml_snapshots: Iterable[str],
    *,
    package: str | None = None,
) -> list[RankedFeedAnchor]:
    items = list(candidates)
    snapshots = list(xml_snapshots)
    if not items:
        raise FeedAnchorRankingError("no selector candidates were supplied")
    if len(snapshots) < 2:
        raise FeedAnchorRankingError("at least two positive feed snapshots are required")

    parsed = []
    for text in snapshots:
        root = parse_ui_xml(text)
        nodes = _scoped_nodes(root, package)
        width, height = _screen_extent(nodes)
        if width <= 0 or height <= 0:
            raise FeedAnchorRankingError("positive XML did not expose usable node bounds")
        parsed.append((nodes, width, height))

    ranked: list[RankedFeedAnchor] = []
    for candidate in items:
        key, value = _identity(candidate)
        area_ratios: list[float] = []
        center_hits = 0
        valid = True

        for nodes, width, height in parsed:
            matches = [
                node
                for node in nodes
                if node.attrib.get(key) == value
                and (not candidate.class_name or node.attrib.get("class") == candidate.class_name)
            ]
            if len(matches) != 1:
                valid = False
                break
            box = _bounds(matches[0].attrib.get("bounds"))
            if box is None:
                valid = False
                break
            x1, y1, x2, y2 = box
            area_ratio = ((x2 - x1) * (y2 - y1)) / float(width * height)
            area_ratios.append(max(0.0, min(1.0, area_ratio)))
            cx, cy = width / 2.0, height / 2.0
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                center_hits += 1

        if not valid or len(area_ratios) != len(parsed):
            continue

        median_area = float(median(area_ratios))
        max_area = max(area_ratios)
        min_area = min(area_ratios)
        stability = 1.0 if max_area <= 0 else max(0.0, 1.0 - ((max_area - min_area) / max_area))
        center_ratio = center_hits / len(parsed)
        semantic = _semantic_adjustment(value)

        # Geometry matters more than opaque/id naming.  The area term is capped
        # so a single full-screen wrapper does not overwhelm all other evidence.
        area_bonus = min(35.0, median_area * 55.0)
        center_bonus = center_ratio * 18.0
        stability_bonus = stability * 12.0
        small_control_penalty = -14.0 if median_area < 0.01 else (-6.0 if median_area < 0.03 else 0.0)
        kind_bonus = 6.0 if candidate.kind == "resource-id" else 0.0
        score = (
            float(candidate.score)
            + area_bonus
            + center_bonus
            + stability_bonus
            + small_control_penalty
            + kind_bonus
            + semantic
        )
        ranked.append(
            RankedFeedAnchor(
                candidate=candidate,
                rank_score=score,
                median_area_ratio=median_area,
                center_coverage_ratio=center_ratio,
                geometry_stability=stability,
                semantic_adjustment=semantic,
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.rank_score,
            -item.median_area_ratio,
            -item.center_coverage_ratio,
            item.candidate.kind,
            item.candidate.xpath,
        )
    )
    return ranked
