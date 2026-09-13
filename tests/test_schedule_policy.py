import pytest

from genfarmer_automation.schedule_policy import (
    SchedulePolicyError,
    load_schedule_plan,
    plan_summary,
)


def test_same_proxy_is_allowed_across_different_apps_in_one_wave():
    plan = load_schedule_plan(
        {
            "interval_minutes": [30, 73],
            "waves": [
                {
                    "name": "w1",
                    "tasks": [
                        {"device": "d1", "app": "tiktok", "mode": "warmup", "proxy_id": "p1"},
                        {"device": "d2", "app": "reddit", "mode": "warmup", "proxy_id": "p1"},
                    ],
                }
            ],
        }
    )
    assert plan_summary(plan)["same_app_proxy_uniqueness"] is True


def test_same_app_cannot_share_proxy_in_concurrent_wave():
    with pytest.raises(SchedulePolicyError, match="reuses proxy"):
        load_schedule_plan(
            {
                "waves": [
                    {
                        "name": "w1",
                        "tasks": [
                            {"device": "d1", "app": "tiktok", "mode": "warmup", "proxy_id": "p1"},
                            {"device": "d2", "app": "tiktok", "mode": "warmup", "proxy_id": "p1"},
                        ],
                    }
                ]
            }
        )


def test_device_cannot_have_two_concurrent_tasks():
    with pytest.raises(SchedulePolicyError, match="more than once"):
        load_schedule_plan(
            {
                "waves": [
                    {
                        "name": "w1",
                        "tasks": [
                            {"device": "d1", "app": "tiktok", "mode": "warmup", "proxy_id": "p1"},
                            {"device": "d1", "app": "reddit", "mode": "warmup", "proxy_id": "p2"},
                        ],
                    }
                ]
            }
        )


def test_barrier_plan_summary_counts_waves_and_tasks():
    plan = load_schedule_plan(
        {
            "waves": [
                {"name": "w1", "tasks": [{"device": "d1", "app": "tiktok", "mode": "warmup", "proxy_id": "p1"}]},
                {"name": "w2", "tasks": [{"device": "d1", "app": "reddit", "mode": "warmup", "proxy_id": "p1"}]},
            ]
        }
    )
    summary = plan_summary(plan)
    assert summary["waves"] == 2
    assert summary["tasks"] == 2
    assert summary["barrier_between_waves"] is True
