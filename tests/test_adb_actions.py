import pytest

from genfarmer_automation.adb_actions import AdbActions


def test_tap_uses_runtime_coordinate(monkeypatch):
    actions = AdbActions("device")
    seen = []
    monkeypatch.setattr(actions, "_run", lambda args: seen.append(list(args)) or "ok")
    actions.tap(10, 20)
    assert seen == [["shell", "input", "tap", "10", "20"]]


def test_input_text_encodes_spaces_and_rejects_unqualified_characters(monkeypatch):
    actions = AdbActions("device")
    seen = []
    monkeypatch.setattr(actions, "_run", lambda args: seen.append(list(args)) or "ok")
    actions.input_text("hello world")
    assert seen[-1] == ["shell", "input", "text", "hello%sworld"]
    with pytest.raises(ValueError):
        actions.input_text("unsafe;command")
    with pytest.raises(ValueError):
        actions.input_text("emoji 🚀")


def test_stop_package_validates_name(monkeypatch):
    actions = AdbActions("device")
    monkeypatch.setattr(actions, "_run", lambda args: "ok")
    actions.stop_package("com.zhiliaoapp.musically")
    with pytest.raises(ValueError):
        actions.stop_package("com.bad package")
