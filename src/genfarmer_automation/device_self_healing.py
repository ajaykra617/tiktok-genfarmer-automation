"""Persistent, non-reboot self-healing policy for unreliable Android devices.

The fleet-level worker may keep trying a device indefinitely, but every recovery
cycle remains bounded. This module deliberately has no reboot primitive. Reboot
is an external/client-approval boundary and is represented only as a recommendation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DeviceWorkerState(str, Enum):
    READY = "ready"
    RUNNING = "running"
    APP_RECOVERY = "app_recovery"
    COOLDOWN = "cooldown"
    REBOOT_APPROVAL_RECOMMENDED = "reboot_approval_recommended"
    COMPLETE = "complete"


@dataclass(frozen=True)
class SelfHealingPolicy:
    cooldown_seconds: tuple[float, ...] = (2.0, 5.0, 10.0, 20.0, 30.0, 60.0)
    reboot_recommend_after: int = 3

    def __post_init__(self) -> None:
        if not self.cooldown_seconds:
            raise ValueError("cooldown_seconds must not be empty")
        if any(value < 0 or value > 3600 for value in self.cooldown_seconds):
            raise ValueError("cooldown values must be between 0 and 3600 seconds")
        if self.reboot_recommend_after < 1:
            raise ValueError("reboot_recommend_after must be >= 1")

    def cooldown_for_failure(self, consecutive_failures: int) -> float:
        if consecutive_failures < 1:
            raise ValueError("consecutive_failures must be >= 1")
        index = min(consecutive_failures - 1, len(self.cooldown_seconds) - 1)
        return float(self.cooldown_seconds[index])

    def reboot_approval_recommended(self, consecutive_failures: int) -> bool:
        return consecutive_failures >= self.reboot_recommend_after


def retryable_client_failure(reason: str | None) -> bool:
    """Return whether the passive/pre-publish client demo may start a fresh cycle.

    The worker wraps only the passive Warm-up + READY_FOR_PUBLISH preparation
    demo. It never wraps a final publishing action, so a fresh cycle begins from
    the qualified feed checkpoint rather than replaying a consequential action.
    """
    if not isinstance(reason, str) or not reason.strip():
        return True
    lowered = reason.casefold()
    nonretryable = (
        "media file does not exist",
        "candidate file does not contain requested candidate",
        "--dwell must be",
        "invalid",
    )
    return not any(marker in lowered for marker in nonretryable)
