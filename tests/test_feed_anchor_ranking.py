from genfarmer_automation.feed_anchor_ranking import rank_feed_anchor_candidates
from genfarmer_automation.ui_xml import SelectorCandidate


PKG = "com.zhiliaoapp.musically"


def candidate(resource_id, *, score=125):
    return SelectorCandidate(
        kind="resource-id",
        xpath=f"//android.view.View[@resource-id='{resource_id}']",
        class_name="android.view.View",
        occurrences=(1, 1, 1, 1),
        present_in_all=True,
        unique_in_all=True,
        score=score,
    )


def xml(feed_bounds, tiny_bounds="[900,1500][980,1580]"):
    return (
        '<hierarchy rotation="0">'
        f'<node package="{PKG}" class="android.view.View" resource-id="screen" bounds="[0,0][1080,1920]" />'
        f'<node package="{PKG}" class="android.view.View" resource-id="video_feed_container" bounds="{feed_bounds}" />'
        f'<node package="{PKG}" class="android.view.View" resource-id="like_button" bounds="{tiny_bounds}" />'
        '</hierarchy>'
    )


def test_large_centered_feed_container_beats_tiny_action_control():
    snapshots = [xml("[50,180][1030,1750]"), xml("[45,175][1035,1755]")]
    ranked = rank_feed_anchor_candidates(
        [candidate("like_button"), candidate("video_feed_container")],
        snapshots,
        package=PKG,
    )
    assert ranked[0].candidate.xpath.endswith("[@resource-id='video_feed_container']")
    assert ranked[0].median_area_ratio > ranked[1].median_area_ratio
    assert ranked[0].center_coverage_ratio == 1.0


def test_geometry_stability_rewards_consistent_candidate():
    snapshots = [
        (
            '<hierarchy>'
            f'<node package="{PKG}" class="android.view.View" resource-id="screen" bounds="[0,0][1000,1000]" />'
            f'<node package="{PKG}" class="android.view.View" resource-id="feed_stable" bounds="[100,100][900,900]" />'
            f'<node package="{PKG}" class="android.view.View" resource-id="feed_unstable" bounds="[100,100][900,900]" />'
            '</hierarchy>'
        ),
        (
            '<hierarchy>'
            f'<node package="{PKG}" class="android.view.View" resource-id="screen" bounds="[0,0][1000,1000]" />'
            f'<node package="{PKG}" class="android.view.View" resource-id="feed_stable" bounds="[100,100][900,900]" />'
            f'<node package="{PKG}" class="android.view.View" resource-id="feed_unstable" bounds="[250,250][750,750]" />'
            '</hierarchy>'
        ),
    ]
    ranked = rank_feed_anchor_candidates(
        [candidate("feed_unstable"), candidate("feed_stable")],
        snapshots,
        package=PKG,
    )
    assert ranked[0].candidate.xpath.endswith("[@resource-id='feed_stable']")
    assert ranked[0].geometry_stability == 1.0


def test_candidate_without_bounds_is_dropped():
    snapshots = [
        (
            '<hierarchy>'
            f'<node package="{PKG}" class="android.view.View" resource-id="screen" bounds="[0,0][1000,1000]" />'
            f'<node package="{PKG}" class="android.view.View" resource-id="feed" bounds="[0,0][1000,900]" />'
            f'<node package="{PKG}" class="android.view.View" resource-id="missing" />'
            '</hierarchy>'
        )
    ] * 2
    ranked = rank_feed_anchor_candidates(
        [candidate("missing"), candidate("feed")],
        snapshots,
        package=PKG,
    )
    assert len(ranked) == 1
    assert "feed" in ranked[0].candidate.xpath


def test_private_dict_preserves_patch_compatible_candidate_shape():
    snapshots = [xml("[50,180][1030,1750]"), xml("[50,180][1030,1750]")]
    item = rank_feed_anchor_candidates([candidate("video_feed_container")], snapshots, package=PKG)[0]
    payload = item.to_private_dict()
    assert payload["xpath"].endswith("[@resource-id='video_feed_container']")
    assert payload["kind"] == "resource-id"
    assert "rank_score" in payload
