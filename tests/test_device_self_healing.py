import pytest

from genfarmer_automation.device_self_healing import (
    DeviceWorkerState,
    SelfHealingPolicy,
    retryable_client_failure,
)


def test_cooldown_backoff_caps_at_last_value():
    policy = SelfHealingPolicy(cooldown_seconds=(2.0, 5.0, 10.0), reboot_recommend_after=3)
    assert policy.cooldown_for_failure(1) == 2.0
    assert policy.cooldown_for_failure(2) == 5.0
    assert policy.cooldown_for_failure(3) == 10.0
    assert policy.cooldown_for_failure(8) == 10.0


def test_reboot_is_recommendation_only_after_threshold():
    policy = SelfHealingPolicy(reboot_recommend_after=3)
    assert policy.reboot_approval_recommended(1) is False
    assert policy.reboot_approval_recommended(2) is False
    assert policy.reboot_approval_recommended(3) is True
    assert policy.reboot_approval_recommended(10) is True


def test_runtime_failures_remain_retryable_but_configuration_errors_do_not():
    assert retryable_client_failure("TikTok/Android reported app-not-responding")
    assert retryable_client_failure("no healthy hierarchy source after helper-service recovery")
    assert retryable_client_failure("helper returned invalid hierarchy XML")
    assert not retryable_client_failure("demo media file does not exist")
    assert not retryable_client_failure("candidate file does not contain requested candidate")


def test_policy_rejects_invalid_values():
    with pytest.raises(ValueError):
        SelfHealingPolicy(cooldown_seconds=())
    with pytest.raises(ValueError):
        SelfHealingPolicy(reboot_recommend_after=0)


def test_shared_resource_wait_has_distinct_worker_state():
    assert DeviceWorkerState.WAITING_RESOURCE.value == "waiting_resource"
