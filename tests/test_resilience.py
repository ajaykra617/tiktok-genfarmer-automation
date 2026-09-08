from genfarmer_automation.resilience import (
    ModuleOutcome,
    ResilientSupervisor,
    SupervisorPolicy,
)


def test_success_requires_postcondition():
    states = iter(["feed-a", "feed-b"])
    supervisor = ResilientSupervisor(SupervisorPolicy(local_attempts=1, recovery_attempts=0))
    result = supervisor.run_module(
        module="browse_one",
        observe=lambda: next(states),
        precondition=lambda state: state.startswith("feed"),
        action=lambda _state: "swipe-ok",
        postcondition=lambda state: state == "feed-b",
    )
    assert result.success is True
    assert result.outcome is ModuleOutcome.SUCCESS
    assert result.attempts == 1


def test_action_success_without_postcondition_is_failure():
    states = iter(["feed-a", "feed-a"])
    supervisor = ResilientSupervisor(SupervisorPolicy(local_attempts=1, recovery_attempts=0))
    result = supervisor.run_module(
        module="browse_one",
        observe=lambda: next(states),
        precondition=lambda state: state == "feed-a",
        action=lambda _state: "swipe-node-reported-success",
        postcondition=lambda state: state == "feed-b",
    )
    assert result.success is False
    assert result.outcome is ModuleOutcome.POSTCONDITION_FAILED


def test_known_interrupt_fails_closed_without_handler():
    supervisor = ResilientSupervisor(SupervisorPolicy(local_attempts=1, recovery_attempts=0))
    result = supervisor.run_module(
        module="ensure_ready",
        observe=lambda: "permission-dialog",
        precondition=lambda _state: True,
        action=lambda _state: None,
        postcondition=lambda _state: True,
        interrupt=lambda state: "android_permission_dialog" if state == "permission-dialog" else None,
    )
    assert result.outcome is ModuleOutcome.INTERRUPTED
    assert result.attempts == 0


def test_recovery_can_restore_precondition_once():
    states = iter(["home", "feed", "feed-next"])
    recovered = []
    supervisor = ResilientSupervisor(SupervisorPolicy(local_attempts=1, recovery_attempts=1))
    result = supervisor.run_module(
        module="browse_one",
        observe=lambda: next(states),
        precondition=lambda state: state == "feed",
        action=lambda _state: "swipe",
        postcondition=lambda state: state == "feed-next",
        recover=lambda state: recovered.append(state) is None or True,
    )
    assert result.outcome is ModuleOutcome.SUCCESS
    assert result.recoveries == 1
    assert recovered == ["home"]
