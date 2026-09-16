"""Deterministic plan builder for the live TikTok client demo.

The demo deliberately randomizes the order of passive warm-up features so the
operator does not present a fixed chronological pattern.  The plan contains no
likes, follows, replies, DMs, account creation, or publishing actions.
"""
from __future__ import annotations

from dataclasses import dataclass
import random


PASSIVE_DEMO_FEATURES = ("profile", "comments", "keyword", "hashtag")


@dataclass(frozen=True)
class ClientDemoPlan:
    seed: int
    feature_order: tuple[str, ...]
    watch_seconds: tuple[float, ...]


def build_client_demo_plan(
    *,
    seed: int,
    videos: int = 3,
    watch_min_seconds: float = 4.0,
    watch_max_seconds: float = 7.0,
) -> ClientDemoPlan:
    if not 1 <= videos <= 20:
        raise ValueError("videos must be between 1 and 20")
    if watch_min_seconds < 0 or watch_max_seconds < watch_min_seconds:
        raise ValueError("invalid watch interval")
    if watch_max_seconds > 60:
        raise ValueError("demo watch interval must not exceed 60 seconds")

    rng = random.Random(seed)
    features = list(PASSIVE_DEMO_FEATURES)
    rng.shuffle(features)
    watches = tuple(round(rng.uniform(watch_min_seconds, watch_max_seconds), 2) for _ in range(videos))
    return ClientDemoPlan(seed=seed, feature_order=tuple(features), watch_seconds=watches)
