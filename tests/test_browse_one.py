from genfarmer_automation.browse_one import (
    BrowseOneError,
    EXPECTED_BROWSE_ONE_ROUTE,
    created_run_binding,
    exact_bound_device_id,
    validate_browse_one_flow,
)
from genfarmer_automation.flow import FlowDocument
from genfarmer_automation.run_binding import RunBinding


def node(node_id, action):
    return {"id": node_id, "data": {"action": action}}


def linear_flow(actions):
    nodes = [node(f"n{i}", action) for i, action in enumerate(actions)]
    edges = [
        {"id": f"e{i}", "source": f"n{i}", "target": f"n{i+1}"}
        for i in range(len(nodes) - 1)
    ]
    return FlowDocument.from_flow({"nodes": nodes, "edges": edges})


def binding(*device_ids):
    return RunBinding(
        run_id="run-1",
        app_id="app-1",
        task_id="task-1",
        status="2",
        created_at="2026-09-08T01:00:00Z",
        updated_at=None,
        device_ids=tuple(device_ids),
    )


def test_exact_browse_one_route_is_accepted():
    flow = linear_flow(EXPECTED_BROWSE_ONE_ROUTE)
    assert validate_browse_one_flow(flow) == EXPECTED_BROWSE_ONE_ROUTE


def test_stop_app_or_extra_swipe_is_rejected():
    flow = linear_flow(("Start", "StartApp", "Pause", "Swipe", "Swipe", "StopApp", "Stop"))
    try:
        validate_browse_one_flow(flow)
    except BrowseOneError:
        pass
    else:
        raise AssertionError("unsafe long/closing flow should be rejected")


def test_exact_device_binding_only():
    value = binding("other", "device-1")
    assert exact_bound_device_id(value, "device-1") == "device-1"
    assert exact_bound_device_id(value, "device") is None
    assert exact_bound_device_id(value, "DEVICE-1") is None


def test_created_run_binding_requires_single_matching_record():
    payload = {
        "data": {
            "id": "run-new",
            "appId": "app-1",
            "taskId": "task-1",
            "status": 0,
            "devices": {"list": [{"id": "device-1"}]},
        }
    }
    value = created_run_binding(payload, app_id="app-1", task_id="task-1")
    assert value is not None
    assert value.run_id == "run-new"


def test_created_run_binding_rejects_wrong_task():
    payload = {"id": "run-new", "appId": "app-1", "taskId": "other"}
    assert created_run_binding(payload, app_id="app-1", task_id="task-1") is None
