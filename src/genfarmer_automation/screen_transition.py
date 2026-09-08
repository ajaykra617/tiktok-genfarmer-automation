"""Conservative before/after screen transition evidence.

This module is deliberately stricter than a normal screenshot diff. It uses only
screen points that were temporally stable before an action, then asks whether a
meaningful fraction of those points stayed different across an entire post-action
window. A transition is only *proven* when the baseline is trustworthy and the
change is spatially distributed.

Visual evidence is secondary evidence. Callers must still prove foreground and
interrupt state separately, and selector/accessibility evidence should replace or
augment this signal whenever a stable native selector is available.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import median
from typing import Iterable, Sequence

from .screen_state import GridPoint, RawScreenFrame, ScreenStateError, sampling_grid


class TransitionDecision(str, Enum):
    PROVEN_CHANGED = "proven_changed"
    INCONCLUSIVE_BASELINE = "inconclusive_baseline"
    INCONCLUSIVE_CHANGE = "inconclusive_change"


@dataclass(frozen=True)
class TransitionReport:
    decision: TransitionDecision
    total_points: int
    baseline_stable_points: int
    baseline_stable_ratio: float
    changed_points: int
    changed_ratio_of_stable: float
    changed_cells: int
    occupied_cells: int
    stable_range_threshold: int
    changed_delta_threshold: int
    reason: str


def _validate_frames(frames: Sequence[RawScreenFrame], *, label: str) -> RawScreenFrame:
    if len(frames) < 2:
        raise ValueError(f"{label} requires at least two frames")
    first = frames[0]
    signature = (first.width, first.height, first.pixel_format)
    if any((f.width, f.height, f.pixel_format) != signature for f in frames):
        raise ScreenStateError(f"{label} screen geometry/pixel format changed during sampling")
    return first


def _range(colors: Sequence[tuple[int, int, int]]) -> int:
    return max(max(c[i] for c in colors) - min(c[i] for c in colors) for i in range(3))


def _median_color(colors: Sequence[tuple[int, int, int]]) -> tuple[int, int, int]:
    return tuple(int(median([c[i] for c in colors])) for i in range(3))  # type: ignore[return-value]


def _delta(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return max(abs(a[i] - b[i]) for i in range(3))


def assess_visual_transition(
    before_frames: Sequence[RawScreenFrame],
    after_frames: Sequence[RawScreenFrame],
    *,
    points: Iterable[GridPoint] | None = None,
    stable_range_threshold: int = 16,
    changed_delta_threshold: int = 40,
    min_baseline_stable_ratio: float = 0.50,
    min_changed_ratio: float = 0.15,
    cell_columns: int = 4,
    cell_rows: int = 6,
    min_changed_cells: int = 4,
) -> TransitionReport:
    """Assess whether a screen transition is conservatively proven.

    A sample point is eligible only when its RGB range across the complete
    pre-action window is at most ``stable_range_threshold``. It is counted as
    changed only when *every* post-action frame differs from the baseline median
    color by at least ``changed_delta_threshold``. Requiring persistence across
    the post window rejects many animation-only spikes.
    """
    before = _validate_frames(before_frames, label="before_frames")
    after = _validate_frames(after_frames, label="after_frames")
    if (before.width, before.height, before.pixel_format) != (
        after.width,
        after.height,
        after.pixel_format,
    ):
        raise ScreenStateError("before/after screen geometry or pixel format differs")
    if not (0 <= stable_range_threshold <= 255 and 0 <= changed_delta_threshold <= 255):
        raise ValueError("thresholds must be 0..255")
    if not (0.0 <= min_baseline_stable_ratio <= 1.0 and 0.0 <= min_changed_ratio <= 1.0):
        raise ValueError("ratios must be 0..1")
    if cell_columns < 1 or cell_rows < 1 or min_changed_cells < 1:
        raise ValueError("cell dimensions/min_changed_cells must be positive")

    sample_points = list(points or sampling_grid(before.width, before.height))
    stable_points: list[tuple[GridPoint, tuple[int, int, int]]] = []
    for point in sample_points:
        colors = [frame.rgb_at(point.x, point.y) for frame in before_frames]
        if _range(colors) <= stable_range_threshold:
            stable_points.append((point, _median_color(colors)))

    total = len(sample_points)
    stable_count = len(stable_points)
    stable_ratio = stable_count / total if total else 0.0
    if stable_ratio < min_baseline_stable_ratio or stable_count == 0:
        return TransitionReport(
            TransitionDecision.INCONCLUSIVE_BASELINE,
            total,
            stable_count,
            stable_ratio,
            0,
            0.0,
            0,
            0,
            stable_range_threshold,
            changed_delta_threshold,
            "not enough temporally stable baseline area to trust visual transition evidence",
        )

    changed: list[GridPoint] = []
    for point, baseline in stable_points:
        post_colors = [frame.rgb_at(point.x, point.y) for frame in after_frames]
        if min(_delta(baseline, color) for color in post_colors) >= changed_delta_threshold:
            changed.append(point)

    changed_count = len(changed)
    changed_ratio = changed_count / stable_count if stable_count else 0.0

    occupied: set[tuple[int, int]] = set()
    changed_cell_set: set[tuple[int, int]] = set()
    for point, _ in stable_points:
        cx = min(cell_columns - 1, int(point.x * cell_columns / before.width))
        cy = min(cell_rows - 1, int(point.y * cell_rows / before.height))
        occupied.add((cx, cy))
    for point in changed:
        cx = min(cell_columns - 1, int(point.x * cell_columns / before.width))
        cy = min(cell_rows - 1, int(point.y * cell_rows / before.height))
        changed_cell_set.add((cx, cy))

    if changed_ratio >= min_changed_ratio and len(changed_cell_set) >= min_changed_cells:
        decision = TransitionDecision.PROVEN_CHANGED
        reason = "persistent visual change is large enough and spatially distributed"
    else:
        decision = TransitionDecision.INCONCLUSIVE_CHANGE
        reason = "visual change did not meet the conservative ratio/spatial-coverage gate"

    return TransitionReport(
        decision,
        total,
        stable_count,
        stable_ratio,
        changed_count,
        changed_ratio,
        len(changed_cell_set),
        len(occupied),
        stable_range_threshold,
        changed_delta_threshold,
        reason,
    )
