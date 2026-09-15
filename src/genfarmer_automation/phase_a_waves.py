"""Runtime planning for TikTok Boost Phase A wave execution.

The static schedule policy defines barriers and same-app proxy uniqueness. This
module resolves those logical tasks into private local runtime values without
committing client IPs, device ids, credentials, or media paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .schedule_policy import SchedulePlan, ScheduledTask


class PhaseAWaveError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeDevice:
    alias: str
    adb_id: str
    media: tuple[Path, ...]
    media_dirs: tuple[Path, ...]
    account_key: str | None = None


@dataclass(frozen=True)
class RuntimeProxy:
    proxy_id: str
    http_url: str


@dataclass(frozen=True)
class RuntimeDefaults:
    preset_config: Path
    reservations: Path | None = None
    history: Path | None = None
    candidates: Path | None = None
    warmup_compiled: Path | None = None
    preferred_hierarchy_port: int = 8912


@dataclass(frozen=True)
class PhaseARuntime:
    devices: Mapping[str, RuntimeDevice]
    proxies: Mapping[str, RuntimeProxy]
    defaults: RuntimeDefaults


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PhaseAWaveError(f"{field} must be a non-empty string")
    return value.strip()


def _paths(raw: Any, field: str) -> tuple[Path, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise PhaseAWaveError(f"{field} must be an array")
    values: list[Path] = []
    for item in raw:
        values.append(Path(_required_text(item, field)))
    return tuple(values)


def load_phase_a_runtime(payload: Mapping[str, Any], *, root: Path) -> PhaseARuntime:
    raw_devices = payload.get("devices")
    raw_proxies = payload.get("proxies")
    raw_defaults = payload.get("defaults", {})
    if not isinstance(raw_devices, Mapping) or not raw_devices:
        raise PhaseAWaveError("runtime devices must be a non-empty object")
    if not isinstance(raw_proxies, Mapping) or not raw_proxies:
        raise PhaseAWaveError("runtime proxies must be a non-empty object")
    if not isinstance(raw_defaults, Mapping):
        raise PhaseAWaveError("runtime defaults must be an object")

    devices: dict[str, RuntimeDevice] = {}
    for alias, raw in raw_devices.items():
        if not isinstance(raw, Mapping):
            raise PhaseAWaveError(f"runtime device {alias!r} must be an object")
        name = _required_text(alias, "device alias")
        media = _paths(raw.get("media"), f"devices.{name}.media")
        media_dirs = _paths(raw.get("media_dirs"), f"devices.{name}.media_dirs")
        if not media and not media_dirs:
            raise PhaseAWaveError(f"runtime device {name!r} has no approved media source")
        devices[name] = RuntimeDevice(
            alias=name,
            adb_id=_required_text(raw.get("adb_id"), f"devices.{name}.adb_id"),
            media=tuple((root / p if not p.is_absolute() else p) for p in media),
            media_dirs=tuple((root / p if not p.is_absolute() else p) for p in media_dirs),
            account_key=(str(raw.get("account_key")).strip() if raw.get("account_key") else None),
        )

    proxies: dict[str, RuntimeProxy] = {}
    for proxy_id, raw in raw_proxies.items():
        if not isinstance(raw, Mapping):
            raise PhaseAWaveError(f"runtime proxy {proxy_id!r} must be an object")
        name = _required_text(proxy_id, "proxy id")
        proxies[name] = RuntimeProxy(
            proxy_id=name,
            http_url=_required_text(raw.get("http_url"), f"proxies.{name}.http_url"),
        )

    def resolve_optional(value: Any) -> Path | None:
        if value in (None, ""):
            return None
        p = Path(_required_text(value, "runtime path"))
        return root / p if not p.is_absolute() else p

    preset = Path(str(raw_defaults.get("preset_config", "config/tiktok-boost-presets.example.json")))
    if not preset.is_absolute():
        preset = root / preset
    try:
        hierarchy_port = int(raw_defaults.get("preferred_hierarchy_port", 8912))
    except (TypeError, ValueError) as exc:
        raise PhaseAWaveError("preferred_hierarchy_port must be an integer") from exc
    if not 1 <= hierarchy_port <= 65535:
        raise PhaseAWaveError("preferred_hierarchy_port must be 1..65535")

    return PhaseARuntime(
        devices=devices,
        proxies=proxies,
        defaults=RuntimeDefaults(
            preset_config=preset,
            reservations=resolve_optional(raw_defaults.get("reservations")),
            history=resolve_optional(raw_defaults.get("history")),
            candidates=resolve_optional(raw_defaults.get("candidates")),
            warmup_compiled=resolve_optional(raw_defaults.get("warmup_compiled")),
            preferred_hierarchy_port=hierarchy_port,
        ),
    )


def validate_runtime_for_plan(plan: SchedulePlan, runtime: PhaseARuntime) -> None:
    for wave in plan.waves:
        for task in wave.tasks:
            if task.app != "tiktok":
                raise PhaseAWaveError(f"Phase A executor only supports app='tiktok', got {task.app!r}")
            if task.mode not in {"boost", "boost_prepare", "phase_a"}:
                raise PhaseAWaveError(f"unsupported TikTok Phase A mode: {task.mode!r}")
            if task.device not in runtime.devices:
                raise PhaseAWaveError(f"schedule device {task.device!r} is missing from runtime map")
            if task.proxy_id not in runtime.proxies:
                raise PhaseAWaveError(f"schedule proxy {task.proxy_id!r} is missing from runtime map")
            if not task.preset:
                raise PhaseAWaveError(f"schedule task for {task.device!r} must name a Boost Phase A preset")


def build_task_command(
    task: ScheduledTask,
    runtime: PhaseARuntime,
    *,
    python_executable: str,
    root: Path,
    seed: int,
    apply: bool,
) -> list[str]:
    device = runtime.devices[task.device]
    proxy = runtime.proxies[task.proxy_id]
    defaults = runtime.defaults
    cmd = [
        python_executable,
        str(root / "scripts" / "tiktok_boost_prepare_preset.py"),
        "--config", str(defaults.preset_config),
        "--preset", str(task.preset),
        "--device", device.adb_id,
        "--proxy-id", task.proxy_id,
        "--seed", str(seed),
        "--preferred-hierarchy-port", str(defaults.preferred_hierarchy_port),
    ]
    for path in device.media:
        cmd.extend(["--media", str(path)])
    for path in device.media_dirs:
        cmd.extend(["--media-dir", str(path)])
    account_key = task.account_key or device.account_key
    if account_key:
        cmd.extend(["--account-key", account_key])
    if defaults.reservations:
        cmd.extend(["--reservations", str(defaults.reservations)])
    if defaults.history:
        cmd.extend(["--history", str(defaults.history)])
    if defaults.candidates:
        cmd.extend(["--candidates", str(defaults.candidates)])
    if defaults.warmup_compiled:
        cmd.extend(["--warmup-compiled", str(defaults.warmup_compiled)])
    # The child gets host/port only after proxy readiness has already succeeded.
    from .proxy_readiness import parse_http_proxy
    endpoint = parse_http_proxy(proxy.http_url)
    cmd.extend(["--proxy-host", endpoint.host, "--proxy-port", str(endpoint.port)])
    if apply:
        cmd.extend(["--ready", "--apply"])
    return cmd
