"""Primary TikTok feed-selector gate used around short GenFarmer actions.

The gate is intentionally independent of GenFarmer node return values. It checks
that a previously-qualified selector appears exactly once in every fresh Android
hierarchy snapshot. This makes the application-level pre/postcondition explicit
and fail-closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .feed_anchor_variation import candidate_counts
from .ui_xml import SelectorCandidate


@dataclass(frozen=True)
class SelectorGateReport:
    counts: tuple[int, ...]
    passed: bool


def assess_selector_gate(
    candidate: SelectorCandidate,
    xml_snapshots: Iterable[str],
    *,
    package: str | None = None,
) -> SelectorGateReport:
    snapshots = list(xml_snapshots)
    if len(snapshots) < 2:
        raise ValueError("selector gate requires at least two hierarchy snapshots")
    counts = candidate_counts(candidate, snapshots, package=package)
    return SelectorGateReport(counts=counts, passed=bool(counts) and all(count == 1 for count in counts))
