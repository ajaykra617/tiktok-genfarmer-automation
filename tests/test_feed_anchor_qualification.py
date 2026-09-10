import pytest

from genfarmer_automation.feed_anchor_qualification import (
    FeedAnchorQualificationError,
    candidate_from_dict,
    candidates_from_payload,
    qualify_against_negative_xml,
)


def _candidate(xpath="//android.view.View[@resource-id='feed_anchor']"):
    return {
        "kind": "resource-id",
        "xpath": xpath,
        "class_name": "android.view.View",
        "occurrences": [1, 1, 1],
        "present_in_all": True,
        "unique_in_all": True,
        "score": 125,
    }


def _xml(resource_id):
    return (
        '<hierarchy rotation="0">'
        f'<node package="com.zhiliaoapp.musically" class="android.view.View" resource-id="{resource_id}" />'
        '</hierarchy>'
    )


def test_candidate_from_dict_round_trip_shape():
    item = candidate_from_dict(_candidate())
    assert item.kind == "resource-id"
    assert item.occurrences == (1, 1, 1)
    assert item.unique_in_all is True


def test_candidates_payload_requires_list():
    with pytest.raises(FeedAnchorQualificationError):
        candidates_from_payload({"bad": True})


def test_negative_qualification_keeps_feed_only_candidate():
    candidates = candidates_from_payload([_candidate()])
    kept = qualify_against_negative_xml(
        candidates,
        [_xml("profile_only"), _xml("profile_only")],
        package="com.zhiliaoapp.musically",
    )
    assert len(kept) == 1


def test_negative_qualification_rejects_candidate_present_off_feed():
    candidates = candidates_from_payload([_candidate()])
    kept = qualify_against_negative_xml(
        candidates,
        [_xml("feed_anchor"), _xml("profile_only")],
        package="com.zhiliaoapp.musically",
    )
    assert kept == []


def test_negative_qualification_requires_two_snapshots():
    candidates = candidates_from_payload([_candidate()])
    with pytest.raises(FeedAnchorQualificationError):
        qualify_against_negative_xml(candidates, [_xml("profile_only")])
