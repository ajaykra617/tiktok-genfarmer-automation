import json
from pathlib import Path

from genfarmer_automation.interaction_trace import trace_event, trace_text_artifact


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
