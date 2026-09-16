import pytest

from genfarmer_automation.client_demo_plan import PASSIVE_DEMO_FEATURES, build_client_demo_plan


def test_client_demo_plan_is_deterministic_and_complete():
    first = build_client_demo_plan(seed=42, videos=3, watch_min_seconds=4, watch_max_seconds=7)
    second = build_client_demo_plan(seed=42, videos=3, watch_min_seconds=4, watch_max_seconds=7)
    assert first == second
    assert set(first.feature_order) == set(PASSIVE_DEMO_FEATURES)
    assert len(first.feature_order) == len(PASSIVE_DEMO_FEATURES)
    assert len(first.watch_seconds) == 3
    assert all(4 <= value <= 7 for value in first.watch_seconds)


def test_client_demo_plan_changes_with_seed():
    one = build_client_demo_plan(seed=1)
    two = build_client_demo_plan(seed=2)
    assert one.feature_order != two.feature_order or one.watch_seconds != two.watch_seconds


@pytest.mark.parametrize(
    "kwargs",
    [
        {"videos": 0},
        {"videos": 21},
        {"watch_min_seconds": -1},
        {"watch_min_seconds": 8, "watch_max_seconds": 7},
        {"watch_max_seconds": 61},
    ],
)
def test_client_demo_plan_rejects_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        build_client_demo_plan(seed=42, **kwargs)
