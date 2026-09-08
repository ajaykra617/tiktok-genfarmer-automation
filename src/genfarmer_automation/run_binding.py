"""Read-only helpers for discovering reusable GenFarmer run/task bindings.

The Local API response shape is treated as partially unknown. These helpers scan
nested JSON defensively and only recognize records that expose an id together
with both appId and taskId. Exact identifiers are intended for local/private
evidence; shareable reports should redact them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


def iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def _scalar(value: Any) -> str | None:
    # bool is a subclass of int in Python. Treating True/False as identifiers
    # caused metadata such as devices.enabled=True to leak into device_ids.
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int)) and str(value):
        return str(value)
    return None


def _first(mapping: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _scalar(mapping.get(key))
        if value is not None:
            return value
    return None


def _collect_device_ids(value: Any, *, inside_devices: bool = False) -> list[str]:
    found: list[str] = []

    def add(candidate: Any) -> None:
        value = _scalar(candidate)
        if value is not None and value not in found:
            found.append(value)

    if isinstance(value, Mapping):
        direct = value.get("deviceIds")
        if isinstance(direct, list):
            for item in direct:
                add(item)
        add(value.get("deviceId"))
        if inside_devices:
            add(value.get("id"))

        for key, child in value.items():
            if key == "devices":
                found.extend(x for x in _collect_device_ids(child, inside_devices=True) if x not in found)
            elif key not in {"deviceIds", "deviceId"}:
                found.extend(x for x in _collect_device_ids(child, inside_devices=inside_devices) if x not in found)
    elif isinstance(value, list):
        for child in value:
            found.extend(x for x in _collect_device_ids(child, inside_devices=inside_devices) if x not in found)
    elif inside_devices:
        add(value)
    return found


@dataclass(frozen=True)
class RunBinding:
    run_id: str
    app_id: str
    task_id: str
    status: str | None
    created_at: str | None
    updated_at: str | None
    device_ids: tuple[str, ...]

    def private_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "app_id": self.app_id,
            "task_id": self.task_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "device_ids": list(self.device_ids),
        }


def extract_run_bindings(payload: Any) -> list[RunBinding]:
    bindings: list[RunBinding] = []
    seen: set[str] = set()
    for obj in iter_dicts(payload):
        run_id = _first(obj, "id", "runId", "run_id")
        app_id = _first(obj, "appId", "app_id")
        task_id = _first(obj, "taskId", "task_id")
        if not run_id or not app_id or not task_id or run_id in seen:
            continue
        seen.add(run_id)
        bindings.append(
            RunBinding(
                run_id=run_id,
                app_id=app_id,
                task_id=task_id,
                status=_first(obj, "status"),
                created_at=_first(obj, "createdAt", "created_at"),
                updated_at=_first(obj, "updatedAt", "updated_at"),
                device_ids=tuple(_collect_device_ids(obj)),
            )
        )
    return bindings


def newest_for_app(bindings: Iterable[RunBinding], app_id: str) -> RunBinding | None:
    matches = [item for item in bindings if item.app_id == str(app_id)]
    if not matches:
        return None
    # ISO timestamps sort lexically. Missing timestamps sort before present ones.
    return max(matches, key=lambda item: (item.created_at or item.updated_at or "", item.updated_at or ""))
