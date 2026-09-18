"""App-only self-healing for a single authorized TikTok device.

This recovery deliberately stops at the application boundary. It never reboots
the phone, clears TikTok data/cache, kills the host ADB server, or touches
unrelated applications. A fleet worker can call it repeatedly with cooldowns.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import time
from typing import Any, Callable

from .adb_actions import AdbActions
from .adb_observer import AdbObserver, TIKTOK_PACKAGE
from .adb_transport import AdbTransport
from .runtime_diagnostics import RuntimeDiagnosticSummary, capture_tiktok_runtime_diagnostics
from .runtime_supervisor import TikTokRuntimeSupervisor
from .tiktok_runtime import TIKTOK_COMPONENT


@dataclass(frozen=True)
class AppRecoveryResult:
    success: bool
    force_stop_attempts: int
    process_gone: bool
    adb_ready: bool
    stable_foreground: bool
    evidence_directory: str
    reason: str


def _safe_device(device: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", device)


def recover_tiktok_without_reboot(
    device: str,
    evidence_root: str | Path,
    *,
    max_force_stops: int = 2,
    stop_settle_seconds: float = 1.5,
    launch_settle_seconds: float = 1.5,
    sleeper: Callable[[float], None] = time.sleep,
    transport: Any | None = None,
    actions: Any | None = None,
    observer: Any | None = None,
    supervisor: Any | None = None,
    diagnostics: Callable[[str, str | Path, str], RuntimeDiagnosticSummary] = capture_tiktok_runtime_diagnostics,
) -> AppRecoveryResult:
    """Force-stop/relaunch TikTok and prove stability without rebooting device."""
    if not isinstance(device, str) or not device.strip():
        raise ValueError("device must be non-empty")
    if not 1 <= max_force_stops <= 3:
        raise ValueError("max_force_stops must be 1..3")
    if not 0 <= stop_settle_seconds <= 10 or not 0 <= launch_settle_seconds <= 10:
        raise ValueError("settle seconds must be between 0 and 10")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(evidence_root) / f"{_safe_device(device)}-{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    channel = transport or AdbTransport(device)
    bounded_actions = actions or AdbActions(device, transport=channel)
    runtime_observer = observer or AdbObserver(device, transport=channel)
    runtime_supervisor = supervisor or TikTokRuntimeSupervisor(
        device,
        observer=runtime_observer,
        actions=bounded_actions,
    )

    diagnostics(device, out, "before-recovery")
    channel.ensure_ready()

    process_gone = False
    stops = 0
    for attempt in range(1, max_force_stops + 1):
        stops = attempt
        bounded_actions.stop_package(TIKTOK_PACKAGE)
        if stop_settle_seconds:
            sleeper(stop_settle_seconds)
        stopped = diagnostics(device, out, f"after-force-stop-{attempt}")
        if not stopped.process_alive:
            process_gone = True
            break

    if not process_gone:
        return AppRecoveryResult(
            False, stops, False, True, False, str(out),
            "TikTok process remained alive after bounded force-stop attempts; reboot not attempted",
        )

    channel.ensure_ready()
    bounded_actions.launch_component(TIKTOK_COMPONENT)
    if launch_settle_seconds:
        sleeper(launch_settle_seconds)

    try:
        runtime_supervisor.ensure_stable(
            apply=False,
            consecutive=3,
            interval_seconds=0.35,
        )
    except Exception as exc:
        diagnostics(device, out, "after-launch-unstable")
        return AppRecoveryResult(
            False, stops, True, True, False, str(out),
            f"TikTok relaunched but stable foreground was not proven: {exc}",
        )

    after = diagnostics(device, out, "after-launch-stable")
    stable = (
        after.process_alive
        and after.foreground_package == TIKTOK_PACKAGE
        and not after.anr_detected
    )
    if not stable:
        return AppRecoveryResult(
            False, stops, True, True, False, str(out),
            "TikTok passed runtime stability gate but final diagnostics were not healthy",
        )

    return AppRecoveryResult(
        True, stops, True, True, True, str(out),
        "TikTok app-only recovery completed; no reboot/data clear/global ADB restart used",
    )
