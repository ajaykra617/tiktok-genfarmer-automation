"""Generic observe/act/verify/recover supervisor primitives.

The supervisor is intentionally independent of TikTok and GenFarmer transport.
Callers provide observation, precondition, action, postcondition and optional
recovery hooks. Success is granted only when the postcondition passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Callable


class ModuleOutcome(str, Enum):
    SUCCESS = "success"
    INTERRUPTED = "interrupted"
    PRECONDITION_FAILED = "precondition_failed"
    POSTCONDITION_FAILED = "postcondition_failed"
    RECOVERY_FAILED = "recovery_failed"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    ACTION_ERROR = "action_error"


@dataclass(frozen=True)
class SupervisorPolicy:
    local_attempts: int = 2
    recovery_attempts: int = 1
    retry_delay_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.local_attempts < 1:
            raise ValueError("local_attempts must be >= 1")
        if self.recovery_attempts < 0:
            raise ValueError("recovery_attempts must be >= 0")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be >= 0")


@dataclass
class ModuleResult:
    module: str
    outcome: ModuleOutcome
    attempts: int
    recoveries: int
    reason: str | None = None
    observations: list[Any] = field(default_factory=list)
    action_results: list[Any] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.outcome is ModuleOutcome.SUCCESS


ObservationFn = Callable[[], Any]
PredicateFn = Callable[[Any], bool]
ActionFn = Callable[[Any], Any]
InterruptFn = Callable[[Any], str | None]
RecoveryFn = Callable[[Any], bool]
CheckpointFn = Callable[[ModuleResult], None]


class ResilientSupervisor:
    def __init__(self, policy: SupervisorPolicy | None = None) -> None:
        self.policy = policy or SupervisorPolicy()

    def run_module(
        self,
        *,
        module: str,
        observe: ObservationFn,
        precondition: PredicateFn,
        action: ActionFn,
        postcondition: PredicateFn,
        interrupt: InterruptFn | None = None,
        recover: RecoveryFn | None = None,
        checkpoint: CheckpointFn | None = None,
        deadline_monotonic: float | None = None,
    ) -> ModuleResult:
        attempts = 0
        recoveries = 0
        observations: list[Any] = []
        action_results: list[Any] = []

        def done(outcome: ModuleOutcome, reason: str | None = None) -> ModuleResult:
            result = ModuleResult(
                module=module,
                outcome=outcome,
                attempts=attempts,
                recoveries=recoveries,
                reason=reason,
                observations=observations,
                action_results=action_results,
            )
            if checkpoint:
                checkpoint(result)
            return result

        while True:
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                return done(ModuleOutcome.DEADLINE_EXCEEDED, "session deadline reached")

            before = observe()
            observations.append(before)

            if interrupt:
                interrupt_reason = interrupt(before)
                if interrupt_reason:
                    if recover is None or recoveries >= self.policy.recovery_attempts:
                        return done(ModuleOutcome.INTERRUPTED, interrupt_reason)
                    recoveries += 1
                    if not recover(before):
                        return done(ModuleOutcome.RECOVERY_FAILED, interrupt_reason)
                    continue

            if not precondition(before):
                if recover is None or recoveries >= self.policy.recovery_attempts:
                    return done(ModuleOutcome.PRECONDITION_FAILED, "module precondition not proven")
                recoveries += 1
                if not recover(before):
                    return done(ModuleOutcome.RECOVERY_FAILED, "recovery did not restore precondition")
                continue

            attempts += 1
            try:
                action_results.append(action(before))
            except Exception as exc:  # caller gets a bounded failure, never an infinite retry
                if attempts >= self.policy.local_attempts:
                    return done(ModuleOutcome.ACTION_ERROR, str(exc))
                if self.policy.retry_delay_seconds:
                    time.sleep(self.policy.retry_delay_seconds)
                continue

            after = observe()
            observations.append(after)

            if interrupt:
                interrupt_reason = interrupt(after)
                if interrupt_reason:
                    if recover is None or recoveries >= self.policy.recovery_attempts:
                        return done(ModuleOutcome.INTERRUPTED, interrupt_reason)
                    recoveries += 1
                    if not recover(after):
                        return done(ModuleOutcome.RECOVERY_FAILED, interrupt_reason)
                    continue

            if postcondition(after):
                return done(ModuleOutcome.SUCCESS)

            if attempts < self.policy.local_attempts:
                if self.policy.retry_delay_seconds:
                    time.sleep(self.policy.retry_delay_seconds)
                continue

            if recover is not None and recoveries < self.policy.recovery_attempts:
                recoveries += 1
                if recover(after):
                    attempts = 0
                    continue
                return done(ModuleOutcome.RECOVERY_FAILED, "postcondition recovery failed")

            return done(ModuleOutcome.POSTCONDITION_FAILED, "module postcondition not proven")
