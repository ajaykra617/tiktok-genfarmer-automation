"""Read-only parsing helpers for Android TCP listener discovery.

Used to locate the actual runtime port of GenFarmer/openatx/UiAutomator helpers
without hard-coding one device port.  The module only parses command output; it
does not create sessions or mutate Android application state.
"""
from __future__ import annotations

import re
from typing import Iterable


class ListenerDiscoveryError(ValueError):
    pass


def _valid_port(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535


def parse_proc_net_tcp(text: str) -> tuple[int, ...]:
    """Extract LISTEN ports from /proc/net/tcp or /proc/net/tcp6 text."""
    found: list[int] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("sl"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[1]
        state = parts[3].upper()
        if state != "0A" or ":" not in local:
            continue
        port_hex = local.rsplit(":", 1)[1]
        try:
            port = int(port_hex, 16)
        except ValueError:
            continue
        if _valid_port(port) and port not in found:
            found.append(port)
    return tuple(found)


def parse_ss_listeners(text: str) -> tuple[int, ...]:
    """Extract local TCP listening ports from common Android `ss -ltn` output."""
    found: list[int] = []
    port_re = re.compile(r":(?P<port>\d{1,5})(?=\s|$)")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith(("state", "netid")):
            continue
        if "LISTEN" not in line.upper():
            continue
        matches = list(port_re.finditer(line))
        if not matches:
            continue
        # The first numeric address:port in `ss -ltn` is the local endpoint.
        port = int(matches[0].group("port"))
        if _valid_port(port) and port not in found:
            found.append(port)
    return tuple(found)


def extract_ports_from_cmdline(text: str) -> tuple[int, ...]:
    """Conservatively extract explicit TCP port hints from helper command lines."""
    patterns = (
        re.compile(r"(?i)(?:--?|/)(?:port|addr|listen|server)[=\s]+(?:[^\s:]+:)?(?P<port>\d{2,5})"),
        re.compile(r"(?<!\d):(?P<port>\d{2,5})(?!\d)"),
    )
    found: list[int] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            port = int(match.group("port"))
            if _valid_port(port) and port not in found:
                found.append(port)
    return tuple(found)


def prioritized_candidate_ports(
    observed: Iterable[int],
    cmdline_hints: Iterable[int] = (),
    *,
    common_hints: Iterable[int] = (7912, 7913, 9008, 6790),
    max_ports: int = 64,
) -> tuple[int, ...]:
    """Return deterministic candidate ports, preferring runtime evidence.

    Unprivileged ports are preferred because GenFarmer/openatx helpers normally
    bind there.  Common hints are appended only after observed/cmdline evidence.
    """
    if not isinstance(max_ports, int) or isinstance(max_ports, bool) or max_ports < 1:
        raise ListenerDiscoveryError("max_ports must be >= 1")

    out: list[int] = []
    for group in (cmdline_hints, observed, common_hints):
        for raw in group:
            if not isinstance(raw, int) or isinstance(raw, bool) or not _valid_port(raw):
                continue
            if raw < 1024 and raw not in common_hints:
                continue
            if raw not in out:
                out.append(raw)
            if len(out) >= max_ports:
                return tuple(out)
    return tuple(out)
