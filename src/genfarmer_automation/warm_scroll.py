"""Pure planning helpers for short passive TikTok warm-scroll preparation."""
from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Mapping


class WarmScrollError(ValueError):
    pass


_TRANSIENT_HIERARCHY_REASON = "no healthy hierarchy source after helper-service recovery"
_TRANSIENT_FYP_RECOVERY_REASON = (
    "qualified For You feed could not be restored with bounded semantic/BACK recovery; last counts=None"
)


@dataclass(frozen=True)
class WarmScrollPlan:
    videos: int
    watch_seconds: tuple[float, ...]
    seed: int
    max_session_seconds: float


def build_warm_scroll_plan(
    *,
    videos: int,
    watch_min_seconds: float,
    watch_max_seconds: float,
    seed: int,
    max_session_minutes: float,
) -> WarmScrollPlan:
    if not 1 <= int(videos) <= 20:
        raise WarmScrollError("videos must be 1..20")
    if watch_min_seconds < 0 or watch_max_seconds < watch_min_seconds:
        raise WarmScrollError("watch interval bounds are invalid")
    if not 0 < max_session_minutes <= 15:
        raise WarmScrollError("max_session_minutes must be >0 and <=15")

    rng = random.Random(int(seed))
    schedule = tuple(round(rng.uniform(watch_min_seconds, watch_max_seconds), 2) for _ in range(int(videos)))
    return WarmScrollPlan(
        videos=int(videos),
        watch_seconds=schedule,
        seed=int(seed),
        max_session_seconds=float(max_session_minutes) * 60.0,
    )


def is_transient_bootstrap_failure(payload: Mapping[str, Any] | None) -> bool:
    """Return True only for hierarchy-unavailable FYP bootstrap failures.

    A retry is not allowed for semantic selector failures, missing controls, or
    other UI mismatches. Live GF#7 qualification has shown the helper/uiautomator
    hierarchy sources can briefly be unavailable and then recover immediately.
    """
    if not isinstance(payload, Mapping) or payload.get("status") != "BLOCKED":
        return False
    reason = payload.get("reason")
    if not isinstance(reason, str):
        return False
    return _TRANSIENT_HIERARCHY_REASON in reason or _TRANSIENT_FYP_RECOVERY_REASON in reason
