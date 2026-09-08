from genfarmer_automation.browse_one import (
    BrowseOneError,
    EXPECTED_BROWSE_ONE_ROUTE,
    control_window_is_safe,
    created_run_binding,
    exact_bound_device_id,
    validate_browse_one_flow,
)
from genfarmer_automation.flow import FlowDocument
from genfarmer_automation.run_binding import RunBinding
from genfarmer_automation.screen_transition import TransitionDecision, TransitionReport


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


def transition(decision, *, stable_ratio=1.0, changed_ratio=0.0):
    return TransitionReport(
        decision=decision,
        total_points=100,
        baseline_stable_points=round(100 * stable_ratio),
        baseline_stable_ratio=stable_ratio,
        changed_points=round(100 * stable_ratio * changed_ratio),
        changed_ratio_of_stable=changed_ratio,
        changed_cells=0,
        occupied_cells=24,
        stable_range_threshold=16,
        changed_delta_threshold=40,
        reason="test",
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


def test_control_window_accepts_only_trustworthy_quiet_baseline():
    report = transition(TransitionDecision.INCONCLUSIVE_CHANGE, stable_ratio=0.97, changed_ratio=0.0)
    assert control_window_is_safe(report) is True


def test_control_window_rejects_unstable_baseline_even_without_proven_change():
    report = transition(TransitionDecision.INCONCLUSIVE_BASELINE, stable_ratio=0.034, changed_ratio=0.0)
    assert control_window_is_safe(report) is False


def test_control_window_rejects_no_action_transition():
    report = transition(TransitionDecision.PROVEN_CHANGED, stable_ratio=0.97, changed_ratio=0.40)
    assert control_window_is_safe(report) is False
