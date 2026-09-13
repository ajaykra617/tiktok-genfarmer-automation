"""Resilient GenFarmer run creation for a verified app/task lane.

Try the previously observed task once. If the documented POST /automation/runs
returns a server-side 5xx, create one fresh task for the same verified app using
GenFarmer's documented empty-device task shape, then create the run once more.
4xx failures are never hidden and recovery never loops.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from .genfarmer_client import GenFarmerHTTPError


class RunBootstrapError(RuntimeError):
    pass


class MutationClientLike(Protocol):
    def create_run(self, *, user_id: int, task_id: str, app_id: str, status: int = 0) -> Any: ...
    def create_task(self, *, app_id: str, user_id: int, name: str, input_values=None, devices=None) -> Any: ...


@dataclass(frozen=True)
class RunBootstrapResult:
    created_run: Any
    task_id: str
    task_refreshed: bool
    initial_http_status: int | None = None
    initial_error_data: Any = None
    created_task: Any = None


def _iter_dicts(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dicts(child)


def _scalar(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int)) and str(value):
        return str(value)
    return None


def extract_created_task_id(payload: Any, *, app_id: str, task_name: str) -> str:
    """Resolve exactly one new task id without accepting unrelated nested ids."""
    app_matches: list[str] = []
    name_matches: list[str] = []
    for obj in _iter_dicts(payload):
        task_id = _scalar(obj.get("id")) or _scalar(obj.get("taskId"))
        if task_id is None:
            continue
        obj_app = _scalar(obj.get("appId")) or _scalar(obj.get("app_id"))
        obj_name = obj.get("name")
        if obj_app == str(app_id) and task_id not in app_matches:
            app_matches.append(task_id)
        if isinstance(obj_name, str) and obj_name == task_name and task_id not in name_matches:
            name_matches.append(task_id)

    if len(app_matches) == 1:
        return app_matches[0]
    if len(app_matches) > 1:
        overlap = [value for value in app_matches if value in name_matches]
        if len(overlap) == 1:
            return overlap[0]
        raise RunBootstrapError("fresh-task response contained multiple app-matching task ids")
    if len(name_matches) == 1:
        return name_matches[0]
    raise RunBootstrapError("fresh-task response did not expose one unambiguous task id")


def create_run_with_task_refresh(
    client: MutationClientLike,
    *,
    user_id: int,
    app_id: str,
    task_id: str,
    recovery_task_name: str,
) -> RunBootstrapResult:
    """Create a run, self-healing exactly one stale-task-style 5xx failure."""
    try:
        created = client.create_run(user_id=user_id, task_id=task_id, app_id=app_id, status=0)
        return RunBootstrapResult(created_run=created, task_id=str(task_id), task_refreshed=False)
    except GenFarmerHTTPError as exc:
        if exc.method != "POST" or exc.path != "/automation/runs" or not (500 <= exc.status <= 599):
            raise

        task_response = client.create_task(
            app_id=app_id,
            user_id=user_id,
            name=recovery_task_name,
            input_values=[],
            devices={"enable": True, "list": []},
        )
        fresh_task_id = extract_created_task_id(
            task_response,
            app_id=app_id,
            task_name=recovery_task_name,
        )
        created = client.create_run(
            user_id=user_id,
            task_id=fresh_task_id,
            app_id=app_id,
            status=0,
        )
        return RunBootstrapResult(
            created_run=created,
            task_id=fresh_task_id,
            task_refreshed=True,
            initial_http_status=exc.status,
            initial_error_data=exc.data,
            created_task=task_response,
        )
