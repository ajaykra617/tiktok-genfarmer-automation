from types import SimpleNamespace

import pytest

from genfarmer_automation.adb_observer import DeviceObservation, InterruptKind
from genfarmer_automation.runtime_recovery import RecoveryBudget, RecoveryLimits
from genfarmer_automation.runtime_supervisor import (
    RuntimeSupervisorError,
    TikTokRuntimeSupervisor,
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


class FakeObserver:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def observe(self):
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        if isinstance(value, BaseException):
            raise value
        return value


class DeepFakeObserver(FakeObserver):
    def __init__(self, values, deep_values):
        super().__init__(values)
        self.deep_values = list(deep_values)
        self.deep_index = 0

    def observe_deep(self):
        value = self.deep_values[min(self.deep_index, len(self.deep_values) - 1)]
        self.deep_index += 1
        if isinstance(value, BaseException):
            raise value
        return value


class FakeRuntime:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def factory(self, *_args, **_kwargs):
        outer = self

        class Runtime:
            def ensure_foreground(self):
                outer.calls += 1
                return outer.result

        return Runtime()


class FakeActions:
    def __init__(self):
        self.stopped = []

    def stop_package(self, package):
        self.stopped.append(package)


def test_healthy_runtime_needs_no_recovery():
    supervisor = TikTokRuntimeSupervisor(
        "device:5555",
        observer=FakeObserver([obs()]),
        sleeper=lambda _seconds: None,
    )
    supervisor.ensure_ready()
    assert supervisor.snapshot().recovery_budget_used == {}


def test_stability_gate_requires_consecutive_healthy_observations():
    observer = FakeObserver([obs(), obs(), obs(), obs(), obs(), obs()])
    supervisor = TikTokRuntimeSupervisor(
        "device:5555",
        observer=observer,
        sleeper=lambda _seconds: None,
    )
    supervisor.ensure_stable(apply=False, consecutive=3, interval_seconds=0)
    assert observer.index >= 6
    assert supervisor.snapshot().recovery_budget_used == {}


def test_stability_gate_prefers_deep_checkpoint_observations():
    observer = DeepFakeObserver(
        [obs(), obs(), obs(), obs(), obs()],
        [obs(), obs(), obs()],
    )
    supervisor = TikTokRuntimeSupervisor(
        "device:5555",
        observer=observer,
        sleeper=lambda _seconds: None,
    )
    supervisor.ensure_stable(apply=False, consecutive=3, interval_seconds=0)
    assert observer.deep_index == 3


def test_stability_gate_recovers_anr_found_only_by_deep_observation():
    runtime = FakeRuntime(SimpleNamespace(success=True, reason="ok"))
    observer = DeepFakeObserver(
        [obs(), obs(), obs(), obs(), obs(), obs()],
        [
            obs(interrupt=InterruptKind.APP_NOT_RESPONDING),
            obs(),
            obs(),
            obs(),
        ],
    )
    supervisor = TikTokRuntimeSupervisor(
        "device:5555",
        observer=observer,
        runtime_factory=runtime.factory,
        sleeper=lambda _seconds: None,
        budget=RecoveryBudget(RecoveryLimits(app_restarts=2)),
    )
    supervisor.ensure_stable(apply=True, consecutive=3, interval_seconds=0)
    assert runtime.calls == 1
    assert supervisor.snapshot().recovery_budget_used == {"restart_app": 1}


def test_stability_gate_rejects_invalid_parameters():
    supervisor = TikTokRuntimeSupervisor(
        "device:5555",
        observer=FakeObserver([obs()]),
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(ValueError, match="consecutive"):
        supervisor.ensure_stable(consecutive=0)
    with pytest.raises(ValueError, match="interval_seconds"):
        supervisor.ensure_stable(interval_seconds=6)


def test_anr_consumes_one_restart_and_requires_proven_recovery():
    runtime = FakeRuntime(SimpleNamespace(success=True, reason="ok"))
    supervisor = TikTokRuntimeSupervisor(
        "device:5555",
        observer=FakeObserver([obs(interrupt=InterruptKind.APP_NOT_RESPONDING), obs()]),
        runtime_factory=runtime.factory,
        sleeper=lambda _seconds: None,
    )
    supervisor.ensure_ready()
    assert runtime.calls == 1
    assert supervisor.snapshot().recovery_budget_used == {"restart_app": 1}


def test_permission_dialog_uses_bounded_recovery():
    calls = []

    def recover(device, *, observer):
        calls.append((device, observer))
        return SimpleNamespace(success=True, reason="ok")

    observer = FakeObserver(
        [
            obs(package="com.google.android.permissioncontroller", interrupt=InterruptKind.ANDROID_PERMISSION_DIALOG),
            obs(),
        ]
    )
    supervisor = TikTokRuntimeSupervisor(
        "device:5555",
        observer=observer,
        permission_recoverer=recover,
        sleeper=lambda _seconds: None,
    )
    supervisor.ensure_ready()
    assert len(calls) == 1
    assert supervisor.snapshot().recovery_budget_used == {"recover_permission": 1}


def test_observation_adb_timeout_retries_once():
    supervisor = TikTokRuntimeSupervisor(
        "device:5555",
        observer=FakeObserver([RuntimeError("adb command timed out after 12s"), obs()]),
        sleeper=lambda _seconds: None,
    )
    supervisor.ensure_ready()
    assert supervisor.snapshot().recovery_budget_used == {"retry_adb": 1}


def test_read_only_hierarchy_operation_retries_once():
    calls = {"n": 0}
    supervisor = TikTokRuntimeSupervisor("device:5555", observer=FakeObserver([obs()]), sleeper=lambda _s: None)

    def operation():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("no healthy hierarchy source after helper-service recovery")
        return "ok"

    assert supervisor.run_read_only(operation) == "ok"
    assert calls["n"] == 2
    assert supervisor.snapshot().recovery_budget_used == {"retry_hierarchy": 1}


def test_read_only_semantic_failure_is_never_retried():
    calls = {"n": 0}
    supervisor = TikTokRuntimeSupervisor("device:5555", observer=FakeObserver([obs()]), sleeper=lambda _s: None)

    def operation():
        calls["n"] += 1
        raise RuntimeError("expected unique Search control but found 2")

    with pytest.raises(RuntimeError, match="unique Search"):
        supervisor.run_read_only(operation)
    assert calls["n"] == 1
    assert supervisor.snapshot().recovery_budget_used == {}


def test_recovery_budget_exhaustion_fails_closed():
    runtime = FakeRuntime(SimpleNamespace(success=True, reason="ok"))
    budget = RecoveryBudget(RecoveryLimits(app_restarts=0))
    supervisor = TikTokRuntimeSupervisor(
        "device:5555",
        observer=FakeObserver([obs(interrupt=InterruptKind.APP_NOT_RESPONDING)]),
        runtime_factory=runtime.factory,
        budget=budget,
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(RuntimeSupervisorError, match="budget exhausted"):
        supervisor.ensure_ready()
    assert runtime.calls == 0


def test_hard_restart_force_stops_only_tiktok_and_reproves_stability():
    runtime = FakeRuntime(SimpleNamespace(success=True, reason="ok"))
    actions = FakeActions()
    supervisor = TikTokRuntimeSupervisor(
        "device:5555",
        observer=FakeObserver([obs()]),
        actions=actions,
        runtime_factory=runtime.factory,
        sleeper=lambda _seconds: None,
        budget=RecoveryBudget(RecoveryLimits(app_restarts=2)),
    )

    supervisor.hard_restart(reason="checkpoint detected a stalled UI", settle_seconds=0)

    assert actions.stopped == ["com.zhiliaoapp.musically"]
    assert runtime.calls == 1
    assert supervisor.snapshot().recovery_budget_used == {"restart_app": 1}


def test_hard_restart_fails_closed_when_budget_is_exhausted():
    runtime = FakeRuntime(SimpleNamespace(success=True, reason="ok"))
    actions = FakeActions()
    supervisor = TikTokRuntimeSupervisor(
        "device:5555",
        observer=FakeObserver([obs()]),
        actions=actions,
        runtime_factory=runtime.factory,
        sleeper=lambda _seconds: None,
        budget=RecoveryBudget(RecoveryLimits(app_restarts=0)),
    )

    with pytest.raises(RuntimeSupervisorError, match="hard-restart budget exhausted"):
        supervisor.hard_restart(reason="stalled")

    assert actions.stopped == []
    assert runtime.calls == 0
