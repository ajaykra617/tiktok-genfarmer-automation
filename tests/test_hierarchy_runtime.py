import subprocess

from genfarmer_automation import hierarchy_runtime as hr


XML = '<hierarchy rotation="0"><node class="android.view.View" /></hierarchy>'


def test_extract_embedded_xml_accepts_shell_noise():
    text = "UI hierchary dumped to: /dev/tty\n<hierarchy rotation=\"0\"><node class=\"android.view.View\" /></hierarchy>\n"
    xml = hr._extract_embedded_xml(text)
    assert xml is not None
    assert xml.startswith("<hierarchy")


def test_extract_embedded_xml_rejects_incomplete_xml():
    assert hr._extract_embedded_xml("<hierarchy><node />") is None


def test_candidate_ports_prefers_explicit_hint_then_runtime(monkeypatch):
    monkeypatch.setattr(hr, "runtime_listener_ports", lambda device: (5555, 8912, 10001))
    ports = hr.candidate_ports("device-1", 7777, max_ports=8)
    assert ports[0] == 7777
    assert 8912 in ports
    assert 10001 in ports


def test_candidate_ports_deduplicates_preferred_and_runtime(monkeypatch):
    monkeypatch.setattr(hr, "runtime_listener_ports", lambda device: (8912, 7912))
    ports = hr.candidate_ports("device-1", 8912, max_ports=8)
    assert ports.count(8912) == 1


def test_discover_helper_restarts_identified_uiautomator_service(monkeypatch):
    monkeypatch.setattr(hr, "candidate_ports", lambda device, preferred_port, max_ports=16: (8912,))
    calls = {"capture": 0, "recover": 0}

    def capture(device, port, *, timeout):
        calls["capture"] += 1
        if calls["capture"] == 1:
            raise hr.HierarchyRuntimeError("service stopped")
        return XML

    def recover(device, port, *, timeout=1.0):
        calls["recover"] += 1
        return True

    monkeypatch.setattr(hr, "_capture_helper_once", capture)
    monkeypatch.setattr(hr, "_recover_helper_service_once", recover)
    monkeypatch.setattr(hr.time, "sleep", lambda value: None)

    port, attempts = hr.discover_helper_port("device-1", preferred_port=8912)
    assert port == 8912
    assert calls == {"capture": 2, "recover": 1}
    assert "helper:8912:service-recovery:started" in attempts
    assert "helper:8912:recovery-pass" in attempts


def test_capture_uiautomator_prefers_compressed_tty(monkeypatch):
    commands = []
    payload = XML.encode()

    def fake_adb(device, *args, timeout=8.0):
        commands.append(args)
        return subprocess.CompletedProcess(["adb"], 0, stdout=payload, stderr=b"")

    monkeypatch.setattr(hr, "_adb", fake_adb)
    xml = hr.capture_uiautomator_once("device-1")
    assert xml.startswith("<hierarchy")
    assert commands[0] == ("exec-out", "uiautomator", "dump", "--compressed", "/dev/tty")


def test_batch_retries_transient_helper_sample_before_fallback(monkeypatch):
    monkeypatch.setattr(
        hr,
        "discover_helper_port",
        lambda *args, **kwargs: (8912, ("helper:8912:pass",)),
    )
    calls = {"capture": 0, "fallback": 0}

    def capture(device, port, *, timeout):
        calls["capture"] += 1
        if calls["capture"] == 2:
            raise hr.HierarchyRuntimeError("transient hierarchy race")
        return XML

    def fallback(device, *, timeout=12.0):
        calls["fallback"] += 1
        return XML

    monkeypatch.setattr(hr, "_capture_helper_once", capture)
    monkeypatch.setattr(hr, "capture_uiautomator_once", fallback)
    monkeypatch.setattr(hr.time, "sleep", lambda value: None)

    batch = hr.capture_hierarchy_batch("device-1", count=2, preferred_port=8912)

    assert batch.provider == "genfarmer-helper"
    assert batch.remote_port == 8912
    assert len(batch.snapshots) == 2
    assert calls == {"capture": 3, "fallback": 0}
    assert "helper:8912:sample-2:retry-pass" in batch.attempts


def test_batch_rechecks_helper_service_before_uiautomator(monkeypatch):
    discover_calls = {"count": 0}

    def discover(*args, **kwargs):
        discover_calls["count"] += 1
        return 8912, ("helper:8912:pass",)

    calls = {"capture": 0, "recover": 0, "fallback": 0}

    def capture(device, port, *, timeout):
        calls["capture"] += 1
        # sample 1 succeeds; sample 2 fails twice; service-check retry succeeds.
        if calls["capture"] in {2, 3}:
            raise hr.HierarchyRuntimeError("helper temporarily wedged")
        return XML

    def recover(device, port, *, timeout=1.0):
        calls["recover"] += 1
        return True

    def fallback(device, *, timeout=12.0):
        calls["fallback"] += 1
        return XML

    monkeypatch.setattr(hr, "discover_helper_port", discover)
    monkeypatch.setattr(hr, "_capture_helper_once", capture)
    monkeypatch.setattr(hr, "_recover_helper_service_once", recover)
    monkeypatch.setattr(hr, "capture_uiautomator_once", fallback)
    monkeypatch.setattr(hr.time, "sleep", lambda value: None)

    batch = hr.capture_hierarchy_batch("device-1", count=2, preferred_port=8912)

    assert batch.provider == "genfarmer-helper"
    assert calls == {"capture": 4, "recover": 1, "fallback": 0}
    assert discover_calls["count"] == 1
    assert "helper:8912:sample-2:service-check:pass" in batch.attempts
    assert "helper:8912:sample-2:service-retry-pass" in batch.attempts


def test_batch_uses_bounded_uiautomator_timeout(monkeypatch):
    monkeypatch.setattr(hr, "discover_helper_port", lambda *args, **kwargs: (None, ()))
    observed_timeouts = []

    def fallback(device, *, timeout=12.0):
        observed_timeouts.append(timeout)
        return XML

    monkeypatch.setattr(hr, "capture_uiautomator_once", fallback)

    batch = hr.capture_hierarchy_batch(
        "device-1",
        count=2,
        uiautomator_timeout=3.5,
    )

    assert batch.provider == "adb-uiautomator"
    assert observed_timeouts == [3.5, 3.5]


def test_batch_rejects_nonpositive_uiautomator_timeout():
    try:
        hr.capture_hierarchy_batch("device-1", uiautomator_timeout=0)
    except ValueError as exc:
        assert "uiautomator_timeout" in str(exc)
    else:
        raise AssertionError("expected ValueError")
