from genfarmer_automation.adb_observer import DeviceObservation, InterruptKind
from genfarmer_automation.runtime_recovery import (
    RecoveryAction,
    RecoveryBudget,
    RecoveryDecision,
    RecoveryLimits,
    RuntimeFailureKind,
    classify_error,
    classify_observation,
)


def obs(*, package="com.zhiliaoapp.musically", interrupt=InterruptKind.NONE, state="device"):
    return DeviceObservation(
        device="device:5555",
        adb_state=state,
        foreground_package=package,
        foreground_activity="Activity",
        tiktok_foreground=package == "com.zhiliaoapp.musically",
        interrupt=interrupt,
    )


def test_classify_healthy_observation():
    decision = classify_observation(obs())
    assert decision.kind is RuntimeFailureKind.HEALTHY
    assert decision.action is RecoveryAction.NONE
    assert decision.retryable is False


def test_classify_anr_as_bounded_restart():
    decision = classify_observation(obs(interrupt=InterruptKind.APP_NOT_RESPONDING))
    assert decision.kind is RuntimeFailureKind.APP_HUNG
    assert decision.action is RecoveryAction.RESTART_APP
    assert decision.retryable is True


def test_classify_permission_dialog_uses_specific_recovery():
    decision = classify_observation(
        obs(
            package="com.google.android.permissioncontroller",
            interrupt=InterruptKind.ANDROID_PERMISSION_DIALOG,
        )
    )
    assert decision.kind is RuntimeFailureKind.UI_STATE_RECOVERABLE
    assert decision.action is RecoveryAction.RECOVER_PERMISSION


def test_classify_background_tiktok_as_foreground_restore():
    decision = classify_observation(obs(package="com.google.android.apps.nexuslauncher"))
    assert decision.kind is RuntimeFailureKind.UI_STATE_RECOVERABLE
    assert decision.action is RecoveryAction.RESTORE_FOREGROUND


def test_classify_hierarchy_failure_is_readonly_retryable():
    decision = classify_error(
        "no healthy hierarchy source after helper-service recovery and compressed/standard uiautomator fallback"
    )
    assert decision.kind is RuntimeFailureKind.HIERARCHY_TEMPORARY
    assert decision.action is RecoveryAction.RETRY_HIERARCHY
    assert decision.retryable is True


def test_classify_adb_timeout_is_transient():
    decision = classify_error("adb command timed out after 12s")
    assert decision.kind is RuntimeFailureKind.ADB_TRANSIENT
    assert decision.action is RecoveryAction.RETRY_ADB

def test_classify_resilient_adb_read_timeout_is_transient():
    decision = classify_error(
        "adb read-only command timed out after 5.0s; transport recovery did not restore a healthy channel"
    )
    assert decision.kind is RuntimeFailureKind.ADB_TRANSIENT
    assert decision.action is RecoveryAction.RETRY_ADB


def test_unknown_semantic_failure_fails_closed():
    decision = classify_error("expected unique Comments control but found 2")
    assert decision.kind is RuntimeFailureKind.AUTOMATION_FAILURE
    assert decision.action is RecoveryAction.FAIL
    assert decision.retryable is False


def test_recovery_budget_consumes_only_up_to_limit():
    budget = RecoveryBudget(RecoveryLimits(hierarchy_retries=1))
    decision = RecoveryDecision(
        RuntimeFailureKind.HIERARCHY_TEMPORARY,
        RecoveryAction.RETRY_HIERARCHY,
        True,
        "temporary",
    )
    assert budget.consume(decision) is True
    assert budget.consume(decision) is False
    assert budget.snapshot() == {"retry_hierarchy": 1}


def test_nonretryable_decision_never_consumes_budget():
    budget = RecoveryBudget()
    decision = RecoveryDecision(
        RuntimeFailureKind.AUTOMATION_FAILURE,
        RecoveryAction.FAIL,
        False,
        "semantic failure",
    )
    assert budget.consume(decision) is False
    assert budget.snapshot() == {}
