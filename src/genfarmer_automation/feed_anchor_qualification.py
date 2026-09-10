"""Two-sided qualification helpers for a TikTok feed-anchor selector.

Positive candidates are learned from repeated normal-feed hierarchy snapshots.
A candidate is only promoted if it is absent from repeated hierarchy snapshots
captured on a known non-feed screen. Exact XPath values remain local/private.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .ui_xml import SelectorCandidate, filter_against_negative_xml


class FeedAnchorQualificationError(ValueError):
    pass


def candidate_from_dict(value: Mapping[str, Any]) -> SelectorCandidate:
    try:
        kind = str(value["kind"])
        xpath = str(value["xpath"])
        class_name_raw = value.get("class_name")
        class_name = str(class_name_raw) if class_name_raw is not None else None
        occurrences_raw = value["occurrences"]
        if not isinstance(occurrences_raw, (list, tuple)):
            raise TypeError("occurrences")
        occurrences = tuple(int(item) for item in occurrences_raw)
        present_in_all = bool(value["present_in_all"])
        unique_in_all = bool(value["unique_in_all"])
        score = int(value["score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FeedAnchorQualificationError("invalid selector candidate payload") from exc

    if not kind or not xpath.strip() or not occurrences:
        raise FeedAnchorQualificationError("selector candidate is missing required values")
    return SelectorCandidate(
        kind=kind,
        xpath=xpath,
        class_name=class_name,
        occurrences=occurrences,
        present_in_all=present_in_all,
        unique_in_all=unique_in_all,
        score=score,
    )


def candidates_from_payload(payload: Any) -> list[SelectorCandidate]:
    if not isinstance(payload, list):
        raise FeedAnchorQualificationError("candidate payload must be a list")
    return [candidate_from_dict(item) for item in payload if isinstance(item, Mapping)]


def qualify_against_negative_xml(
    candidates: Iterable[SelectorCandidate],
    negative_snapshots: Iterable[str],
    *,
    package: str | None = None,
) -> list[SelectorCandidate]:
    """Keep only positive candidates absent from every negative snapshot."""
    positive = list(candidates)
    if not positive:
        raise FeedAnchorQualificationError("no positive selector candidates were supplied")
    negative = list(negative_snapshots)
    if len(negative) < 2:
        raise FeedAnchorQualificationError("at least two negative snapshots are required")
    return filter_against_negative_xml(positive, negative, package=package)
