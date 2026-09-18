import json
from pathlib import Path

from genfarmer_automation.interaction_trace import (
    console_safe_text,
    trace_event,
    trace_text_artifact,
    truncate_text,
)


def test_trace_event_writes_private_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("GF_INTERACTION_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("GF_INTERACTION_TRACE_DEVICE", "device:5555")
    monkeypatch.delenv("GF_INTERACTION_TRACE_CONSOLE", raising=False)

    sequence = trace_event(
        "unit-test",
        category="test",
        answer=42,
        values=("a", "b"),
    )

    assert isinstance(sequence, int)
    files = list(tmp_path.glob("trace-*.jsonl"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8").splitlines()[-1])
    assert payload["device"] == "device:5555"
    assert payload["category"] == "test"
    assert payload["event"] == "unit-test"
    assert payload["details"]["answer"] == 42
    assert payload["details"]["values"] == ["a", "b"]


def test_trace_text_artifact_writes_xml_and_pointer(tmp_path, monkeypatch):
    monkeypatch.setenv("GF_INTERACTION_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("GF_INTERACTION_TRACE_DEVICE", "device:5555")

    path = trace_text_artifact(
        "fyp-live",
        "<hierarchy><node text=\"LIVE\" /></hierarchy>",
        suffix=".xml",
        category="hierarchy",
        provider="helper",
    )

    assert path is not None
    artifact = Path(path)
    assert artifact.exists()
    assert artifact.suffix == ".xml"
    assert "LIVE" in artifact.read_text(encoding="utf-8")


def test_binary_adb_payload_is_summarized_instead_of_decoded():
    payload = b"\x89PNG\r\n\x1a\n\x00\xff\x10\x00binary"
    rendered = truncate_text(payload, 500)
    assert rendered.startswith("<binary bytes=")
    assert "sha256=" in rendered
    assert "\ufffd" not in rendered


def test_console_safe_text_escapes_characters_cp1252_cannot_encode():
    rendered = console_safe_text("binary replacement: \ufffd and emoji: \U0001f680", "cp1252")
    assert "\\ufffd" in rendered
    assert "\\U0001f680" in rendered


def test_trace_event_accepts_binary_details_without_console_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GF_INTERACTION_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("GF_INTERACTION_TRACE_DEVICE", "device:5555")
    monkeypatch.setenv("GF_INTERACTION_TRACE_CONSOLE", "1")

    sequence = trace_event(
        "binary-output",
        category="adb",
        stdout=b"\x89PNG\r\n\x1a\n\x00\xff\x10\x00binary",
    )

    assert isinstance(sequence, int)
    payload = json.loads(
        next(tmp_path.glob("trace-*.jsonl")).read_text(encoding="utf-8").splitlines()[-1]
    )
    assert payload["details"]["stdout"].startswith("<binary bytes=")
    assert "binary-output" in capsys.readouterr().out
