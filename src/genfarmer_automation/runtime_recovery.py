"""Shared runtime failure classification for bounded Android/TikTok recovery.

This module deliberately separates *classification* from *mutation*. Callers
may use the returned recovery action to decide whether a read-only retry,
foreground restore, or bounded app restart is appropriate. Semantic/UI
failures that are not positively recognized remain fail-closed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from .adb_observer import DeviceObservation, InterruptKind


class RuntimeFailureKind(str, Enum):
    HEALTHY = "healthy"
    APP_HUNG = "app_hung"
    HIERARCHY_TEMPORARY = "hierarchy_temporarily_unavailable"
    ADB_TRANSIENT = "adb_transient"
    UI_STATE_RECOVERABLE = "ui_state_recoverable"
    DEVICE_UNAVAILABLE = "device_unavailable"
    AUTOMATION_FAILURE = "automation_failure"


class RecoveryAction(str, Enum):
    NONE = "none"
    RESTART_APP = "restart_app"
    RETRY_HIERARCHY = "retry_hierarchy"
    RETRY_ADB = "retry_adb"
    RESTORE_FOREGROUND = "restore_foreground"
    RECOVER_PERMISSION = "recover_permission"
    FAIL = "fail"


@dataclass(frozen=True)
class RecoveryDecision:
    kind: RuntimeFailureKind
    action: RecoveryAction
    retryable: bool
    reason: str


@dataclass(frozen=True)
class RecoveryLimits:
    app_restarts: int = 1
    hierarchy_retries: int = 1
    adb_retries: int = 1
    foreground_restores: int = 1
    permission_recoveries: int = 1

    def __post_init__(self) -> None:
        for value in (
            self.app_restarts,
            self.hierarchy_retries,
            self.adb_retries,
            self.foreground_restores,
            self.permission_recoveries,
        ):
            if value < 0:
                raise ValueError("recovery limits must be >= 0")


@dataclass
class RecoveryBudget:
    limits: RecoveryLimits = field(default_factory=RecoveryLimits)
    used: dict[RecoveryAction, int] = field(default_factory=dict)

    def limit_for(self, action: RecoveryAction) -> int:
        return {
            RecoveryAction.RESTART_APP: self.limits.app_restarts,
            RecoveryAction.RETRY_HIERARCHY: self.limits.hierarchy_retries,
            RecoveryAction.RETRY_ADB: self.limits.adb_retries,
            RecoveryAction.RESTORE_FOREGROUND: self.limits.foreground_restores,
            RecoveryAction.RECOVER_PERMISSION: self.limits.permission_recoveries,
        }.get(action, 0)

    def can_attempt(self, decision: RecoveryDecision) -> bool:
        if not decision.retryable:
            return False
        return self.used.get(decision.action, 0) < self.limit_for(decision.action)

    def consume(self, decision: RecoveryDecision) -> bool:
        if not self.can_attempt(decision):
            return False
        self.used[decision.action] = self.used.get(decision.action, 0) + 1
        return True

    def snapshot(self) -> dict[str, int]:
        return {action.value: count for action, count in self.used.items()}


_HIERARCHY_MARKERS = (
    "no healthy hierarchy source after helper-service recovery",
    "uiautomator dump failed",
    "helper returned invalid hierarchy",
    "helper response did not contain hierarchy xml",
)

_ADB_TRANSIENT_MARKERS = (
    "adb command timed out",
    "adb action timed out",
    "device offline",
    "device unauthorized",
    "no devices/emulators found",
    "transport error",
    "transport closed",
    "connection closed",
)


def classify_observation(observation: DeviceObservation) -> RecoveryDecision:
    if observation.adb_state != "device" or observation.interrupt is InterruptKind.DEVICE_OFFLINE:
        return RecoveryDecision(
            RuntimeFailureKind.DEVICE_UNAVAILABLE,
            RecoveryAction.FAIL,
            False,
            "ADB device is not ready",
        )
    if observation.interrupt is InterruptKind.APP_NOT_RESPONDING:
        return RecoveryDecision(
            RuntimeFailureKind.APP_HUNG,
            RecoveryAction.RESTART_APP,
            True,
            "TikTok/Android reported an app-not-responding state",
        )
    if observation.interrupt is InterruptKind.ANDROID_PERMISSION_DIALOG:
        return RecoveryDecision(
            RuntimeFailureKind.UI_STATE_RECOVERABLE,
            RecoveryAction.RECOVER_PERMISSION,
            True,
            "Android permission dialog is foreground",
        )
    if observation.interrupt is not InterruptKind.NONE:
        return RecoveryDecision(
            RuntimeFailureKind.AUTOMATION_FAILURE,
            RecoveryAction.FAIL,
            False,
            f"unsupported foreground interrupt: {observation.interrupt.value}",
        )
    if not observation.tiktok_foreground:
        return RecoveryDecision(
            RuntimeFailureKind.UI_STATE_RECOVERABLE,
            RecoveryAction.RESTORE_FOREGROUND,
            True,
            "TikTok is not foreground but no blocking interrupt is present",
        )
    return RecoveryDecision(
        RuntimeFailureKind.HEALTHY,
        RecoveryAction.NONE,
        False,
        "TikTok foreground/no-interrupt state is healthy",
    )


def classify_error(error: BaseException | str) -> RecoveryDecision:
    text = str(error).strip()
    lowered = text.casefold()

    if any(marker in lowered for marker in _HIERARCHY_MARKERS):
        return RecoveryDecision(
            RuntimeFailureKind.HIERARCHY_TEMPORARY,
            RecoveryAction.RETRY_HIERARCHY,
            True,
            text or "hierarchy source temporarily unavailable",
        )

    if any(marker in lowered for marker in _ADB_TRANSIENT_MARKERS):
        return RecoveryDecision(
            RuntimeFailureKind.ADB_TRANSIENT,
            RecoveryAction.RETRY_ADB,
            True,
            text or "ADB transport temporarily unavailable",
        )

    # ANR strings vary substantially by Android build/locale. Framework markers
    # such as APP_NOT_RESPONDING are preferred; generic "not responding" remains
    # useful when it comes from our normalized observer/recovery messages.
    if "app_not_responding" in lowered or "application not responding" in lowered or "not responding" in lowered:
        return RecoveryDecision(
            RuntimeFailureKind.APP_HUNG,
            RecoveryAction.RESTART_APP,
            True,
            text or "application is not responding",
        )

    return RecoveryDecision(
        RuntimeFailureKind.AUTOMATION_FAILURE,
        RecoveryAction.FAIL,
        False,
        text or "unclassified automation failure",
    )


def decision_to_dict(decision: RecoveryDecision) -> Mapping[str, object]:
    return {
        "kind": decision.kind.value,
        "action": decision.action.value,
        "retryable": decision.retryable,
        "reason": decision.reason,
    }
