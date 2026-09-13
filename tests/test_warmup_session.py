from pathlib import Path

import pytest

from genfarmer_automation.warmup_session import (
    WarmupSessionError,
    build_plan,
    completed_index,
    extract_shareable_path,
    step_passed,
)


def test_build_plan_is_seeded_and_bounded():
    a = build_plan(
        video_count=4,
        watch_min_seconds=5,
        watch_max_seconds=9,
        seed=123,
        max_session_minutes=20,
        step_retries=1,
        failure_budget=2,
    )
    b = build_plan(
        video_count=4,
        watch_min_seconds=5,
        watch_max_seconds=9,
        seed=123,
        max_session_minutes=20,
        step_retries=1,
        failure_budget=2,
    )
    assert a.watch_seconds == b.watch_seconds
    assert len(a.watch_seconds) == 4
    assert all(5 <= value <= 9 for value in a.watch_seconds)
    assert a.max_session_seconds == 1200


def test_build_plan_rejects_more_than_one_hour():
    with pytest.raises(ValueError):
        build_plan(
            video_count=3,
            watch_min_seconds=1,
            watch_max_seconds=2,
            seed=1,
            max_session_minutes=61,
            step_retries=0,
            failure_budget=0,
        )


def test_extract_shareable_path_takes_last_result():
    text = "Shareable result: evidence/a.json\nnoise\nShareable result: evidence/b.json\n"
    assert extract_shareable_path(text) == "evidence/b.json"


def test_step_pass_requires_process_and_payload_success():
    assert step_passed(0, {"status": "PASS"})
    assert not step_passed(1, {"status": "PASS"})
    assert not step_passed(0, {"status": "BLOCKED"})
    assert not step_passed(0, None)


def test_completed_index_validates_checkpoint():
    assert completed_index({"completed_steps": 2}, total=5) == 2
    with pytest.raises(WarmupSessionError):
        completed_index({"completed_steps": 6}, total=5)
