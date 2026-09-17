"""Shared bounded runtime supervision for authorized TikTok automation.

The supervisor centralizes recovery policy without making workflow decisions.
Read-only observation/hierarchy operations may be retried when positively
classified as transient. UI mutations are never replayed by this module.

Recovery remains intentionally bounded:
- permission dialogs: one qualified recovery by default;
- TikTok background/ANR: bounded foreground restore or process restart;
- hierarchy and read-only ADB failures: bounded read-only retries;
- explicit hard restart: force-stop only TikTok, relaunch the qualified
  component, and prove healthy foreground state again;
- unknown semantic/UI failures: fail closed.

A hard restart is intentionally not a generic retry mechanism. Callers may use
it only at a known workflow checkpoint where replay is safe. It never clears
TikTok data/cache, never reinstalls the app, and never kills unrelated apps.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable, TypeVar

from .adb_observer import AdbObserver, TIKTOK_PACKAGE
from .permission_recovery import recover_tiktok_permission_dialog
from .runtime_recovery import (
    RecoveryAction,
    RecoveryBudget,
    RecoveryDecision,
    RuntimeFailureKind,
    classify_error,
    classify_observation,
)
from .tiktok_runtime import TikTokRuntime


class RuntimeSupervisorError(RuntimeError):
    pass


T = TypeVar("T")


@dataclass(frozen=True)
class RuntimeSupervisorSnapshot:
    recovery_budget_used: dict[str, int]


class TikTokRuntimeSupervisor:
    def __init__(
        self,
        device: str,
        *,
        observer: Any | None = None,
        actions: Any | None = None,
        budget: RecoveryBudget | None = None,
        permission_recoverer: Callable[..., Any] | None = None,
        runtime_factory: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        retry_sleep_seconds: float = 0.75,
    ) -> None:
        if retry_sleep_seconds < 0:
            raise ValueError("retry_sleep_seconds must be >= 0")
        self.device = device
        self.observer = observer or AdbObserver(device)
        self.actions = actions
        self.budget = budget or RecoveryBudget()
        self.permission_recoverer = permission_recoverer or recover_tiktok_permission_dialog
        self.runtime_factory = runtime_factory or TikTokRuntime
        self.sleeper = sleeper
        self.retry_sleep_seconds = retry_sleep_seconds

    def snapshot(self) -> RuntimeSupervisorSnapshot:
        return RuntimeSupervisorSnapshot(self.budget.snapshot())

    def _observe_with_retry(self):
        while True:
            try:
                return self.observer.observe()
            except Exception as exc:
                decision = classify_error(exc)
                if decision.action is not RecoveryAction.RETRY_ADB or not self.budget.consume(decision):
                    raise RuntimeSupervisorError(str(exc) or "ADB observation failed") from exc
                if self.retry_sleep_seconds:
                    self.sleeper(self.retry_sleep_seconds)

    def ensure_ready(self, *, apply: bool = True) -> None:
        """Prove healthy TikTok foreground, applying only bounded known recovery."""
        for _ in range(4):
            observation = self._observe_with_retry()
            decision = classify_observation(observation)
            if decision.kind is RuntimeFailureKind.HEALTHY:
                return
            if not apply:
                raise RuntimeSupervisorError(decision.reason)
            if not self.budget.consume(decision):
                raise RuntimeSupervisorError(
                    f"runtime recovery budget exhausted or failure is not retryable: {decision.reason}"
                )

            if decision.action is RecoveryAction.RECOVER_PERMISSION:
                recovered = self.permission_recoverer(self.device, observer=self.observer)
                if not getattr(recovered, "success", False):
                    reason = getattr(recovered, "reason", "permission recovery failed")
                    raise RuntimeSupervisorError(f"permission recovery failed: {reason}")
                continue

            if decision.action in {RecoveryAction.RESTORE_FOREGROUND, RecoveryAction.RESTART_APP}:
                kwargs = {"observer": self.observer}
                if self.actions is not None:
                    kwargs["actions"] = self.actions
                recovered = self.runtime_factory(self.device, **kwargs).ensure_foreground()
                if not getattr(recovered, "success", False):
                    reason = getattr(recovered, "reason", "TikTok runtime recovery failed")
                    raise RuntimeSupervisorError(f"TikTok runtime recovery failed: {reason}")
                continue

            raise RuntimeSupervisorError(decision.reason)

        raise RuntimeSupervisorError("TikTok healthy runtime state was not proven within the recovery loop budget")

    def hard_restart(self, *, reason: str, settle_seconds: float = 1.5) -> None:
        """Perform one budgeted clean TikTok process restart from a checkpoint.

        `am force-stop` terminates TikTok's process, allowing Android to reclaim
        that app's private memory. We deliberately do not run global RAM cleaners,
        clear application data/cache, reinstall TikTok, or touch unrelated apps.
        After the stop, the already-qualified TikTok launcher component is
        relaunched and healthy foreground state must be proven before returning.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("hard restart reason must be a non-empty string")
        if settle_seconds < 0 or settle_seconds > 10:
            raise ValueError("settle_seconds must be between 0 and 10")
        if self.actions is None:
            raise RuntimeSupervisorError("hard restart requires bounded ADB actions")

        decision = RecoveryDecision(
            RuntimeFailureKind.APP_HUNG,
            RecoveryAction.RESTART_APP,
            True,
            reason.strip(),
        )
        if not self.budget.consume(decision):
            raise RuntimeSupervisorError("TikTok hard-restart budget exhausted")

        self.actions.stop_package(TIKTOK_PACKAGE)
        if settle_seconds:
            self.sleeper(min(settle_seconds, 2.0))

        recovered = self.runtime_factory(
            self.device,
            observer=self.observer,
            actions=self.actions,
            settle_seconds=settle_seconds,
            poll_seconds=0.35,
            max_polls=12,
        ).ensure_foreground()
        if not getattr(recovered, "success", False):
            detail = getattr(recovered, "reason", "TikTok did not recover after hard restart")
            raise RuntimeSupervisorError(f"TikTok hard restart failed: {detail}")

        # One final independent observation ensures the runtime did not briefly
        # foreground and immediately disappear again.
        final = self._observe_with_retry()
        final_decision = classify_observation(final)
        if final_decision.kind is not RuntimeFailureKind.HEALTHY:
            raise RuntimeSupervisorError(
                f"TikTok was not stable after hard restart: {final_decision.reason}"
            )

    def run_read_only(self, operation: Callable[[], T]) -> T:
        """Run one read-only operation with classified transient retries only.

        Callers must not pass taps, swipes, text entry, posting, or any other
        mutation here because a timed-out mutation may already have executed.
        """
        while True:
            try:
                return operation()
            except Exception as exc:
                decision = classify_error(exc)
                if decision.action not in {RecoveryAction.RETRY_HIERARCHY, RecoveryAction.RETRY_ADB}:
                    raise
                if not self.budget.consume(decision):
                    raise
                if self.retry_sleep_seconds:
                    self.sleeper(self.retry_sleep_seconds)
