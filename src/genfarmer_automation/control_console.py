"""Pure helpers for the local Python automation control console.

The UI itself lives in scripts/automation_console.py. Keeping command building
and parsing here makes the desktop surface testable without launching Tk.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class DeviceRow:
    serial: str
    state: str
    model: str | None = None
    product: str | None = None
    transport_id: str | None = None


def parse_adb_devices(text: str) -> list[DeviceRow]:
    rows: list[DeviceRow] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("List of devices attached") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        meta: dict[str, str] = {}
        for token in parts[2:]:
            if ":" in token:
                key, value = token.split(":", 1)
                meta[key] = value
        rows.append(
            DeviceRow(
                serial=serial,
                state=state,
                model=meta.get("model"),
                product=meta.get("product"),
                transport_id=meta.get("transport_id"),
            )
        )
    return rows


def build_warmup_command(
    *,
    python_exe: str,
    root: Path,
    preset_file: Path,
    preset: str,
    compiled: Path,
    candidates: Path,
    candidate: int,
    device: str,
    apply: bool,
) -> list[str]:
    if candidate < 1:
        raise ValueError("candidate must be >= 1")
    cmd = [
        python_exe,
        str(root / "scripts" / "tiktok_warmup_preset.py"),
        str(preset_file),
        preset,
        str(compiled),
        str(candidates),
        "--candidate", str(candidate),
        "--device", device,
    ]
    if apply:
        cmd.append("--apply")
    return cmd


def build_boost_command(
    *,
    python_exe: str,
    root: Path,
    device: str,
    media: Path,
    candidates: Path,
    candidate: int,
    caption: str = "",
    explore_type: str | None = None,
    explore_value: str | None = None,
    ready: bool = True,
    publish: bool = False,
    apply: bool = False,
) -> list[str]:
    if candidate < 1:
        raise ValueError("candidate must be >= 1")
    if bool(explore_type) != bool(explore_value):
        raise ValueError("explore_type and explore_value must be provided together")
    cmd = [
        python_exe,
        str(root / "scripts" / "tiktok_boost_session.py"),
        "--device", device,
        "--media", str(media),
        "--candidates", str(candidates),
        "--candidate", str(candidate),
    ]
    if caption:
        cmd.extend(["--caption", caption])
    if explore_type and explore_value:
        cmd.extend(["--explore-type", explore_type, "--explore-value", explore_value])
    if ready:
        cmd.append("--ready")
    if publish:
        cmd.append("--publish")
    if apply:
        cmd.append("--apply")
    return cmd


def command_preview(cmd: Iterable[str]) -> str:
    def quote(value: str) -> str:
        if not value or any(ch.isspace() for ch in value) or '"' in value:
            return '"' + value.replace('"', '\\"') + '"'
        return value
    return " ".join(quote(str(part)) for part in cmd)
