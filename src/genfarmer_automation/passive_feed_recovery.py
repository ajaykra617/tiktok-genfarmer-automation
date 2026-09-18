"""Non-replay recovery for passive feed-advance mutations.

A timed-out swipe may already have executed, so it is never sent twice. When
the ADB transport is positively healthy, a passive warm-up workflow may instead
reset the app to its already-qualified feed checkpoint and prove that checkpoint
before continuing to the next watch interval. This is intentionally limited to
passive feed navigation; callers for publishing/messages/purchases must not use it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from .adb_actions import AdbActionError
from .mutation_recovery import healthy_transport_ambiguous_mutation


T = TypeVar("T")


@dataclass(frozen=True)
class PassiveFeedAdvanceResult:
    recovered_via_checkpoint: bool
    reason: str | None


def run_passive_feed_advance(
    swipe: Callable[[], T],
    *,
    reset_checkpoint: Callable[[str], None],
    prove_checkpoint: Callable[[], object],
) -> PassiveFeedAdvanceResult:
    """Run one swipe or recover via checkpoint without replaying the swipe."""
    try:
        swipe()
    except AdbActionError as exc:
        if not healthy_transport_ambiguous_mutation(exc):
            raise
        reason = str(exc) or "ambiguous feed swipe on healthy ADB transport"
        reset_checkpoint(reason)
        prove_checkpoint()
        return PassiveFeedAdvanceResult(True, reason)
    return PassiveFeedAdvanceResult(False, None)
