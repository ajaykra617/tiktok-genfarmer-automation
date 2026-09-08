"""High-level Python supervision entry point.

GenFarmer remains the short deterministic action executor. This controller owns
coarse device observation and the bounded observe/act/verify/recover lifecycle.
"""

from __future__ import annotations

from typing import Any, Callable

from .adb_observer import AdbObserver, DeviceObservation
from .resilience import ModuleResult, ResilientSupervisor, SupervisorPolicy
from .tiktok_runtime import EnsureForegroundResult, TikTokRuntime


class AutomationController:
    def __init__(self, settings: Any, *, policy: SupervisorPolicy | None = None) -> None:
        self.settings = settings
        self.supervisor = ResilientSupervisor(policy)

    def observe_device(self, device: str | None = None) -> DeviceObservation:
        target = device or self.settings.default_device_adb
        return AdbObserver(target).observe()

    def ensure_tiktok_foreground(self, device: str | None = None) -> EnsureForegroundResult:
        """Restore only the coarse qualified TikTok foreground checkpoint.

        This may perform one explicit app relaunch but never taps through UI or
        dismisses interrupts. A fresh observation must prove TikTok foreground.
        """
        target = device or self.settings.default_device_adb
        return TikTokRuntime(target).ensure_foreground()

    def run_verified_module(
        self,
        *,
        module: str,
        observe: Callable[[], Any],
        precondition: Callable[[Any], bool],
        action: Callable[[Any], Any],
        postcondition: Callable[[Any], bool],
        interrupt: Callable[[Any], str | None] | None = None,
        recover: Callable[[Any], bool] | None = None,
        checkpoint: Callable[[ModuleResult], None] | None = None,
        deadline_monotonic: float | None = None,
    ) -> ModuleResult:
        return self.supervisor.run_module(
            module=module,
            observe=observe,
            precondition=precondition,
            action=action,
            postcondition=postcondition,
            interrupt=interrupt,
            recover=recover,
            checkpoint=checkpoint,
            deadline_monotonic=deadline_monotonic,
        )
