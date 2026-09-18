from genfarmer_automation.live_diagnostics import collect_live_hints, live_hint_summary


def xml(*nodes: str) -> str:
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


def node(text="", desc="", rid="", bounds="[0,0][100,100]") -> str:
    return (
        f'<node text="{text}" content-desc="{desc}" resource-id="{rid}" '
        f'class="android.view.View" package="com.zhiliaoapp.musically" '
        f'clickable="true" enabled="true" bounds="{bounds}" />'
    )


def test_bare_live_badge_is_collected_for_diagnostics():
    doc = xml(node(text="LIVE", rid="live_badge"))
    summary = live_hint_summary(doc, package="com.zhiliaoapp.musically")
    assert summary["detected"] is True
    assert summary["count"] == 1
    assert summary["nodes"][0]["text"] == "LIVE"


def test_french_en_direct_marker_is_collected():
    hints = collect_live_hints(
        xml(node(desc="Regarder en direct")),
        package="com.zhiliaoapp.musically",
    )
    assert len(hints) == 1
    assert hints[0]["content_desc"] == "Regarder en direct"


def test_unrelated_word_containing_live_substring_is_not_collected():
    summary = live_hint_summary(
        xml(node(text="delivery")),
        package="com.zhiliaoapp.musically",
    )
    assert summary["detected"] is False
    assert summary["count"] == 0
