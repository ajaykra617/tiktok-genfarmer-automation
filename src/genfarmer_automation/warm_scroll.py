"""Pure planning helpers for short passive TikTok warm-scroll preparation."""
from __future__ import annotations

from dataclasses import dataclass
import random


class WarmScrollError(ValueError):
    pass


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
