import pytest

from genfarmer_automation.warmup_step import (
    ExecutionPhase,
    VerificationLevel,
    adb_fallback_allowed,
    choose_verification_level,
)


def test_full_selector_verification_wins():
    decision = choose_verification_level(
        selector_pre=True,
        selector_post=True,
        foreground_pre=True,
        foreground_post=True,
    )
    assert decision.level is VerificationLevel.FULL_SELECTOR


def test_foreground_continuity_is_explicitly_degraded():
    decision = choose_verification_level(
        selector_pre=None,
        selector_post=None,
        foreground_pre=True,
        foreground_post=True,
    )
    assert decision.level is VerificationLevel.FOREGROUND_CONTINUITY
    assert decision.selector_pre is False
    assert decision.selector_post is False


def test_missing_foreground_postcondition_fails_closed():
    with pytest.raises(RuntimeError):
        choose_verification_level(
            selector_pre=None,
            selector_post=None,
            foreground_pre=True,
            foreground_post=False,
        )


def test_adb_fallback_only_before_execute_request():
    assert adb_fallback_allowed(ExecutionPhase.BEFORE_RUN_CREATE)
    assert adb_fallback_allowed(ExecutionPhase.RUN_CREATE_FAILED)
    assert not adb_fallback_allowed(ExecutionPhase.RUN_CREATED)
    assert not adb_fallback_allowed(ExecutionPhase.EXECUTE_REQUEST_SENT)
