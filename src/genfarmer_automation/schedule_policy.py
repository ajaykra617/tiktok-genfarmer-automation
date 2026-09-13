"""Validation helpers for device/proxy barrier schedules.

The client scheduler requirement is modeled as explicit waves. All tasks in one
wave may run concurrently; the next wave may not start until the current wave
finishes. A proxy identity may be reused across different applications, but the
same application may not use the same proxy identity on two different devices
inside one concurrent wave.

This module plans and validates. It does not rotate a proxy, change account
state, or bypass any platform control.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class SchedulePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class ScheduledTask:
    device: str
    app: str
    mode: str
    proxy_id: str
    preset: str | None = None
    account_key: str | None = None


@dataclass(frozen=True)
class ScheduleWave:
    name: str
    tasks: tuple[ScheduledTask, ...]


@dataclass(frozen=True)
class SchedulePlan:
    waves: tuple[ScheduleWave, ...]
    interval_min_minutes: float
    interval_max_minutes: float


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchedulePolicyError(f"{field} must be a non-empty string")
    return value.strip()


def _task_from_mapping(raw: Mapping[str, Any]) -> ScheduledTask:
    return ScheduledTask(
        device=_required_text(raw.get("device"), "device"),
        app=_required_text(raw.get("app"), "app").casefold(),
        mode=_required_text(raw.get("mode"), "mode").casefold(),
        proxy_id=_required_text(raw.get("proxy_id"), "proxy_id"),
        preset=(str(raw["preset"]).strip() if raw.get("preset") else None),
        account_key=(str(raw["account_key"]).strip() if raw.get("account_key") else None),
    )


def validate_wave(wave: ScheduleWave) -> None:
    devices: set[str] = set()
    app_proxy: set[tuple[str, str]] = set()
    for task in wave.tasks:
        if task.device in devices:
            raise SchedulePolicyError(
                f"wave {wave.name!r} schedules device {task.device!r} more than once"
            )
        devices.add(task.device)
        key = (task.app, task.proxy_id)
        if key in app_proxy:
            raise SchedulePolicyError(
                f"wave {wave.name!r} reuses proxy {task.proxy_id!r} for app {task.app!r}"
            )
        app_proxy.add(key)


def load_schedule_plan(payload: Mapping[str, Any]) -> SchedulePlan:
    raw_waves = payload.get("waves")
    if not isinstance(raw_waves, Sequence) or isinstance(raw_waves, (str, bytes)) or not raw_waves:
        raise SchedulePolicyError("waves must be a non-empty array")

    interval = payload.get("interval_minutes", [30, 73])
    if (
        not isinstance(interval, Sequence)
        or isinstance(interval, (str, bytes))
        or len(interval) != 2
    ):
        raise SchedulePolicyError("interval_minutes must contain [min,max]")
    try:
        interval_min = float(interval[0])
        interval_max = float(interval[1])
    except (TypeError, ValueError) as exc:
        raise SchedulePolicyError("interval_minutes values must be numeric") from exc
    if interval_min < 0 or interval_max < interval_min:
        raise SchedulePolicyError("invalid interval_minutes range")

    waves: list[ScheduleWave] = []
    names: set[str] = set()
    for index, raw_wave in enumerate(raw_waves, 1):
        if not isinstance(raw_wave, Mapping):
            raise SchedulePolicyError(f"wave {index} must be an object")
        name = _required_text(raw_wave.get("name", f"wave-{index}"), "wave.name")
        if name in names:
            raise SchedulePolicyError(f"duplicate wave name: {name}")
        names.add(name)
        raw_tasks = raw_wave.get("tasks")
        if not isinstance(raw_tasks, Sequence) or isinstance(raw_tasks, (str, bytes)) or not raw_tasks:
            raise SchedulePolicyError(f"wave {name!r} tasks must be a non-empty array")
        tasks = tuple(_task_from_mapping(raw) for raw in raw_tasks if isinstance(raw, Mapping))
        if len(tasks) != len(raw_tasks):
            raise SchedulePolicyError(f"wave {name!r} contains a non-object task")
        wave = ScheduleWave(name=name, tasks=tasks)
        validate_wave(wave)
        waves.append(wave)

    return SchedulePlan(
        waves=tuple(waves),
        interval_min_minutes=interval_min,
        interval_max_minutes=interval_max,
    )


def plan_summary(plan: SchedulePlan) -> dict[str, Any]:
    apps = sorted({task.app for wave in plan.waves for task in wave.tasks})
    devices = sorted({task.device for wave in plan.waves for task in wave.tasks})
    proxies = sorted({task.proxy_id for wave in plan.waves for task in wave.tasks})
    return {
        "waves": len(plan.waves),
        "tasks": sum(len(wave.tasks) for wave in plan.waves),
        "apps": apps,
        "devices": len(devices),
        "proxy_ids": len(proxies),
        "barrier_between_waves": True,
        "same_app_proxy_uniqueness": True,
        "interval_minutes": [plan.interval_min_minutes, plan.interval_max_minutes],
    }
