import pytest

from genfarmer_automation.app_resilience import (
    restart_worthy_failure,
    run_checkpointed_stage,
)


def test_runtime_and_hierarchy_faults_are_restart_worthy():
    assert restart_worthy_failure("no healthy hierarchy source after helper-service recovery")
    assert restart_worthy_failure("adb command timed out after 12s")
    assert restart_worthy_failure("qualified FYP anchor is absent; counts=(0, 0)")


def test_timed_out_ui_mutations_are_not_restart_worthy():
    assert not restart_worthy_failure("adb action timed out after 12.0s")
    assert not restart_worthy_failure(
        "adb mutation timed out after 6.0s; transport remained healthy; mutation outcome is ambiguous"
    )
    assert not restart_worthy_failure(
        "TikTok app-not-responding after timed-out swipe; swipe outcome is ambiguous"
    )


def test_anr_before_unsent_swipe_remains_restart_worthy():
    assert restart_worthy_failure("TikTok app-not-responding before swipe; swipe was not sent")


def test_unknown_semantic_failure_is_not_restart_worthy():
    assert not restart_worthy_failure("expected unique Search control but found 2")


def test_checkpointed_stage_restarts_once_then_succeeds():
    calls = {"operation": 0, "restart": 0}
    events = []

    def operation():
        calls["operation"] += 1
        if calls["operation"] == 1:
            raise RuntimeError("qualified FYP anchor is absent; counts=(0, 0)")
        return "PASS"

    def restart(_reason):
        calls["restart"] += 1

    result = run_checkpointed_stage(
        "warm-scroll-video-1",
        operation,
        restart=restart,
        max_restarts=1,
        on_recovery=events.append,
    )

    assert result == "PASS"
    assert calls == {"operation": 2, "restart": 1}
    assert len(events) == 1
    assert events[0].label == "warm-scroll-video-1"


def test_checkpointed_stage_does_not_retry_unknown_semantic_failure():
    calls = {"restart": 0}

    def operation():
        raise RuntimeError("multiple comments controls tied for best runtime match")

    def restart(_reason):
        calls["restart"] += 1

    with pytest.raises(RuntimeError, match="multiple comments controls"):
        run_checkpointed_stage("comments", operation, restart=restart, max_restarts=2)

    assert calls["restart"] == 0


def test_checkpointed_stage_does_not_replay_ambiguous_mutation_timeout():
    calls = {"operation": 0, "restart": 0}

    def operation():
        calls["operation"] += 1
        raise RuntimeError("adb action timed out after 6.0s")

    def restart(_reason):
        calls["restart"] += 1

    with pytest.raises(RuntimeError, match="adb action timed out"):
        run_checkpointed_stage("warm-scroll-video-2", operation, restart=restart, max_restarts=1)

    assert calls == {"operation": 1, "restart": 0}


def test_checkpointed_stage_respects_restart_limit():
    calls = {"restart": 0}

    def operation():
        raise RuntimeError("qualified FYP could not be restored within bounded semantic recovery")

    def restart(_reason):
        calls["restart"] += 1

    with pytest.raises(RuntimeError, match="qualified FYP"):
        run_checkpointed_stage("fyp", operation, restart=restart, max_restarts=1)

    assert calls["restart"] == 1
