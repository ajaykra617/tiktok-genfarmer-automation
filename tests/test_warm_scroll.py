import pytest

from genfarmer_automation.warm_scroll import (
    WarmScrollError,
    build_warm_scroll_plan,
    is_transient_bootstrap_failure,
)


def test_seeded_warm_scroll_plan_is_reproducible():
    first = build_warm_scroll_plan(
        videos=3,
        watch_min_seconds=5,
        watch_max_seconds=10,
        seed=42,
        max_session_minutes=8,
    )
    second = build_warm_scroll_plan(
        videos=3,
        watch_min_seconds=5,
        watch_max_seconds=10,
        seed=42,
        max_session_minutes=8,
    )
    assert first == second
    assert len(first.watch_seconds) == 3
    assert all(5 <= value <= 10 for value in first.watch_seconds)


def test_warm_scroll_plan_rejects_invalid_video_count():
    with pytest.raises(WarmScrollError, match="videos"):
        build_warm_scroll_plan(
            videos=0,
            watch_min_seconds=5,
            watch_max_seconds=10,
            seed=1,
            max_session_minutes=8,
        )


def test_warm_scroll_plan_rejects_inverted_watch_bounds():
    with pytest.raises(WarmScrollError, match="watch interval"):
        build_warm_scroll_plan(
            videos=3,
            watch_min_seconds=10,
            watch_max_seconds=5,
            seed=1,
            max_session_minutes=8,
        )


def test_warm_scroll_plan_caps_short_boost_session():
    with pytest.raises(WarmScrollError, match="max_session_minutes"):
        build_warm_scroll_plan(
            videos=3,
            watch_min_seconds=5,
            watch_max_seconds=10,
            seed=1,
            max_session_minutes=16,
        )


def test_transient_bootstrap_failure_accepts_hierarchy_unavailable_reason():
    assert is_transient_bootstrap_failure(
        {
            "status": "BLOCKED",
            "reason": "no healthy hierarchy source after helper-service recovery and fallback",
        }
    )


def test_transient_bootstrap_failure_accepts_no_counts_fyp_recovery_reason():
    assert is_transient_bootstrap_failure(
        {
            "status": "BLOCKED",
            "reason": (
                "qualified For You feed could not be restored with bounded semantic/BACK recovery; "
                "last counts=None"
            ),
        }
    )


def test_transient_bootstrap_failure_rejects_semantic_failure():
    assert not is_transient_bootstrap_failure(
        {"status": "BLOCKED", "reason": "For You tap did not retain qualified FYP; counts=(0, 0)"}
    )
