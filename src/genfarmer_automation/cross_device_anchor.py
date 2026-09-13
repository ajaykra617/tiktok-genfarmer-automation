"""Evaluate already-qualified feed-anchor candidates on another Android device.

This module is deliberately read-only and selector-value agnostic at the reporting
boundary.  It evaluates the exact private candidates against hierarchy XML and
returns source-rank/count metadata so callers can choose the best selector that
survives across devices without printing the selector itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .feed_anchor_variation import candidate_counts
from .ui_xml import SelectorCandidate


@dataclass(frozen=True)
class CrossDeviceCandidateResult:
    source_rank: int
    kind: str
    counts: tuple[int, ...]
    passed: bool


def evaluate_cross_device_candidates(
    candidates: Iterable[SelectorCandidate],
    xml_snapshots: Iterable[str],
    *,
    package: str | None = None,
) -> list[CrossDeviceCandidateResult]:
    """Evaluate every candidate against all target-device hierarchy snapshots.

    ``source_rank`` is 1-based and preserves the original ranking order.  A
    candidate passes only when it appears exactly once in every target snapshot.
    """
    items = list(candidates)
    snapshots = list(xml_snapshots)
    if not items:
        raise ValueError("no selector candidates were supplied")
    if len(snapshots) < 2:
        raise ValueError("at least two target-device hierarchy snapshots are required")

    out: list[CrossDeviceCandidateResult] = []
    for index, candidate in enumerate(items, start=1):
        counts = candidate_counts(candidate, snapshots, package=package)
        passed = bool(counts) and all(count == 1 for count in counts)
        out.append(
            CrossDeviceCandidateResult(
                source_rank=index,
                kind=candidate.kind,
                counts=counts,
                passed=passed,
            )
        )
    return out


def survivor_ranks(results: Iterable[CrossDeviceCandidateResult]) -> tuple[int, ...]:
    """Return surviving source ranks in original ranking order."""
    return tuple(item.source_rank for item in results if item.passed)
