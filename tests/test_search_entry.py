import pytest

from genfarmer_automation.native_ui import NativeUiAmbiguous, NativeUiNotFound
from genfarmer_automation.search_entry import wait_for_search_editable


def xml(*nodes: str) -> str:
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


def node(*, cls="android.view.View", text="", desc="", bounds="[0,0][100,100]") -> str:
    return (
        f'<node text="{text}" content-desc="{desc}" resource-id="" class="{cls}" '
        f'package="com.zhiliaoapp.musically" clickable="true" enabled="true" bounds="{bounds}" />'
    )


def test_search_editable_is_returned_immediately():
    captures = [xml(node(cls="android.widget.EditText", desc="Search"))]
    result = wait_for_search_editable(lambda: captures[0], package="com.zhiliaoapp.musically")
    assert result.attempts == 1
    assert result.node.class_name.endswith("EditText")


def test_search_editable_waits_for_accessibility_settle():
    captures = [
        xml(node(text="Search")),
        xml(node(text="Search")),
        xml(node(cls="android.widget.EditText", desc="Search")),
    ]
    delays = []

    def capture():
        return captures.pop(0)

    result = wait_for_search_editable(
        capture,
        package="com.zhiliaoapp.musically",
        attempts=3,
        settle_delays=(0.1, 0.2),
        sleeper=delays.append,
    )

    assert result.attempts == 3
    assert delays == [0.1, 0.2]


def test_search_editable_exhaustion_fails_closed():
    with pytest.raises(NativeUiNotFound, match="after 2 bounded hierarchy checks"):
        wait_for_search_editable(
            lambda: xml(node(text="Search")),
            package="com.zhiliaoapp.musically",
            attempts=2,
            settle_delays=(0,),
            sleeper=lambda _seconds: None,
        )


def test_search_editable_ambiguity_is_not_retried():
    calls = {"n": 0}

    def capture():
        calls["n"] += 1
        return xml(
            node(cls="android.widget.EditText", desc="Search", bounds="[0,0][100,100]"),
            node(cls="android.widget.EditText", desc="Search", bounds="[0,100][100,200]"),
        )

    with pytest.raises(NativeUiAmbiguous):
        wait_for_search_editable(
            capture,
            package="com.zhiliaoapp.musically",
            attempts=4,
            sleeper=lambda _seconds: None,
        )

    assert calls["n"] == 1
