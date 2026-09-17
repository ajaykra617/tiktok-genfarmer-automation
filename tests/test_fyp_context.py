from genfarmer_automation.fyp_context import FypState, classify_fyp_context, prove_fyp_context


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


def test_standard_fyp_with_comments_is_content():
    proof = classify_fyp_context(
        xml(
            node(text="For You", bounds="[200,0][320,80]"),
            node(**{"content-desc": "Comments 42", "bounds": "[800,300][900,400]"}),
        )
    )
    assert proof.passed
    assert proof.state is FypState.CONTENT
    assert "comments-control" in proof.signals


def test_live_fyp_variant_is_content_without_standard_anchor():
    proof = prove_fyp_context(
        xml(
            node(text="For You", bounds="[200,0][320,80]"),
            node(text="Tap to watch LIVE", bounds="[100,400][500,500]"),
            node(text="Repost to followers", bounds="[100,600][500,680]"),
        )
    )
    assert proof.passed
    assert proof.state is FypState.CONTENT
    assert "live-card" in proof.signals
    assert "repost-affordance" in proof.signals


def test_photo_fyp_variant_is_content():
    proof = classify_fyp_context(
        xml(
            node(text="For You", bounds="[200,0][320,80]"),
            node(text="Swipe to see more", bounds="[100,600][500,680]"),
        )
    )
    assert proof.passed
    assert proof.state is FypState.CONTENT
    assert "photo-card" in proof.signals


def test_sponsored_fyp_variant_is_content():
    proof = classify_fyp_context(
        xml(
            node(text="For You", bounds="[200,0][320,80]"),
            node(text="Sponsored", bounds="[100,600][500,680]"),
        )
    )
    assert proof.passed
    assert proof.state is FypState.CONTENT
    assert "sponsored-card" in proof.signals


def test_shop_fyp_variant_is_content():
    proof = classify_fyp_context(
        xml(
            node(text="For You", bounds="[200,0][320,80]"),
            node(text="View product", bounds="[100,600][500,680]"),
        )
    )
    assert proof.passed
    assert proof.state is FypState.CONTENT
    assert "shop-card" in proof.signals


def test_bare_for_you_tab_is_loading_not_content():
    proof = classify_fyp_context(xml(node(text="For You")))
    assert not proof.passed
    assert proof.state is FypState.LOADING
    assert proof.signals == ("for-you-tab",)


def test_explicit_loading_screen_is_loading():
    proof = classify_fyp_context(xml(node(text="For You"), node(text="Loading...")))
    assert not proof.passed
    assert proof.state is FypState.LOADING
    assert "loading-indicator" in proof.signals
    assert "sponsored-card" not in proof.signals


def test_short_ad_marker_does_not_match_inside_loading_or_other_words():
    for text in ("Loading...", "Heading", "Shadow", "Ready"):
        proof = classify_fyp_context(xml(node(text="For You"), node(text=text)))
        assert not proof.passed
        assert proof.state is FypState.LOADING
        assert "sponsored-card" not in proof.signals


def test_explicit_sponsored_phrase_still_beats_bare_shell():
    proof = classify_fyp_context(
        xml(node(text="For You"), node(text="Paid partnership"))
    )
    assert proof.passed
    assert proof.state is FypState.CONTENT
    assert "sponsored-card" in proof.signals


def test_loading_indicator_wins_over_weak_variant_text():
    proof = classify_fyp_context(
        xml(node(text="For You"), node(text="Loading..."), node(text="Sponsored"))
    )
    assert not proof.passed
    assert proof.state is FypState.LOADING
    assert "loading-indicator" in proof.signals


def test_non_fyp_screen_is_off_fyp_even_with_live_text():
    proof = classify_fyp_context(xml(node(text="Search"), node(text="Tap to watch LIVE")))
    assert not proof.passed
    assert proof.state is FypState.OFF_FYP
