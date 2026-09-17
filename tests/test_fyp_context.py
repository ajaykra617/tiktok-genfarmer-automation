from genfarmer_automation.fyp_context import prove_fyp_context


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


def test_standard_fyp_with_comments_is_proven():
    proof = prove_fyp_context(
        xml(
            node(text="For You", bounds="[200,0][320,80]"),
            node(**{"content-desc": "Comments 42", "bounds": "[800,300][900,400]"}),
        )
    )
    assert proof.passed
    assert "for-you-tab" in proof.signals
    assert "comments-control" in proof.signals


def test_live_fyp_variant_is_proven_without_standard_video_anchor():
    proof = prove_fyp_context(
        xml(
            node(text="For You", bounds="[200,0][320,80]"),
            node(text="Tap to watch LIVE", bounds="[100,400][500,500]"),
            node(text="Repost to followers", bounds="[100,600][500,680]"),
        )
    )
    assert proof.passed
    assert "live-card" in proof.signals
    assert "repost-affordance" in proof.signals


def test_bare_for_you_tab_is_not_enough():
    proof = prove_fyp_context(xml(node(text="For You")))
    assert not proof.passed
    assert proof.signals == ("for-you-tab",)


def test_non_fyp_screen_is_not_proven():
    proof = prove_fyp_context(xml(node(text="Search"), node(text="Tap to watch LIVE")))
    assert not proof.passed
