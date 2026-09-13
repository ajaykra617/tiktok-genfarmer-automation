"""Policy helpers for one bounded TikTok warm-up browse step.

The runtime prefers strong selector evidence and GenFarmer execution, but a
single browse step must not become unusable merely because the read-only UI
hierarchy helper or GenFarmer run-creation endpoint is temporarily unhealthy.

Fallbacks are deliberately narrow:
- hierarchy failure may degrade verification only to TikTok foreground/no-
  interrupt continuity for the swipe-only browse primitive;
- ADB action fallback is allowed only before a GenFarmer execute request has
  been sent, preventing duplicate swipes after an ambiguous execution error.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VerificationLevel(str, Enum):
    FULL_SELECTOR = "full_selector"
    FOREGROUND_CONTINUITY = "foreground_continuity"


class ActionBackend(str, Enum):
    GENFARMER = "genfarmer"
    ADB_FALLBACK = "adb_fallback"


class ExecutionPhase(str, Enum):
    BEFORE_RUN_CREATE = "before_run_create"
    RUN_CREATE_FAILED = "run_create_failed"
    RUN_CREATED = "run_created"
    EXECUTE_REQUEST_SENT = "execute_request_sent"


@dataclass(frozen=True)
class VerificationDecision:
    level: VerificationLevel
    selector_pre: bool
    selector_post: bool


def choose_verification_level(
    *,
    selector_pre: bool | None,
    selector_post: bool | None,
    foreground_pre: bool,
    foreground_post: bool,
) -> VerificationDecision:
    """Classify post-step evidence without overstating degraded evidence."""
    if selector_pre is True and selector_post is True:
        return VerificationDecision(VerificationLevel.FULL_SELECTOR, True, True)
    if foreground_pre and foreground_post:
        return VerificationDecision(
            VerificationLevel.FOREGROUND_CONTINUITY,
            selector_pre is True,
            selector_post is True,
        )
    raise RuntimeError("warm-up step postcondition was not proven")


def adb_fallback_allowed(phase: ExecutionPhase) -> bool:
    """Allow direct ADB fallback only before execution can be ambiguous."""
    return phase in {
        ExecutionPhase.BEFORE_RUN_CREATE,
        ExecutionPhase.RUN_CREATE_FAILED,
    }
