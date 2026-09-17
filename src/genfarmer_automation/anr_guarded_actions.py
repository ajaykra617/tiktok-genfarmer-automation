"""ANR-aware guards around bounded UI mutations used by production demos.

The base :class:`AdbActions` helper intentionally keeps mutation primitives small.
This production-only wrapper adds one deep, read-only TikTok health check immediately
before a feed swipe. If Android already reports APP_NOT_RESPONDING, the swipe is not
sent. If a swipe itself times out, a second deep observation reclassifies the failure
when Android has surfaced an ANR so checkpoint recovery gets a precise reason.

This module never dismisses ANR dialogs, clears app data, retries an ambiguous swipe,
or performs engagement/publishing actions.
"""
from __future__ import annotations

from typing import Any

from .adb_actions import AdbActionError, AdbActions, AdbActionResult
from .adb_observer import AdbObserver, InterruptKind


class AnrGuardedAdbActions(AdbActions):
    """Guard feed swipes with a deep ANR checkpoint.

    ``swipe_timeout`` is deliberately shorter than the generic ADB mutation timeout:
    a normal Android ``input swipe`` returns quickly, while a wedged input dispatch
    should not hold one device worker for the full generic timeout. Recovery remains
    stage/checkpoint owned; this class never retries a timed-out swipe because the
    mutation outcome is ambiguous.
    """

    def __init__(
        self,
        device: str,
        *,
        timeout: float = 12.0,
        swipe_timeout: float = 6.0,
        observer: Any | None = None,
    ) -> None:
        super().__init__(device, timeout=timeout)
        if swipe_timeout <= 0:
            raise ValueError("swipe_timeout must be > 0")
        self.swipe_timeout = min(float(swipe_timeout), float(timeout))
        self._anr_observer = observer or AdbObserver(device)

    def _deep_observation(self):
        deep = getattr(self._anr_observer, "observe_deep", None)
        if callable(deep):
            return deep()
        return self._anr_observer.observe()

    def _raise_if_anr(self, *, phase: str) -> None:
        observation = self._deep_observation()
        if getattr(observation, "interrupt", None) is InterruptKind.APP_NOT_RESPONDING:
            if phase == "before":
                raise AdbActionError(
                    "TikTok app-not-responding before swipe; swipe was not sent"
                )
            raise AdbActionError(
                "TikTok app-not-responding after timed-out swipe; swipe outcome is ambiguous"
            )

    def swipe_up_relative(
        self,
        *,
        width: int,
        height: int,
        duration_ms: int = 450,
        x_fraction: float = 0.50,
        start_y_fraction: float = 0.72,
        end_y_fraction: float = 0.28,
    ) -> AdbActionResult:
        self._raise_if_anr(phase="before")

        # AdbActions keeps one timeout for all bounded mutations. The demo is
        # single-threaded, so temporarily tightening only this synchronous swipe
        # is deterministic and restored in ``finally``.
        original_timeout = self.timeout
        self.timeout = min(original_timeout, self.swipe_timeout)
        try:
            return super().swipe_up_relative(
                width=width,
                height=height,
                duration_ms=duration_ms,
                x_fraction=x_fraction,
                start_y_fraction=start_y_fraction,
                end_y_fraction=end_y_fraction,
            )
        except AdbActionError as exc:
            try:
                self._raise_if_anr(phase="after-timeout")
            except AdbActionError as anr_exc:
                raise anr_exc from exc
            raise
        finally:
            self.timeout = original_timeout
