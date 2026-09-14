import pytest

from genfarmer_automation.boost_share_handoff import (
    find_tiktok_share_target,
    is_system_share_surface,
)
from genfarmer_automation.native_ui import NativeUiAmbiguous


def _xml(*nodes: str) -> str:
    return '<hierarchy rotation="0">' + ''.join(nodes) + '</hierarchy>'


def _node(text: str, bounds: str, *, package: str = "android", clickable: str = "true") -> str:
    return (
        f'<node text="{text}" content-desc="" resource-id="" '
        f'class="android.widget.TextView" package="{package}" '
        f'clickable="{clickable}" enabled="true" bounds="{bounds}" />'
    )


def test_system_share_surface_recognizes_android_resolver():
    assert is_system_share_surface("android", ".app.ResolverActivity")
    assert is_system_share_surface("com.android.intentresolver", ".ChooserActivity")
    assert not is_system_share_surface("com.zhiliaoapp.musically", ".MainActivity")


def test_tiktok_share_target_requires_exact_semantic_match():
    doc = _xml(
        _node("Messages", "[0,0][100,100]"),
        _node("TikTok", "[100,0][200,100]"),
    )
    assert find_tiktok_share_target(doc).text == "TikTok"


def test_tiktok_share_target_fails_closed_when_ambiguous():
    doc = _xml(
        _node("TikTok", "[0,0][100,100]"),
        _node("TikTok", "[100,0][200,100]"),
    )
    with pytest.raises(NativeUiAmbiguous):
        find_tiktok_share_target(doc)
