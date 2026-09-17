"""Bounded settle recovery for freshly started hierarchy helper services.

The base hierarchy runtime already knows how to positively identify an existing
openatx helper and start its installed UiAutomator service. On some physical
Android devices the service reports a successful start before ``/dump/hierarchy``
is actually ready. This module adds a short, read-only settle poll around that
specific state without restarting TikTok or performing any engagement action.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
import re
import time
from typing import Any


_SERVICE_RECOVERY_STARTED = re.compile(r"^helper:(\d+):service-recovery:started$")


def _service_recovery_ports(attempts: Iterable[str]) -> tuple[int, ...]:
    """Return unique helper ports whose service recovery reported success."""
    ports: list[int] = []
    for entry in attempts:
        match = _SERVICE_RECOVERY_STARTED.fullmatch(entry)
        if match is None:
            continue
        port = int(match.group(1))
        if port not in ports:
            ports.append(port)
    return tuple(ports)


def wrap_discover_helper_port(
    original_discover: Callable[..., tuple[int | None, tuple[str, ...]]],
    capture_once: Callable[..., str],
    error_type: type[BaseException],
    *,
    sleep: Callable[[float], Any] = time.sleep,
    settle_delays: tuple[float, ...] = (0.75, 1.25, 2.0),
) -> Callable[..., tuple[int | None, tuple[str, ...]]]:
    """Wrap helper discovery with bounded post-start readiness polling.

    Extra polling is activated only when the underlying discovery positively
    reports ``service-recovery:started`` but its immediate hierarchy retry still
    failed. This keeps the normal fast path unchanged and avoids blindly probing
    unrelated listeners. The polls are hierarchy reads only.
    """
    if not settle_delays or any(delay < 0 for delay in settle_delays):
        raise ValueError("settle_delays must contain non-negative values")

    def discover(
        device: str,
        *,
        preferred_port: int | None = None,
        probe_timeout: float = 1.5,
        max_ports: int = 16,
    ) -> tuple[int | None, tuple[str, ...]]:
        port, attempts = original_discover(
            device,
            preferred_port=preferred_port,
            probe_timeout=probe_timeout,
            max_ports=max_ports,
        )
        if port is not None:
            return port, attempts

        recovery_ports = _service_recovery_ports(attempts)
        if not recovery_ports:
            return None, attempts

        attempt_log = list(attempts)
        capture_timeout = max(probe_timeout, 1.5)

        for recovered_port in recovery_ports:
            for index, delay in enumerate(settle_delays, start=1):
                if delay:
                    sleep(delay)
                try:
                    capture_once(device, recovered_port, timeout=capture_timeout)
                except error_type as exc:
                    attempt_log.append(
                        f"helper:{recovered_port}:service-settle-{index}:fail:{type(exc).__name__}"
                    )
                else:
                    attempt_log.append(
                        f"helper:{recovered_port}:service-settle-{index}:pass"
                    )
                    return recovered_port, tuple(attempt_log)

        return None, tuple(attempt_log)

    return discover
