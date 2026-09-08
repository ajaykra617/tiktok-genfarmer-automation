"""TikTok-specific coarse runtime recovery helpers.

This layer is intentionally conservative: it only proves/recovers foreground
state for the already-qualified TikTok package/component. Selector-level feed
readiness and popup handling remain separate later gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time
from typing import Protocol

from .adb_actions import AdbActions
from .adb_observer import AdbObserver, DeviceObservation, InterruptKind, TIKTOK_PACKAGE

TIKTOK_LAUNCHER_ACTIVITY = "com.ss.android.ugc.aweme.splash.SplashActivity"
TIKTOK_COMPONENT = f"{TIKTOK_PACKAGE}/{TIKTOK_LAUNCHER_ACTIVITY}"


class ForegroundDecision(str, Enum):
    READY = "ready"
    NEEDS_LAUNCH = "needs_launch"
    BLOCKED_INTERRUPT = "blocked_interrupt"
    DEVICE_UNAVAILABLE = "device_unavailable"


@dataclass(frozen=True)
class ForegroundPlan:
    decision: ForegroundDecision
    reason: str


@dataclass(frozen=True)
class EnsureForegroundResult:
    success: bool
    attempts: int
    initial: DeviceObservation
    final: DeviceObservation
    reason: str


class ObserverLike(Protocol):
    def observe(self) -> DeviceObservation: ...


class ActionsLike(Protocol):
    def launch_component(self, component: str): ...


def plan_foreground(observation: DeviceObservation) -> ForegroundPlan:
    if observation.adb_state != "device" or observation.interrupt is InterruptKind.DEVICE_OFFLINE:
        return ForegroundPlan(ForegroundDecision.DEVICE_UNAVAILABLE, "ADB device is not ready")
    if observation.interrupt is not InterruptKind.NONE:
        return ForegroundPlan(
            ForegroundDecision.BLOCKED_INTERRUPT,
            f"known interrupt is foreground: {observation.interrupt.value}",
        )
    if observation.tiktok_foreground:
        return ForegroundPlan(ForegroundDecision.READY, "TikTok is already foreground")
    return ForegroundPlan(
        ForegroundDecision.NEEDS_LAUNCH,
        "TikTok is not foreground; relaunch from the qualified component checkpoint",
    )


class TikTokRuntime:
    def __init__(
        self,
        device: str,
        *,
        observer: ObserverLike | None = None,
        actions: ActionsLike | None = None,
        settle_seconds: float = 1.0,
        poll_seconds: float = 0.5,
        max_polls: int = 8,
    ) -> None:
        if settle_seconds < 0 or poll_seconds < 0:
            raise ValueError("settle/poll seconds must be >= 0")
        if max_polls < 1:
            raise ValueError("max_polls must be >= 1")
        self.device = device
        self.observer = observer or AdbObserver(device)
        self.actions = actions or AdbActions(device)
        self.settle_seconds = settle_seconds
        self.poll_seconds = poll_seconds
        self.max_polls = max_polls

    def ensure_foreground(self) -> EnsureForegroundResult:
        initial = self.observer.observe()
        plan = plan_foreground(initial)
        if plan.decision is ForegroundDecision.READY:
            return EnsureForegroundResult(True, 0, initial, initial, plan.reason)
        if plan.decision is not ForegroundDecision.NEEDS_LAUNCH:
            return EnsureForegroundResult(False, 0, initial, initial, plan.reason)

        self.actions.launch_component(TIKTOK_COMPONENT)
        attempts = 1
        if self.settle_seconds:
            time.sleep(self.settle_seconds)

        final = initial
        for index in range(self.max_polls):
            final = self.observer.observe()
            current = plan_foreground(final)
            if current.decision is ForegroundDecision.READY:
                return EnsureForegroundResult(True, attempts, initial, final, "TikTok foreground proven after relaunch")
            if current.decision in {ForegroundDecision.BLOCKED_INTERRUPT, ForegroundDecision.DEVICE_UNAVAILABLE}:
                return EnsureForegroundResult(False, attempts, initial, final, current.reason)
            if index + 1 < self.max_polls and self.poll_seconds:
                time.sleep(self.poll_seconds)

        return EnsureForegroundResult(
            False,
            attempts,
            initial,
            final,
            "TikTok foreground was not proven before the bounded recovery poll budget expired",
        )
