from genfarmer_automation.run_binding import extract_run_bindings, newest_for_app


def test_extracts_nested_run_binding_and_devices():
    payload = {
        "data": {
            "runs": [
                {
                    "id": "run-1",
                    "appId": "app-1",
                    "taskId": "task-1",
                    "status": 2,
                    "createdAt": "2026-09-08T01:00:00Z",
                    "devices": {"enabled": True, "list": [{"id": "dev-a"}, {"id": "dev-b"}]},
                }
            ]
        }
    }
    values = extract_run_bindings(payload)
    assert len(values) == 1
    assert values[0].run_id == "run-1"
    assert values[0].app_id == "app-1"
    assert values[0].task_id == "task-1"
    assert values[0].status == "2"
    assert values[0].device_ids == ("dev-a", "dev-b")


def test_boolean_device_metadata_is_never_treated_as_identifier():
    payload = {
        "id": "run-1",
        "appId": "app-1",
        "taskId": "task-1",
        "devices": {
            "enabled": True,
            "primary": False,
            "list": [{"id": "dev-a", "enabled": True}],
        },
    }
    value = extract_run_bindings(payload)[0]
    assert value.device_ids == ("dev-a",)


def test_ignores_unrelated_objects_without_app_and_task_ids():
    payload = {
        "data": [
            {"id": "app-1", "name": "app"},
            {"id": "task-1", "appId": "app-1"},
            {"id": "run-1", "taskId": "task-1"},
        ]
    }
    assert extract_run_bindings(payload) == []


def test_device_ids_field_is_supported_and_deduped():
    payload = {
        "id": "run-1",
        "appId": "app-1",
        "taskId": "task-1",
        "deviceIds": ["dev-a", "dev-a", "dev-b"],
    }
    value = extract_run_bindings(payload)[0]
    assert value.device_ids == ("dev-a", "dev-b")


def test_newest_for_app_prefers_latest_created_timestamp():
    payload = [
        {"id": "old", "appId": "app-1", "taskId": "task-1", "createdAt": "2026-09-08T01:00:00Z"},
        {"id": "new", "appId": "app-1", "taskId": "task-1", "createdAt": "2026-09-08T02:00:00Z"},
        {"id": "other", "appId": "app-2", "taskId": "task-2", "createdAt": "2026-09-08T03:00:00Z"},
    ]
    selected = newest_for_app(extract_run_bindings(payload), "app-1")
    assert selected is not None
    assert selected.run_id == "new"
