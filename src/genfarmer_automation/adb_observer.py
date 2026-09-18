"""Read-only Android observation helpers for resilient automation.

This module intentionally avoids UI mutation. It uses ADB process/window state
and optional screenshots to classify coarse device/app state before a GenFarmer
module runs. Selector-level TikTok state checks belong in a higher layer once
verified selectors are available.

Two observation levels are exposed:
- ``observe`` is the normal lightweight window/activity check used frequently;
- ``observe_deep`` additionally inspects TikTok's ProcessRecord for ANR state.

The deep check is reserved for stability gates and post-restart checkpoints so
we can catch framework-level ANRs without making every watch-loop observation
needlessly expensive.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
import re
from typing import Iterable

from .adb_transport import AdbTransport, AdbTransportError
from .interaction_trace import trace_event, trace_exception
from .screen_state import RawScreenFrame, parse_android_raw_screencap

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


class InterruptKind(str, Enum):
    NONE = "none"
    ANDROID_PERMISSION_DIALOG = "android_permission_dialog"
    APP_NOT_RESPONDING = "app_not_responding"
    SYSTEM_UI = "system_ui"
    PACKAGE_INSTALLER = "package_installer"
    DEVICE_OFFLINE = "device_offline"
    UNKNOWN_FOREGROUND = "unknown_foreground"


@dataclass(frozen=True)
class DeviceObservation:
    device: str
    adb_state: str
    foreground_package: str | None
    foreground_activity: str | None
    tiktok_foreground: bool
    interrupt: InterruptKind

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["interrupt"] = self.interrupt.value
        return value


class AdbObservationError(RuntimeError):
    pass


_COMPONENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"mCurrentFocus=.*?\s([A-Za-z0-9._]+)/(\S+)}?"),
    re.compile(r"mFocusedApp=.*?\s([A-Za-z0-9._]+)/(\S+)}?"),
    re.compile(r"topResumedActivity=.*?\s([A-Za-z0-9._]+)/(\S+)}?"),
    re.compile(r"mResumedActivity:.*?\s([A-Za-z0-9._]+)/(\S+)}?"),
)

_PERMISSION_PACKAGES = {
    "com.android.permissioncontroller",
    "com.google.android.permissioncontroller",
}
_PACKAGE_INSTALLERS = {
    "com.android.packageinstaller",
    "com.google.android.packageinstaller",
}
_ANR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"AppNotRespondingDialog", re.IGNORECASE),
    re.compile(r"Application\s+Not\s+Responding", re.IGNORECASE),
    re.compile(r"APP_NOT_RESPONDING", re.IGNORECASE),
    re.compile(r"\bANR\b.*?" + re.escape(TIKTOK_PACKAGE), re.IGNORECASE),
    # ProcessRecord formatting varies between Android releases. Restrict these
    # markers to a bounded region after the TikTok package so another process's
    # notResponding flag cannot create a false TikTok ANR.
    re.compile(
        re.escape(TIKTOK_PACKAGE) + r"[\s\S]{0,2000}\bnotResponding\s*[=:]\s*true\b",
        re.IGNORECASE,
    ),
    re.compile(
        re.escape(TIKTOK_PACKAGE) + r"[\s\S]{0,2000}\bnot\s+responding\s*[=:]\s*true\b",
        re.IGNORECASE,
    ),
)


def _adb(
    device: str,
    args: Iterable[str],
    *,
    timeout: float = 12.0,
    binary: bool = False,
    transport: AdbTransport | None = None,
):
    channel = transport or AdbTransport(device, timeout=timeout)
    try:
        result = channel.run(args, timeout=timeout, mutation=False)
    except AdbTransportError as exc:
        raise AdbObservationError(str(exc)) from exc
    if binary:
        return result.stdout
    return result.stdout_text()


def parse_foreground(*texts: str) -> tuple[str | None, str | None]:
    """Extract the best foreground package/activity from dumpsys output."""
    for text in texts:
        for pattern in _COMPONENT_PATTERNS:
            match = pattern.search(text)
            if match:
                activity = match.group(2).rstrip("}")
                return match.group(1), activity
    return None, None


def has_app_not_responding(*texts: str) -> bool:
    """Detect Android's ANR surface from locale-independent framework markers.

    The visible dialog text itself is localized, so we prefer framework/window
    implementation markers and ProcessRecord flags over phrases such as
    ``TikTok isn't responding``.
    """
    joined = "\n".join(text for text in texts if text)
    return any(pattern.search(joined) for pattern in _ANR_PATTERNS)


def classify_interrupt(
    adb_state: str,
    foreground_package: str | None,
    *evidence_texts: str,
) -> InterruptKind:
    if adb_state != "device":
        return InterruptKind.DEVICE_OFFLINE
    if has_app_not_responding(*evidence_texts):
        return InterruptKind.APP_NOT_RESPONDING
    if foreground_package in _PERMISSION_PACKAGES:
        return InterruptKind.ANDROID_PERMISSION_DIALOG
    if foreground_package in _PACKAGE_INSTALLERS:
        return InterruptKind.PACKAGE_INSTALLER
    if foreground_package == "com.android.systemui":
        return InterruptKind.SYSTEM_UI
    if foreground_package is None:
        return InterruptKind.UNKNOWN_FOREGROUND
    return InterruptKind.NONE


class AdbObserver:
    def __init__(
        self,
        device: str,
        *,
        timeout: float = 12.0,
        transport: AdbTransport | None = None,
    ) -> None:
        self.device = device
        self.timeout = timeout
        self.transport = transport or AdbTransport(device, timeout=timeout)

    def _observe(self, *, deep: bool) -> DeviceObservation:
        trace_event(
            "observe.begin",
            device=self.device,
            category="observer",
            deep=deep,
        )
        state = _adb(self.device, ["get-state"], timeout=self.timeout, transport=self.transport)
        if state != "device":
            return DeviceObservation(
                device=self.device,
                adb_state=state,
                foreground_package=None,
                foreground_activity=None,
                tiktok_foreground=False,
                interrupt=InterruptKind.DEVICE_OFFLINE,
            )

        window = _adb(self.device, ["shell", "dumpsys", "window", "windows"], timeout=self.timeout, transport=self.transport)
        activity = _adb(self.device, ["shell", "dumpsys", "activity", "activities"], timeout=self.timeout, transport=self.transport)
        package, component = parse_foreground(window, activity)

        evidence = [window, activity]
        if deep:
            # Android's visible ANR dialog can occasionally appear after a brief
            # foreground sample. ProcessRecord is the stronger secondary source.
            # The package argument is a best-effort filter on modern Android;
            # older builds may still return a broader process dump, which is safe
            # because has_app_not_responding() scopes process flags to TikTok.
            processes = _adb(
                self.device,
                ["shell", "dumpsys", "activity", "processes", TIKTOK_PACKAGE],
                timeout=self.timeout,
                transport=self.transport,
            )
            evidence.append(processes)

        interrupt = classify_interrupt(state, package, *evidence)
        observation = DeviceObservation(
            device=self.device,
            adb_state=state,
            foreground_package=package,
            foreground_activity=component,
            tiktok_foreground=package == TIKTOK_PACKAGE,
            interrupt=interrupt,
        )
        trace_event(
            "observe.end",
            device=self.device,
            category="observer",
            deep=deep,
            adb_state=state,
            foreground_package=package,
            foreground_activity=component,
            tiktok_foreground=observation.tiktok_foreground,
            interrupt=interrupt.value,
        )
        return observation

    def observe(self) -> DeviceObservation:
        """Fast coarse observation for frequent runtime checks."""
        return self._observe(deep=False)

    def observe_deep(self) -> DeviceObservation:
        """Checkpoint observation including TikTok ProcessRecord ANR evidence."""
        return self._observe(deep=True)

    def capture_screenshot(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(
            _adb(self.device, ["exec-out", "screencap", "-p"], timeout=self.timeout, binary=True, transport=self.transport)
        )
        return output

    def capture_raw_frame(self) -> RawScreenFrame:
        """Capture one raw RGBA frame without mutating the device."""
        raw = _adb(self.device, ["exec-out", "screencap"], timeout=self.timeout, binary=True, transport=self.transport)
        return parse_android_raw_screencap(raw)
