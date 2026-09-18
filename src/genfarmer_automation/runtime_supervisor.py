"""Shared bounded runtime supervision for authorized TikTok automation.

The supervisor centralizes recovery policy without making workflow decisions.
Read-only observation/hierarchy operations may be retried when positively
classified as transient. UI mutations are never replayed by this module.

Recovery remains intentionally bounded:
- permission dialogs: one qualified recovery by default;
- TikTok background/ANR: bounded foreground restore or process restart;
- hierarchy and read-only ADB failures: bounded read-only retries;
- explicit hard restart: force-stop only TikTok, relaunch the qualified
  component, and prove stable healthy foreground state again;
- unknown semantic/UI failures: fail closed.

A hard restart is intentionally not a generic retry mechanism. Callers may use
it only at a known workflow checkpoint where replay is safe. It never clears
TikTok data/cache, never reinstalls the app, and never kills unrelated apps.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Any, Callable, TypeVar

from .adb_observer import AdbObserver, TIKTOK_PACKAGE
from .interaction_trace import trace_event, trace_exception
from .permission_recovery import recover_tiktok_permission_dialog
from .runtime_diagnostics import capture_tiktok_runtime_diagnostics
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

    def _capture_app_hung_diagnostics(self, *, phase: str, reason: str) -> None:
        """Best-effort ANR evidence capture when private tracing is enabled."""
        trace_root = os.environ.get("GF_INTERACTION_TRACE_DIR")
        if not trace_root:
            return
        out = Path(trace_root) / "runtime-diagnostics"
        label = f"{phase}-app-hung"
        trace_event(
            "anr-diagnostics.begin",
            device=self.device,
            category="recovery",
            phase=phase,
            reason=reason,
            directory=str(out),
        )
        try:
            summary = capture_tiktok_runtime_diagnostics(
                self.device,
                out,
                label,
            )
        except Exception as exc:
            trace_exception(
                "anr-diagnostics.error",
                exc,
                device=self.device,
                category="recovery",
                phase=phase,
                reason=reason,
            )
            return
        trace_event(
            "anr-diagnostics.end",
            device=self.device,
            category="recovery",
            phase=phase,
            reason=reason,
            process_alive=summary.process_alive,
            pid=summary.pid,
            foreground_package=summary.foreground_package,
            foreground_activity=summary.foreground_activity,
            anr_detected=summary.anr_detected,
            crash_marker_detected=summary.crash_marker_detected,
            low_memory_marker_detected=summary.low_memory_marker_detected,
            collection_errors=summary.collection_errors,
        )

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

    def _observe_checkpoint_with_retry(self):
        """Use the strongest available read-only observation at checkpoints."""
        while True:
            try:
                deep = getattr(self.observer, "observe_deep", None)
                if callable(deep):
                    return deep()
                return self.observer.observe()
            except Exception as exc:
                decision = classify_error(exc)
                if decision.action is not RecoveryAction.RETRY_ADB or not self.budget.consume(decision):
                    raise RuntimeSupervisorError(str(exc) or "ADB checkpoint observation failed") from exc
                if self.retry_sleep_seconds:
                    self.sleeper(self.retry_sleep_seconds)

    def ensure_ready(self, *, apply: bool = True) -> None:
        """Prove one healthy TikTok foreground observation with bounded recovery."""
        for _ in range(4):
            observation = self._observe_with_retry()
            decision = classify_observation(observation)
            if decision.kind is RuntimeFailureKind.HEALTHY:
                return
            trace_event(
                "runtime-decision",
                device=self.device,
                category="recovery",
                phase="ensure_ready",
                failure_kind=decision.kind.value,
                action=decision.action.value,
                retryable=decision.retryable,
                reason=decision.reason,
                budget_used=self.budget.snapshot(),
            )
            if decision.kind is RuntimeFailureKind.APP_HUNG:
                self._capture_app_hung_diagnostics(
                    phase="ensure-ready",
                    reason=decision.reason,
                )
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
                trace_event(
                    "runtime-recovery.begin",
                    device=self.device,
                    category="recovery",
                    phase="ensure_ready",
                    action=decision.action.value,
                    reason=decision.reason,
                )
                recovered = self.runtime_factory(self.device, **kwargs).ensure_foreground()
                if not getattr(recovered, "success", False):
                    reason = getattr(recovered, "reason", "TikTok runtime recovery failed")
                    trace_event(
                        "runtime-recovery.end",
                        device=self.device,
                        category="recovery",
                        phase="ensure_ready",
                        action=decision.action.value,
                        success=False,
                        reason=reason,
                    )
                    raise RuntimeSupervisorError(f"TikTok runtime recovery failed: {reason}")
                trace_event(
                    "runtime-recovery.end",
                    device=self.device,
                    category="recovery",
                    phase="ensure_ready",
                    action=decision.action.value,
                    success=True,
                    attempts=getattr(recovered, "attempts", None),
                    reason=getattr(recovered, "reason", None),
                )
                continue

            raise RuntimeSupervisorError(decision.reason)

        raise RuntimeSupervisorError("TikTok healthy runtime state was not proven within the recovery loop budget")

    def ensure_stable(
        self,
        *,
        apply: bool = True,
        consecutive: int = 3,
        interval_seconds: float = 0.35,
    ) -> None:
        """Require multiple consecutive healthy checkpoint observations.

        A single foreground observation can be a brief transition before Android
        surfaces an ANR dialog or the activity disappears again. Demo/session
        entry and post-restart checkpoints therefore use this stronger gate.
        When the observer exposes ``observe_deep()``, this method also inspects
        TikTok's ProcessRecord for framework ANR state.
        """
        if not 1 <= consecutive <= 8:
            raise ValueError("consecutive must be between 1 and 8")
        if not 0 <= interval_seconds <= 5:
            raise ValueError("interval_seconds must be between 0 and 5")

        healthy = 0
        attempts = 0
        max_attempts = max(consecutive * 4, consecutive + 3)

        while healthy < consecutive and attempts < max_attempts:
            attempts += 1
            # First allow the normal bounded recovery path to restore foreground
            # state. Then require an independent deep checkpoint observation.
            self.ensure_ready(apply=apply)
            observation = self._observe_checkpoint_with_retry()
            decision = classify_observation(observation)
            if decision.kind is RuntimeFailureKind.HEALTHY:
                healthy += 1
                if healthy < consecutive and interval_seconds:
                    self.sleeper(interval_seconds)
                continue

            healthy = 0
            trace_event(
                "runtime-decision",
                device=self.device,
                category="recovery",
                phase="ensure_stable",
                failure_kind=decision.kind.value,
                action=decision.action.value,
                retryable=decision.retryable,
                reason=decision.reason,
                budget_used=self.budget.snapshot(),
                consecutive_healthy=healthy,
                attempt=attempts,
            )
            if decision.kind is RuntimeFailureKind.APP_HUNG:
                self._capture_app_hung_diagnostics(
                    phase="ensure-stable",
                    reason=decision.reason,
                )
            if not apply:
                raise RuntimeSupervisorError(decision.reason)

            # If the deep observation found an ANR/foreground problem that the
            # lightweight sample missed, perform its classified recovery now
            # rather than waiting for a later stage to fail semantically.
            if not self.budget.consume(decision):
                raise RuntimeSupervisorError(
                    f"runtime recovery budget exhausted or failure is not retryable: {decision.reason}"
                )

            if decision.action is RecoveryAction.RECOVER_PERMISSION:
                recovered = self.permission_recoverer(self.device, observer=self.observer)
                if not getattr(recovered, "success", False):
                    reason = getattr(recovered, "reason", "permission recovery failed")
                    raise RuntimeSupervisorError(f"permission recovery failed: {reason}")
            elif decision.action in {RecoveryAction.RESTORE_FOREGROUND, RecoveryAction.RESTART_APP}:
                kwargs = {"observer": self.observer}
                if self.actions is not None:
                    kwargs["actions"] = self.actions
                trace_event(
                    "runtime-recovery.begin",
                    device=self.device,
                    category="recovery",
                    phase="ensure_stable",
                    action=decision.action.value,
                    reason=decision.reason,
                )
                recovered = self.runtime_factory(self.device, **kwargs).ensure_foreground()
                if not getattr(recovered, "success", False):
                    reason = getattr(recovered, "reason", "TikTok runtime recovery failed")
                    trace_event(
                        "runtime-recovery.end",
                        device=self.device,
                        category="recovery",
                        phase="ensure_stable",
                        action=decision.action.value,
                        success=False,
                        reason=reason,
                    )
                    raise RuntimeSupervisorError(f"TikTok runtime recovery failed: {reason}")
                trace_event(
                    "runtime-recovery.end",
                    device=self.device,
                    category="recovery",
                    phase="ensure_stable",
                    action=decision.action.value,
                    success=True,
                    attempts=getattr(recovered, "attempts", None),
                    reason=getattr(recovered, "reason", None),
                )
            else:
                raise RuntimeSupervisorError(decision.reason)

            if interval_seconds:
                self.sleeper(interval_seconds)

        if healthy < consecutive:
            raise RuntimeSupervisorError(
                f"TikTok did not remain healthy for {consecutive} consecutive observations"
            )

    def hard_restart(self, *, reason: str, settle_seconds: float = 1.5) -> None:
        """Perform one budgeted clean TikTok process restart from a checkpoint.

        `am force-stop` terminates TikTok's process, allowing Android to reclaim
        that app's private memory. We deliberately do not run global RAM cleaners,
        clear application data/cache, reinstall TikTok, or touch unrelated apps.
        After the stop, the already-qualified TikTok launcher component is
        relaunched and stable healthy foreground state must be proven before
        returning.
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

        # Do not trust one foreground sample after relaunch. The app can briefly
        # appear healthy and immediately surface another ANR. Three consecutive
        # deep observations materially reduce that false-success window.
        self.ensure_stable(apply=False, consecutive=3, interval_seconds=0.35)

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
                    if decision.action is RecoveryAction.RETRY_HIERARCHY:
                        # A frozen TikTok process can poison every accessibility
                        # provider. Before surfacing an exhausted hierarchy error,
                        # perform one strong read-only runtime observation so the
                        # checkpoint layer can distinguish provider failure from
                        # a real Android ANR and spend the app-restart budget on
                        # the correct failure domain.
                        observation = self._observe_checkpoint_with_retry()
                        runtime_decision = classify_observation(observation)
                        if runtime_decision.kind is RuntimeFailureKind.APP_HUNG:
                            raise RuntimeSupervisorError(
                                "TikTok/Android reported app-not-responding while "
                                "hierarchy sources were unavailable"
                            ) from exc
                    raise
                if self.retry_sleep_seconds:
                    self.sleeper(self.retry_sleep_seconds)
