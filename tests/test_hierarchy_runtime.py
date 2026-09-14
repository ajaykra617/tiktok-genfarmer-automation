import subprocess

from genfarmer_automation import hierarchy_runtime as hr


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
        return '<hierarchy rotation="0"><node /></hierarchy>'

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
    payload = b'<hierarchy rotation="0"><node class="android.view.View" /></hierarchy>'

    def fake_adb(device, *args, timeout=8.0):
        commands.append(args)
        return subprocess.CompletedProcess(["adb"], 0, stdout=payload, stderr=b"")

    monkeypatch.setattr(hr, "_adb", fake_adb)
    xml = hr.capture_uiautomator_once("device-1")
    assert xml.startswith("<hierarchy")
    assert commands[0] == ("exec-out", "uiautomator", "dump", "--compressed", "/dev/tty")
