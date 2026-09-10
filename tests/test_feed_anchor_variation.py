import pytest

from genfarmer_automation.feed_anchor_qualification import candidates_from_payload
from genfarmer_automation.feed_anchor_variation import (
    FeedAnchorVariationError,
    candidate_counts,
    qualify_across_feed_variants,
    unique_presence_ratio,
)


def _candidate(resource_id="feed_anchor", class_name="android.view.View"):
    return candidates_from_payload([
        {
            "kind": "resource-id",
            "xpath": f"//{class_name}[@resource-id='{resource_id}']",
            "class_name": class_name,
            "occurrences": [1, 1, 1],
            "present_in_all": True,
            "unique_in_all": True,
            "score": 125,
        }
    ])[0]


def _xml(*resource_ids):
    nodes = "".join(
        f'<node package="com.zhiliaoapp.musically" class="android.view.View" resource-id="{value}" />'
        for value in resource_ids
    )
    return f'<hierarchy rotation="0">{nodes}</hierarchy>'


def test_candidate_counts_across_snapshots():
    candidate = _candidate()
    assert candidate_counts(
        candidate,
        [_xml("feed_anchor"), _xml("feed_anchor")],
        package="com.zhiliaoapp.musically",
    ) == (1, 1)


def test_positive_variation_keeps_unique_candidate_across_feed_items():
    candidate = _candidate()
    kept = qualify_across_feed_variants(
        [candidate],
        [_xml("feed_anchor", "video_a"), _xml("feed_anchor", "video_b"), _xml("feed_anchor", "video_c")],
        package="com.zhiliaoapp.musically",
    )
    assert len(kept) == 1
    assert kept[0].occurrences == (1, 1, 1)


def test_positive_variation_rejects_candidate_missing_from_one_feed_item():
    candidate = _candidate()
    kept = qualify_across_feed_variants(
        [candidate],
        [_xml("feed_anchor"), _xml("other")],
        package="com.zhiliaoapp.musically",
    )
    assert kept == []


def test_positive_variation_rejects_ambiguous_duplicate():
    candidate = _candidate()
    kept = qualify_across_feed_variants(
        [candidate],
        [_xml("feed_anchor"), _xml("feed_anchor", "feed_anchor")],
        package="com.zhiliaoapp.musically",
    )
    assert kept == []


def test_unique_presence_ratio_reports_current_feed_overlap():
    candidates = [_candidate("one"), _candidate("two")]
    ratio = unique_presence_ratio(
        candidates,
        _xml("one", "two"),
        package="com.zhiliaoapp.musically",
    )
    assert ratio == 1.0


def test_positive_variation_requires_two_snapshots():
    with pytest.raises(FeedAnchorVariationError):
        qualify_across_feed_variants([_candidate()], [_xml("feed_anchor")])
