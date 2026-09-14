import pytest

from genfarmer_automation.native_ui import NativeUiNotFound
from genfarmer_automation.warmup_features import (
    find_comments_node,
    find_creator_profile_entry,
    find_feed_source_node,
    prove_comments_context,
    prove_profile_context,
)


def xml(*nodes: str) -> str:
    return '<hierarchy rotation="0">' + ''.join(nodes) + '</hierarchy>'


def node(**attrs) -> str:
    base = {
        "text": "",
        "content-desc": "",
        "resource-id": "",
        "class": "android.view.View",
        "package": "com.zhiliaoapp.musically",
        "clickable": "true",
        "enabled": "true",
        "bounds": "[0,0][100,100]",
    }
    base.update(attrs)
    encoded = " ".join(f'{key}="{value}"' for key, value in base.items())
    return f"<node {encoded} />"


def test_feed_source_finds_exact_following():
    doc = xml(
        node(text="Following", bounds="[100,0][220,80]"),
        node(text="For You", bounds="[220,0][340,80]"),
    )
    assert find_feed_source_node(doc, "following").text == "Following"
    assert find_feed_source_node(doc, "fyp").text == "For You"


def test_creator_entry_uses_avatar_not_bottom_profile_tab():
    doc = xml(
        node(text="Profile", bounds="[0,900][100,1000]"),
        node(**{"content-desc": "Alice avatar", "bounds": "[800,200][900,300]"}),
    )
    match = find_creator_profile_entry(doc)
    assert match.content_desc == "Alice avatar"


def test_creator_entry_fails_without_avatar_evidence():
    with pytest.raises(NativeUiNotFound):
        find_creator_profile_entry(xml(node(text="Profile")))


def test_comments_prefers_explicit_comments_control():
    doc = xml(
        node(text="some comment text", bounds="[0,0][500,300]"),
        node(**{"content-desc": "Comments 42", "bounds": "[800,300][900,400]"}),
    )
    assert find_comments_node(doc).content_desc == "Comments 42"


def test_comments_context_proven_by_add_comment():
    proof = prove_comments_context(xml(node(text="Add comment...")))
    assert proof.passed
    assert "add-comment" in proof.matched_terms


def test_profile_context_requires_two_indicators():
    one = prove_profile_context(xml(node(text="Followers")))
    assert not one.passed
    two = prove_profile_context(xml(node(text="Followers"), node(text="Likes", bounds="[0,100][100,200]")))
    assert two.passed
