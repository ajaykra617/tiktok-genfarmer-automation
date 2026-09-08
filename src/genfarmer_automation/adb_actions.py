"""Small, explicit ADB mutation helpers used only for bounded recovery/lab probes.

GenFarmer remains the normal workflow executor. These helpers exist so the
Python supervisor can restore a coarse known checkpoint (for example, relaunch
an authorized app that is no longer foreground) and perform tightly-scoped lab
qualification without blind UI taps.
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
        """Perform one bounded device-relative upward swipe for lab qualification.

        Coordinates are derived from the *measured current screen geometry*;
        there are no fixed device-specific pixels. This is intentionally a lab
        helper. Production browsing should prefer the already-qualified
        GenFarmer Simple/Up Swipe node as the action executor.
        """
        if width <= 0 or height <= 0:
            raise ValueError("width/height must be positive")
        if not (0.0 < x_fraction < 1.0):
            raise ValueError("x_fraction must be between 0 and 1")
        if not (0.0 < end_y_fraction < start_y_fraction < 1.0):
            raise ValueError("expected 0 < end_y_fraction < start_y_fraction < 1")
        if not (50 <= duration_ms <= 5000):
            raise ValueError("duration_ms must be 50..5000")

        x = round(width * x_fraction)
        start_y = round(height * start_y_fraction)
        end_y = round(height * end_y_fraction)
        out = self._run(
            [
                "shell",
                "input",
                "swipe",
                str(x),
                str(start_y),
                str(x),
                str(end_y),
                str(duration_ms),
            ]
        )
        return AdbActionResult(command="swipe_up_relative", stdout=out)
