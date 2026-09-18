from genfarmer_automation.fyp_context import FypState, classify_fyp_context
from genfarmer_automation.native_ui import find_semantic_node
from genfarmer_automation.search_entry import wait_for_search_editable
from genfarmer_automation.tiktok_semantics import ACCOUNT_TABS, SEARCH
from genfarmer_automation.warmup_features import (
    find_comments_node,
    find_feed_source_node,
    prove_profile_context,
)


TIKTOK = "com.zhiliaoapp.musically"


def xml(*nodes: str) -> str:
    return '<hierarchy rotation="0">' + "".join(nodes) + "</hierarchy>"


def node(**attrs) -> str:
    base = {
        "text": "",
        "content-desc": "",
        "resource-id": "",
        "class": "android.view.View",
        "package": TIKTOK,
        "clickable": "true",
        "enabled": "true",
        "bounds": "[0,0][100,100]",
    }
    base.update(attrs)
    encoded = " ".join(f'{key}="{value}"' for key, value in base.items())
    return f"<node {encoded} />"


def test_observed_french_for_you_and_following_labels_are_supported():
    doc = xml(
        node(text="Suivis", bounds="[0,0][100,80]"),
        node(text="Pour toi", bounds="[100,0][200,80]"),
    )
    assert find_feed_source_node(doc, "for-you").text == "Pour toi"
    assert find_feed_source_node(doc, "following").text == "Suivis"


def test_french_comments_and_profile_context_are_supported():
    comments = xml(node(**{"content-desc": "Commentaires 629"}))
    assert find_comments_node(comments).content_desc == "Commentaires 629"

    profile = xml(
        node(text="Abonnés", bounds="[0,0][100,100]"),
        node(text="Abonnements", bounds="[100,0][200,100]"),
        node(text="J\'aime", bounds="[200,0][300,100]"),
        node(text="Vidéos", bounds="[300,0][400,100]"),
    )
    proof = prove_profile_context(profile)
    assert proof.passed is True
    assert set(proof.matched_terms) >= {"followers", "following"}


def test_french_search_control_and_edittext_are_supported():
    search_doc = xml(node(**{"content-desc": "Rechercher"}))
    assert find_semantic_node(search_doc, SEARCH).content_desc == "Rechercher"

    edit_doc = xml(node(**{"class": "android.widget.EditText", "content-desc": "Rechercher"}))
    result = wait_for_search_editable(lambda: edit_doc, package=TIKTOK)
    assert result.attempts == 1
    assert result.node.class_name.endswith("EditText")


def test_french_account_tab_is_supported():
    doc = xml(node(text="Utilisateurs"))
    assert find_semantic_node(doc, ACCOUNT_TABS).text == "Utilisateurs"


def test_french_loading_text_is_not_misclassified_as_content():
    proof = classify_fyp_context(
        xml(node(text="Pour toi"), node(text="Chargement..."))
    )
    assert proof.passed is False
    assert proof.state is FypState.LOADING
    assert "loading-indicator" in proof.signals


def test_french_sponsored_variant_is_content():
    proof = classify_fyp_context(
        xml(node(text="Pour toi"), node(text="Sponsorisé"))
    )
    assert proof.passed is True
    assert proof.state is FypState.CONTENT
    assert "sponsored-card" in proof.signals
