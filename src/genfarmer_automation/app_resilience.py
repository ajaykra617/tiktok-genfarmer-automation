"""Checkpoint-safe recovery helpers for TikTok workflow stages.

This module is intentionally stricter than a generic retry loop. A caller must
opt in to replaying a whole stage after a clean TikTok process restart. That is
appropriate for passive, checkpointed stages such as warm scrolling, profile or
comments excursions, and Explore preparation where restarting the app returns
the workflow to a known feed checkpoint.

It must not be used to blindly replay final publishing, purchases, messages, or
other mutations whose completion could be ambiguous after a timeout.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from .runtime_recovery import RecoveryAction, classify_error


T = TypeVar("T")


@dataclass(frozen=True)
class StageRecoveryEvent:
    label: str
    restart_number: int
    reason: str


_RESTART_WORTHY_MARKERS = (
    "qualified fyp anchor is absent",
    "qualified fyp could not be restored",
    "qualified for you bootstrap did not reach pass",
    "for you tap did not retain qualified fyp",
    "no healthy hierarchy source",
    "hierarchy source unavailable",
    "creator profile context was not semantically proven",
    "comments context was not semantically proven",
    "tiktok became unhealthy",
    "foreground recovery failed",
    "app-not-responding",
    "boost explore did not reach pass",
)


def restart_worthy_failure(error: BaseException | str) -> bool:
    """Return whether one checkpoint-level app restart is a reasonable recovery.

    Classified transport/runtime failures are eligible. A small explicit list of
    stage postcondition failures is also eligible because those stages are
    passive and the caller restarts back to a known checkpoint before replay.
    Unknown semantic failures remain non-retryable.
    """
    text = str(error)
    decision = classify_error(text)
    if decision.action in {
        RecoveryAction.RETRY_HIERARCHY,
        RecoveryAction.RETRY_ADB,
        RecoveryAction.RESTART_APP,
        RecoveryAction.RESTORE_FOREGROUND,
    }:
        return True
    normalized = text.casefold()
    return any(marker in normalized for marker in _RESTART_WORTHY_MARKERS)


def run_checkpointed_stage(
    label: str,
    operation: Callable[[], T],
    *,
    restart: Callable[[str], None],
    max_restarts: int = 1,
    on_recovery: Callable[[StageRecoveryEvent], None] | None = None,
) -> T:
    """Run one explicitly checkpoint-safe stage with bounded clean restarts."""
    if not isinstance(label, str) or not label.strip():
        raise ValueError("stage label must be a non-empty string")
    if not 0 <= max_restarts <= 5:
        raise ValueError("max_restarts must be between 0 and 5")

    restarts = 0
    while True:
        try:
            return operation()
        except Exception as exc:
            if restarts >= max_restarts or not restart_worthy_failure(exc):
                raise
            restarts += 1
            reason = str(exc) or exc.__class__.__name__
            restart(f"{label}: {reason}")
            event = StageRecoveryEvent(label=label, restart_number=restarts, reason=reason)
            if on_recovery is not None:
                on_recovery(event)
