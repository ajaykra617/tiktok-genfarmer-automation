import pytest

from scripts.tiktok_warmup_session import _checkpoint_plan
from genfarmer_automation.warmup_session import WarmupSessionError


def test_checkpoint_plan_preserves_original_schedule():
    checkpoint = {
        "plan": {
            "video_count": 3,
            "watch_seconds": [4.1, 7.2, 5.3],
            "seed": 123,
            "max_session_seconds": 900.0,
            "step_retries": 1,
            "failure_budget": 2,
        }
    }
    plan = _checkpoint_plan(checkpoint)
    assert plan.video_count == 3
    assert plan.watch_seconds == (4.1, 7.2, 5.3)
    assert plan.seed == 123


def test_checkpoint_plan_rejects_mismatched_schedule_length():
    checkpoint = {
        "plan": {
            "video_count": 3,
            "watch_seconds": [4.1, 7.2],
            "seed": 123,
            "max_session_seconds": 900.0,
            "step_retries": 1,
            "failure_budget": 2,
        }
    }
    with pytest.raises(WarmupSessionError, match="video schedule"):
        _checkpoint_plan(checkpoint)
