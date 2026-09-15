import pytest

from genfarmer_automation.warm_scroll import WarmScrollError, build_warm_scroll_plan


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
