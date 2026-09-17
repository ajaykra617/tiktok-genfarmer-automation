import pytest

from genfarmer_automation.adb_actions import AdbActionError, AdbActionResult, AdbActions
from genfarmer_automation.adb_observer import InterruptKind
from genfarmer_automation.anr_guarded_actions import AnrGuardedAdbActions


class Observation:
    def __init__(self, interrupt):
        self.interrupt = interrupt


class Observer:
    def __init__(self, interrupts):
        self.interrupts = list(interrupts)
        self.calls = 0

    def observe_deep(self):
        self.calls += 1
        if self.interrupts:
            value = self.interrupts.pop(0)
        else:
            value = InterruptKind.NONE
        return Observation(value)


def test_swipe_is_not_sent_when_anr_is_already_present(monkeypatch):
    observer = Observer([InterruptKind.APP_NOT_RESPONDING])
    actions = AnrGuardedAdbActions("device-1", observer=observer)
    sent = {"count": 0}

    def base_swipe(self, **kwargs):
        sent["count"] += 1
        return AdbActionResult(command="swipe_up_relative", stdout="")

    monkeypatch.setattr(AdbActions, "swipe_up_relative", base_swipe)

    with pytest.raises(AdbActionError, match="before swipe; swipe was not sent"):
        actions.swipe_up_relative(width=1080, height=1920)

    assert sent["count"] == 0
    assert observer.calls == 1


def test_timed_out_swipe_is_reclassified_when_anr_appears(monkeypatch):
    observer = Observer([InterruptKind.NONE, InterruptKind.APP_NOT_RESPONDING])
    actions = AnrGuardedAdbActions("device-1", observer=observer, timeout=12.0, swipe_timeout=6.0)
    observed_timeouts = []

    def base_swipe(self, **kwargs):
        observed_timeouts.append(self.timeout)
        raise AdbActionError("adb action timed out after 6.0s")

    monkeypatch.setattr(AdbActions, "swipe_up_relative", base_swipe)

    with pytest.raises(AdbActionError, match="after timed-out swipe; swipe outcome is ambiguous"):
        actions.swipe_up_relative(width=1080, height=1920)

    assert observed_timeouts == [6.0]
    assert actions.timeout == 12.0
    assert observer.calls == 2


def test_normal_swipe_preserves_generic_timeout_after_call(monkeypatch):
    observer = Observer([InterruptKind.NONE])
    actions = AnrGuardedAdbActions("device-1", observer=observer, timeout=12.0, swipe_timeout=6.0)
    observed_timeouts = []

    def base_swipe(self, **kwargs):
        observed_timeouts.append(self.timeout)
        return AdbActionResult(command="swipe_up_relative", stdout="ok")

    monkeypatch.setattr(AdbActions, "swipe_up_relative", base_swipe)

    result = actions.swipe_up_relative(width=1080, height=1920)

    assert result.stdout == "ok"
    assert observed_timeouts == [6.0]
    assert actions.timeout == 12.0


def test_swipe_timeout_must_be_positive():
    with pytest.raises(ValueError, match="swipe_timeout"):
        AnrGuardedAdbActions("device-1", swipe_timeout=0)
