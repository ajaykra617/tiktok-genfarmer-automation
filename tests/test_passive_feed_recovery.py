import pytest

from genfarmer_automation.adb_actions import AdbActionError
from genfarmer_automation.passive_feed_recovery import run_passive_feed_advance


def test_normal_passive_swipe_does_not_reset_checkpoint():
    calls = {"swipe": 0, "reset": 0, "prove": 0}

    def swipe():
        calls["swipe"] += 1

    result = run_passive_feed_advance(
        swipe,
        reset_checkpoint=lambda _reason: calls.__setitem__("reset", calls["reset"] + 1),
        prove_checkpoint=lambda: calls.__setitem__("prove", calls["prove"] + 1),
    )

    assert result.recovered_via_checkpoint is False
    assert calls == {"swipe": 1, "reset": 0, "prove": 0}


def test_healthy_transport_ambiguous_swipe_resets_without_replay():
    calls = {"swipe": 0, "reset": 0, "prove": 0}

    def swipe():
        calls["swipe"] += 1
        raise AdbActionError(
            "adb mutation timed out after 6.0s; transport remained healthy; mutation outcome is ambiguous",
            mutation_ambiguous=True,
            transport_healthy=True,
            failure_kind="timeout",
        )

    def reset(_reason):
        calls["reset"] += 1

    def prove():
        calls["prove"] += 1
        return "FYP"

    result = run_passive_feed_advance(
        swipe,
        reset_checkpoint=reset,
        prove_checkpoint=prove,
    )

    assert result.recovered_via_checkpoint is True
    assert "transport remained healthy" in result.reason
    assert calls == {"swipe": 1, "reset": 1, "prove": 1}


def test_unhealthy_transport_ambiguous_swipe_fails_closed():
    calls = {"swipe": 0, "reset": 0, "prove": 0}

    def swipe():
        calls["swipe"] += 1
        raise AdbActionError(
            "adb mutation timed out; transport remained unhealthy; mutation outcome is ambiguous",
            mutation_ambiguous=True,
            transport_healthy=False,
        )

    with pytest.raises(AdbActionError, match="transport remained unhealthy"):
        run_passive_feed_advance(
            swipe,
            reset_checkpoint=lambda _reason: calls.__setitem__("reset", calls["reset"] + 1),
            prove_checkpoint=lambda: calls.__setitem__("prove", calls["prove"] + 1),
        )

    assert calls == {"swipe": 1, "reset": 0, "prove": 0}


def test_checkpoint_proof_failure_propagates_without_replaying_swipe():
    calls = {"swipe": 0, "reset": 0, "prove": 0}

    def swipe():
        calls["swipe"] += 1
        raise AdbActionError(
            "ambiguous",
            mutation_ambiguous=True,
            transport_healthy=True,
        )

    def reset(_reason):
        calls["reset"] += 1

    def prove():
        calls["prove"] += 1
        raise RuntimeError("qualified FYP could not be restored")

    with pytest.raises(RuntimeError, match="qualified FYP"):
        run_passive_feed_advance(
            swipe,
            reset_checkpoint=reset,
            prove_checkpoint=prove,
        )

    assert calls == {"swipe": 1, "reset": 1, "prove": 1}
