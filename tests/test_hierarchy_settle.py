from genfarmer_automation.hierarchy_settle import (
    _service_recovery_ports,
    wrap_discover_helper_port,
)


class FakeHierarchyError(RuntimeError):
    pass


def test_service_recovery_ports_extracts_unique_started_helpers():
    attempts = (
        "helper:8912:fail:HierarchyRuntimeError",
        "helper:8912:service-recovery:started",
        "helper:8912:recovery-fail:HierarchyRuntimeError",
        "helper:8912:service-recovery:started",
        "helper:7912:service-recovery:started",
    )
    assert _service_recovery_ports(attempts) == (8912, 7912)


def test_settle_wrapper_recovers_helper_that_needs_extra_startup_time():
    attempts = (
        "helper:8912:fail:HierarchyRuntimeError",
        "helper:8912:service-recovery:started",
        "helper:8912:recovery-fail:HierarchyRuntimeError",
    )
    capture_calls = []
    sleeps = []

    def original(device, *, preferred_port=None, probe_timeout=1.5, max_ports=16):
        return None, attempts

    def capture(device, port, *, timeout):
        capture_calls.append((device, port, timeout))
        if len(capture_calls) < 3:
            raise FakeHierarchyError("helper still starting")
        return "<hierarchy />"

    discover = wrap_discover_helper_port(
        original,
        capture,
        FakeHierarchyError,
        sleep=sleeps.append,
        settle_delays=(0.5, 1.0, 1.5),
    )

    port, result_attempts = discover(
        "device-1",
        preferred_port=8912,
        probe_timeout=1.2,
    )

    assert port == 8912
    assert sleeps == [0.5, 1.0, 1.5]
    assert capture_calls == [
        ("device-1", 8912, 1.5),
        ("device-1", 8912, 1.5),
        ("device-1", 8912, 1.5),
    ]
    assert "helper:8912:service-settle-1:fail:FakeHierarchyError" in result_attempts
    assert "helper:8912:service-settle-2:fail:FakeHierarchyError" in result_attempts
    assert "helper:8912:service-settle-3:pass" in result_attempts


def test_settle_wrapper_keeps_normal_failure_path_fast_without_started_service():
    attempts = ("helper:8912:fail:HierarchyRuntimeError",)
    captures = []
    sleeps = []

    def original(device, *, preferred_port=None, probe_timeout=1.5, max_ports=16):
        return None, attempts

    def capture(*args, **kwargs):
        captures.append((args, kwargs))
        raise AssertionError("capture must not be called")

    discover = wrap_discover_helper_port(
        original,
        capture,
        FakeHierarchyError,
        sleep=sleeps.append,
    )

    port, result_attempts = discover("device-1", preferred_port=8912)
    assert port is None
    assert result_attempts == attempts
    assert captures == []
    assert sleeps == []


def test_settle_wrapper_is_bounded_when_helper_never_becomes_ready():
    attempts = (
        "helper:8912:service-recovery:started",
        "helper:8912:recovery-fail:HierarchyRuntimeError",
    )
    capture_count = 0

    def original(device, *, preferred_port=None, probe_timeout=1.5, max_ports=16):
        return None, attempts

    def capture(device, port, *, timeout):
        nonlocal capture_count
        capture_count += 1
        raise FakeHierarchyError("still unavailable")

    discover = wrap_discover_helper_port(
        original,
        capture,
        FakeHierarchyError,
        sleep=lambda value: None,
        settle_delays=(0.1, 0.2),
    )

    port, result_attempts = discover("device-1")
    assert port is None
    assert capture_count == 2
    assert result_attempts[-1] == "helper:8912:service-settle-2:fail:FakeHierarchyError"
