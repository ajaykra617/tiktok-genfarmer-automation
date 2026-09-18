"""Small, explicit ADB mutation helpers used only for bounded recovery/lab probes.

GenFarmer remains the preferred workflow executor. These helpers exist so the
Python supervisor can restore a coarse known checkpoint and, when GenFarmer is
unavailable, execute tightly-scoped actions whose targets were derived from
fresh runtime evidence. Fixed guessed production coordinates remain prohibited.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .adb_transport import AdbTransport, AdbTransportError


class AdbActionError(RuntimeError):
    """ADB mutation failure with transport/outcome metadata when available."""

    def __init__(
        self,
        message: str,
        *,
        mutation_ambiguous: bool = False,
        transport_healthy: bool | None = None,
        failure_kind: str | None = None,
    ) -> None:
        super().__init__(message)
        self.mutation_ambiguous = mutation_ambiguous
        self.transport_healthy = transport_healthy
        self.failure_kind = failure_kind


@dataclass(frozen=True)
class AdbActionResult:
    command: str
    stdout: str


_PACKAGE_RE = re.compile(r"^[A-Za-z0-9_.]+$")
_SAFE_TEXT_RE = re.compile(r"^[A-Za-z0-9 _.,!?@:+\-]*$")


class AdbActions:
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

    def _run(self, args: Iterable[str]) -> str:
        try:
            result = self.transport.run(args, timeout=self.timeout, mutation=True)
        except AdbTransportError as exc:
            raise AdbActionError(
                str(exc),
                mutation_ambiguous=exc.mutation_ambiguous,
                transport_healthy=exc.transport_healthy,
                failure_kind=exc.kind.value,
            ) from exc
        return result.stdout_text()

    def launch_component(self, component: str) -> AdbActionResult:
        """Launch one explicitly qualified Android component."""
        if "/" not in component or any(ch.isspace() for ch in component):
            raise ValueError("component must be PACKAGE/ACTIVITY without whitespace")
        out = self._run(["shell", "am", "start", "-W", "-n", component])
        return AdbActionResult(command="launch_component", stdout=out)

    def tap(self, x: int, y: int) -> AdbActionResult:
        """Tap one runtime-derived coordinate."""
        if not isinstance(x, int) or isinstance(x, bool) or x < 0:
            raise ValueError("x must be a non-negative integer")
        if not isinstance(y, int) or isinstance(y, bool) or y < 0:
            raise ValueError("y must be a non-negative integer")
        out = self._run(["shell", "input", "tap", str(x), str(y)])
        return AdbActionResult(command="tap", stdout=out)

    def keyevent(self, keycode: int) -> AdbActionResult:
        if not isinstance(keycode, int) or isinstance(keycode, bool) or not 0 <= keycode <= 1000:
            raise ValueError("keycode must be an integer 0..1000")
        out = self._run(["shell", "input", "keyevent", str(keycode)])
        return AdbActionResult(command="keyevent", stdout=out)

    def input_text(self, text: str) -> AdbActionResult:
        """Type conservative ASCII text without passing shell metacharacters.

        Spaces use Android input's `%s` encoding. Rich/unicode captions should
        use a separately qualified IME/clipboard path rather than weakening this
        safety boundary.
        """
        if not isinstance(text, str) or len(text) > 2200:
            raise ValueError("text must be a string no longer than 2200 characters")
        if not _SAFE_TEXT_RE.fullmatch(text):
            raise ValueError("text contains characters not qualified for ADB input_text")
        encoded = text.replace(" ", "%s")
        out = self._run(["shell", "input", "text", encoded])
        return AdbActionResult(command="input_text", stdout=out)

    def stop_package(self, package: str) -> AdbActionResult:
        if not _PACKAGE_RE.fullmatch(package):
            raise ValueError("invalid Android package")
        out = self._run(["shell", "am", "force-stop", package])
        return AdbActionResult(command="stop_package", stdout=out)

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
        """Perform one bounded device-relative upward swipe.

        Coordinates are derived from the measured current screen geometry; there
        are no fixed device-specific pixels.
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
