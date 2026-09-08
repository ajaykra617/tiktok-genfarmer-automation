"""Read-only Android observation helpers for resilient automation.

This module intentionally avoids UI mutation. It uses ADB process/window state
and optional screenshots to classify coarse device/app state before a GenFarmer
module runs. Selector-level TikTok state checks belong in a higher layer once
verified selectors are available.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
import re
import subprocess
from typing import Iterable

from .screen_state import RawScreenFrame, parse_android_raw_screencap

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


class InterruptKind(str, Enum):
    NONE = "none"
    ANDROID_PERMISSION_DIALOG = "android_permission_dialog"
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


def _adb(device: str, args: Iterable[str], *, timeout: float = 12.0, binary: bool = False):
    try:
        proc = subprocess.run(
            ["adb", "-s", device, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AdbObservationError("adb was not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise AdbObservationError(f"adb command timed out after {timeout}s") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        raise AdbObservationError(err or f"adb exited {proc.returncode}")
    if binary:
        return proc.stdout
    return proc.stdout.decode(errors="replace").strip()


def parse_foreground(*texts: str) -> tuple[str | None, str | None]:
    """Extract the best foreground package/activity from dumpsys output."""
    for text in texts:
        for pattern in _COMPONENT_PATTERNS:
            match = pattern.search(text)
            if match:
                activity = match.group(2).rstrip("}")
                return match.group(1), activity
    return None, None


def classify_interrupt(adb_state: str, foreground_package: str | None) -> InterruptKind:
    if adb_state != "device":
        return InterruptKind.DEVICE_OFFLINE
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
    def __init__(self, device: str, *, timeout: float = 12.0) -> None:
        self.device = device
        self.timeout = timeout

    def observe(self) -> DeviceObservation:
        state = _adb(self.device, ["get-state"], timeout=self.timeout)
        if state != "device":
            return DeviceObservation(
                device=self.device,
                adb_state=state,
                foreground_package=None,
                foreground_activity=None,
                tiktok_foreground=False,
                interrupt=InterruptKind.DEVICE_OFFLINE,
            )
        window = _adb(self.device, ["shell", "dumpsys", "window", "windows"], timeout=self.timeout)
        activity = _adb(self.device, ["shell", "dumpsys", "activity", "activities"], timeout=self.timeout)
        package, component = parse_foreground(window, activity)
        interrupt = classify_interrupt(state, package)
        return DeviceObservation(
            device=self.device,
            adb_state=state,
            foreground_package=package,
            foreground_activity=component,
            tiktok_foreground=package == TIKTOK_PACKAGE,
            interrupt=interrupt,
        )

    def capture_screenshot(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(
            _adb(self.device, ["exec-out", "screencap", "-p"], timeout=self.timeout, binary=True)
        )
        return output

    def capture_raw_frame(self) -> RawScreenFrame:
        """Capture one raw RGBA frame without mutating the device."""
        raw = _adb(self.device, ["exec-out", "screencap"], timeout=self.timeout, binary=True)
        return parse_android_raw_screencap(raw)
