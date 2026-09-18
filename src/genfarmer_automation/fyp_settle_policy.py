"""Timing policy for conservative TikTok FYP loading settles."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FypSettlePolicy:
    checks: int
    interval_seconds: float
    stable_observations: int


def settle_policy(*, post_restart: bool) -> FypSettlePolicy:
    """Return bounded read-only settle timing for the current checkpoint.

    Normal feed advances get more time than the original ~1.2s window because
    slower physical devices can expose the For You shell before the next card
    publishes accessibility nodes. Post-restart keeps the longer existing
    settle budget.
    """
    if post_restart:
        return FypSettlePolicy(checks=15, interval_seconds=1.0, stable_observations=3)
    return FypSettlePolicy(checks=8, interval_seconds=0.75, stable_observations=2)
