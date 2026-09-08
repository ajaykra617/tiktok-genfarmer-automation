from genfarmer_automation.feed_anchor import (
    EXPECTED_FEED_ANCHOR_LAB_ROUTE,
    FeedAnchorError,
    validate_feed_anchor_lab_flow,
)
from genfarmer_automation.flow import FlowDocument


def node(node_id, action):
    return {"id": node_id, "data": {"action": action}}


def linear_flow(actions):
    nodes = [node(f"n{i}", action) for i, action in enumerate(actions)]
    edges = [
        {"id": f"e{i}", "source": f"n{i}", "target": f"n{i+1}"}
        for i in range(len(nodes) - 1)
    ]
    return FlowDocument.from_flow({"nodes": nodes, "edges": edges})


def test_exact_feed_anchor_lab_route_is_accepted():
    flow = linear_flow(EXPECTED_FEED_ANCHOR_LAB_ROUTE)
    assert validate_feed_anchor_lab_flow(flow) == EXPECTED_FEED_ANCHOR_LAB_ROUTE


def test_missing_element_exists_is_rejected():
    flow = linear_flow(("Start", "StartApp", "Pause", "Screenshot", "Stop"))
    try:
        validate_feed_anchor_lab_flow(flow)
    except FeedAnchorError:
        pass
    else:
        raise AssertionError("feed-anchor lab without ElementExists should fail")


def test_extra_mutating_action_is_rejected():
    flow = linear_flow(("Start", "StartApp", "Pause", "ElementExists", "Touch", "Screenshot", "Stop"))
    try:
        validate_feed_anchor_lab_flow(flow)
    except FeedAnchorError:
        pass
    else:
        raise AssertionError("feed-anchor qualification must remain read-only")
