import pytest

from genfarmer_automation.native_ui import (
    NativeUiAmbiguous,
    NativeUiNotFound,
    find_editable_node,
    find_semantic_node,
    parse_bounds,
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


def test_parse_bounds():
    assert parse_bounds("[10,20][30,50]") == (10, 20, 30, 50)
    assert parse_bounds("[10,20][10,50]") is None


def test_semantic_match_prefers_exact_text():
    doc = xml(
        node(text="Post", bounds="[0,0][100,100]"),
        node(**{"content-desc": "Post settings", "bounds": "[0,100][300,200]"}),
    )
    match = find_semantic_node(doc, ["Post"])
    assert match.text == "Post"
    assert match.center == (50, 50)


def test_semantic_match_fails_closed_on_missing():
    with pytest.raises(NativeUiNotFound):
        find_semantic_node(xml(node(text="Next")), ["Publish"])


def test_editable_node_unique():
    doc = xml(node(**{"class": "android.widget.EditText", "content-desc": "Describe your post"}))
    match = find_editable_node(doc, hints=["describe your post"])
    assert match.class_name.endswith("EditText")


def test_editable_node_ambiguous_without_hint():
    doc = xml(
        node(**{"class": "android.widget.EditText", "bounds": "[0,0][100,100]"}),
        node(**{"class": "android.widget.EditText", "bounds": "[0,100][100,200]"}),
    )
    with pytest.raises(NativeUiAmbiguous):
        find_editable_node(doc)
