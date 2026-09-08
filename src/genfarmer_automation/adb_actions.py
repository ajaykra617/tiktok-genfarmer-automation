"""Small, explicit ADB mutation helpers used only for bounded recovery.

GenFarmer remains the normal workflow executor. These helpers exist so the
Python supervisor can restore a coarse known checkpoint (for example, relaunch
an authorized app that is no longer foreground) without blind UI taps.
"""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Iterable


class AdbActionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdbActionResult:
    command: str
    stdout: str


class AdbActions:
    def __init__(self, device: str, *, timeout: float = 12.0) -> None:
        self.device = device
        self.timeout = timeout

    def _run(self, args: Iterable[str]) -> str:
        try:
            proc = subprocess.run(
                ["adb", "-s", self.device, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AdbActionError("adb was not found in PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbActionError(f"adb action timed out after {self.timeout}s") from exc
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace").strip()
            raise AdbActionError(err or f"adb exited {proc.returncode}")
        return proc.stdout.decode(errors="replace").strip()

    def launch_component(self, component: str) -> AdbActionResult:
        """Launch one explicitly qualified Android component.

        This does not search for packages, install software, or tap through UI.
        The caller must provide a known authorized component.
        """
        if "/" not in component or any(ch.isspace() for ch in component):
            raise ValueError("component must be PACKAGE/ACTIVITY without whitespace")
        out = self._run(["shell", "am", "start", "-W", "-n", component])
        return AdbActionResult(command="launch_component", stdout=out)
