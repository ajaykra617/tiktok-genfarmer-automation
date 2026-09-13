from genfarmer_automation.genfarmer_client import GenFarmerHTTPError
from genfarmer_automation.run_bootstrap import (
    RunBootstrapError,
    create_run_with_task_refresh,
    extract_created_task_id,
)


def test_extract_created_task_id_prefers_app_match():
    payload = {
        "data": {
            "id": "task-new",
            "appId": "app-1",
            "name": "Python recovery",
        },
        "user": {"id": 3},
    }
    assert extract_created_task_id(
        payload,
        app_id="app-1",
        task_name="Python recovery",
    ) == "task-new"


def test_extract_created_task_id_accepts_unique_name_when_app_id_omitted():
    payload = {"data": {"id": "task-new", "name": "Python recovery"}}
    assert extract_created_task_id(
        payload,
        app_id="app-1",
        task_name="Python recovery",
    ) == "task-new"


def test_extract_created_task_id_rejects_ambiguous_response():
    payload = {
        "items": [
            {"id": "task-a", "appId": "app-1"},
            {"id": "task-b", "appId": "app-1"},
        ]
    }
    try:
        extract_created_task_id(payload, app_id="app-1", task_name="Python recovery")
    except RunBootstrapError:
        pass
    else:
        raise AssertionError("ambiguous fresh-task response must fail closed")


class FakeClient:
    def __init__(self, *, first_status=None):
        self.first_status = first_status
        self.run_calls = []
        self.task_calls = []

    def create_run(self, *, user_id, task_id, app_id, status=0):
        self.run_calls.append((user_id, task_id, app_id, status))
        if len(self.run_calls) == 1 and self.first_status is not None:
            raise GenFarmerHTTPError(
                "POST",
                "/automation/runs",
                self.first_status,
                {"message": "server-side test failure"},
            )
        return {"data": {"id": "run-new", "taskId": task_id, "appId": app_id}}

    def create_task(self, *, app_id, user_id, name, input_values=None, devices=None):
        self.task_calls.append((app_id, user_id, name, input_values, devices))
        return {"data": {"id": "task-fresh", "appId": app_id, "name": name}}


def test_existing_task_success_does_not_create_task():
    client = FakeClient()
    result = create_run_with_task_refresh(
        client,
        user_id=3,
        app_id="app-1",
        task_id="task-old",
        recovery_task_name="Python recovery",
    )
    assert result.task_id == "task-old"
    assert result.task_refreshed is False
    assert client.task_calls == []


def test_500_refreshes_task_once_and_retries_run():
    client = FakeClient(first_status=500)
    result = create_run_with_task_refresh(
        client,
        user_id=3,
        app_id="app-1",
        task_id="task-old",
        recovery_task_name="Python recovery",
    )
    assert result.task_id == "task-fresh"
    assert result.task_refreshed is True
    assert result.initial_http_status == 500
    assert [call[1] for call in client.run_calls] == ["task-old", "task-fresh"]
    assert len(client.task_calls) == 1
    assert client.task_calls[0][4] == {"enable": True, "list": []}


def test_4xx_is_not_hidden_by_task_refresh():
    client = FakeClient(first_status=400)
    try:
        create_run_with_task_refresh(
            client,
            user_id=3,
            app_id="app-1",
            task_id="task-old",
            recovery_task_name="Python recovery",
        )
    except GenFarmerHTTPError as exc:
        assert exc.status == 400
    else:
        raise AssertionError("4xx must propagate without mutation fallback")
    assert client.task_calls == []
