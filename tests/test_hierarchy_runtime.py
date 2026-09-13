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
