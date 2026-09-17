"""Best-effort private diagnostics for TikTok runtime recovery.

These helpers are deliberately read-only. They capture enough Android state to
help distinguish a TikTok ANR/crash from a hierarchy/UI-state failure without
changing the application or device. Diagnostic collection must never block the
actual recovery path: individual ADB failures are recorded in the private bundle
instead of being raised to the workflow.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Iterable

from .adb_observer import TIKTOK_PACKAGE, has_app_not_responding, parse_foreground


@dataclass(frozen=True)
class RuntimeDiagnosticSummary:
    timestamp_utc: str
    process_alive: bool
    pid: str | None
    foreground_package: str | None
    foreground_activity: str | None
    anr_detected: bool
    crash_marker_detected: bool
    low_memory_marker_detected: bool
    collection_errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _safe_label(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-.")
    return cleaned or "runtime"


def _run_text(device: str, args: Iterable[str], *, timeout: float = 8.0) -> tuple[str, str | None]:
    try:
        proc = subprocess.run(
            ["adb", "-s", device, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return "", "adb-not-found"
    except subprocess.TimeoutExpired:
        return "", f"timeout:{' '.join(args)}"

    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        return stdout, stderr or f"adb-exit-{proc.returncode}:{' '.join(args)}"
    return stdout, None


def summarize_runtime_evidence(
    *,
    pid_text: str = "",
    window_text: str = "",
    activity_text: str = "",
    process_text: str = "",
    meminfo_text: str = "",
    logcat_text: str = "",
    collection_errors: Iterable[str] = (),
) -> RuntimeDiagnosticSummary:
    """Summarize already-captured read-only evidence.

    Crash/low-memory flags are diagnostic hints only. They are intentionally not
    used by the workflow to decide whether a mutation should be replayed.
    """
    foreground_package, foreground_activity = parse_foreground(window_text, activity_text)
    pid = pid_text.strip().split()[0] if pid_text.strip() else None
    joined_log = logcat_text.casefold()
    crash_marker = (
        TIKTOK_PACKAGE.casefold() in joined_log
        and any(marker in joined_log for marker in ("fatal exception", "am_crash", "has died", "process died"))
    )
    low_memory_marker = (
        TIKTOK_PACKAGE.casefold() in joined_log
        and any(marker in joined_log for marker in ("lowmemory", "low memory", "lmkd", "lowmemorykiller"))
    )
    return RuntimeDiagnosticSummary(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        process_alive=pid is not None,
        pid=pid,
        foreground_package=foreground_package,
        foreground_activity=foreground_activity,
        anr_detected=has_app_not_responding(window_text, activity_text, process_text, logcat_text),
        crash_marker_detected=crash_marker,
        low_memory_marker_detected=low_memory_marker,
        collection_errors=tuple(str(item) for item in collection_errors if str(item).strip()),
    )


def capture_tiktok_runtime_diagnostics(
    device: str,
    directory: str | Path,
    label: str,
) -> RuntimeDiagnosticSummary:
    """Capture a bounded private runtime bundle without interrupting recovery."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    stem = _safe_label(label)

    commands = {
        "pid": ("shell", "pidof", TIKTOK_PACKAGE),
        "window": ("shell", "dumpsys", "window", "windows"),
        "activity": ("shell", "dumpsys", "activity", "activities"),
        "processes": ("shell", "dumpsys", "activity", "processes", TIKTOK_PACKAGE),
        "meminfo": ("shell", "dumpsys", "meminfo", TIKTOK_PACKAGE),
        "logcat": ("logcat", "-d", "-t", "350"),
    }

    captured: dict[str, str] = {}
    errors: list[str] = []
    for name, args in commands.items():
        text, error = _run_text(device, args)
        captured[name] = text
        (out / f"{stem}-{name}.private.txt").write_text(
            text,
            encoding="utf-8",
            errors="replace",
        )
        if error:
            errors.append(f"{name}:{error}")

    summary = summarize_runtime_evidence(
        pid_text=captured["pid"],
        window_text=captured["window"],
        activity_text=captured["activity"],
        process_text=captured["processes"],
        meminfo_text=captured["meminfo"],
        logcat_text=captured["logcat"],
        collection_errors=errors,
    )
    (out / f"{stem}-summary.private.json").write_text(
        json.dumps(summary.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary
