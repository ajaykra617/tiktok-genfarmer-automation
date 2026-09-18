from types import SimpleNamespace

import pytest

from genfarmer_automation.adb_transport import (
    AdbFailureKind,
    AdbHealth,
    AdbTransport,
    AdbTransportError,
    _RawTimeout,
)


def completed(stdout=b"", stderr=b"", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_read_only_timeout_recovers_then_retries(tmp_path, monkeypatch):
    transport = AdbTransport("192.168.4.138:5555", lock_root=tmp_path)
    calls = {"raw": 0, "recover": 0}

    def raw(args, *, timeout, device_scoped=True):
        calls["raw"] += 1
        if calls["raw"] == 1:
            raise _RawTimeout("timeout")
        return completed(stdout=b"ok\n")

    def recover():
        calls["recover"] += 1
        return AdbHealth(True, "device", True, "healthy")

    monkeypatch.setattr(transport, "_raw", raw)
    monkeypatch.setattr(
        transport,
        "_health_unlocked",
        lambda: AdbHealth(False, "offline", False, "device offline"),
    )
    monkeypatch.setattr(transport, "_recover_unlocked", recover)

    result = transport.run(["shell", "echo", "ok"], timeout=1.0, mutation=False)

    assert result.stdout_text() == "ok"
    assert result.attempts == 2
    assert result.recovered is True
    assert calls == {"raw": 2, "recover": 1}


def test_mutation_timeout_is_never_replayed_when_transport_is_healthy(tmp_path, monkeypatch):
    transport = AdbTransport("192.168.4.138:5555", lock_root=tmp_path)
    calls = {"raw": 0}

    def raw(args, *, timeout, device_scoped=True):
        calls["raw"] += 1
        raise _RawTimeout("timeout")

    monkeypatch.setattr(transport, "_raw", raw)
    monkeypatch.setattr(
        transport,
        "_health_unlocked",
        lambda: AdbHealth(True, "device", True, "get-state and shell channel healthy"),
    )

    with pytest.raises(AdbTransportError, match="transport remained healthy") as exc:
        transport.run(["shell", "input", "swipe", "1", "2", "3", "4"], timeout=0.5, mutation=True)

    assert exc.value.kind is AdbFailureKind.TIMEOUT
    assert exc.value.mutation_ambiguous is True
    assert exc.value.transport_healthy is True
    assert calls["raw"] == 1


def test_mutation_timeout_reports_unhealthy_transport_without_replay(tmp_path, monkeypatch):
    transport = AdbTransport("192.168.4.143:5555", lock_root=tmp_path)
    calls = {"raw": 0}

    def raw(args, *, timeout, device_scoped=True):
        calls["raw"] += 1
        raise _RawTimeout("timeout")

    monkeypatch.setattr(transport, "_raw", raw)
    monkeypatch.setattr(
        transport,
        "_health_unlocked",
        lambda: AdbHealth(False, "offline", False, "device offline"),
    )

    with pytest.raises(AdbTransportError, match="transport remained unhealthy") as exc:
        transport.run(["shell", "input", "tap", "10", "20"], timeout=0.5, mutation=True)

    assert exc.value.mutation_ambiguous is True
    assert exc.value.transport_healthy is False
    assert calls["raw"] == 1


def test_network_recovery_is_per_device_and_never_kills_shared_server(tmp_path, monkeypatch):
    transport = AdbTransport(
        "192.168.4.138:5555",
        lock_root=tmp_path,
        sleeper=lambda _seconds: None,
    )
    seen = []
    health_values = [
        AdbHealth(False, "offline", False, "device offline"),
        AdbHealth(True, "device", True, "healthy"),
    ]

    monkeypatch.setattr(transport, "_start_server_unlocked", lambda: seen.append(("start-server",)))

    def health():
        return health_values.pop(0)

    def raw(args, *, timeout, device_scoped=True):
        seen.append(tuple(args))
        return completed(stdout=b"connected\n")

    monkeypatch.setattr(transport, "_health_unlocked", health)
    monkeypatch.setattr(transport, "_raw", raw)

    result = transport._recover_unlocked()

    assert result.ready is True
    assert ("disconnect", "192.168.4.138:5555") in seen
    assert ("connect", "192.168.4.138:5555") in seen
    assert not any("kill-server" in item for call in seen for item in call)


def test_ensure_ready_uses_recovery_after_failed_probe(tmp_path, monkeypatch):
    transport = AdbTransport("192.168.4.138:5555", lock_root=tmp_path)
    monkeypatch.setattr(
        transport,
        "_health_unlocked",
        lambda: AdbHealth(False, "offline", False, "device offline"),
    )
    monkeypatch.setattr(
        transport,
        "_recover_unlocked",
        lambda: AdbHealth(True, "device", True, "healthy"),
    )

    health = transport.ensure_ready()

    assert health.ready is True
    assert health.state == "device"
