import pytest

from genfarmer_automation.feed_anchor_qualification import candidates_from_payload
from genfarmer_automation.selector_gate import assess_selector_gate


def candidate():
    return candidates_from_payload([
        {
            "kind": "resource-id",
            "xpath": "//android.view.View[@resource-id='feed_anchor']",
            "class_name": "android.view.View",
            "occurrences": [1, 1, 1],
            "present_in_all": True,
            "unique_in_all": True,
            "score": 125,
        }
    ])[0]


def xml(*ids):
    nodes = "".join(
        f'<node package="com.zhiliaoapp.musically" class="android.view.View" resource-id="{value}" />'
        for value in ids
    )
    return f'<hierarchy rotation="0">{nodes}</hierarchy>'


def test_selector_gate_passes_only_exactly_once_in_every_snapshot():
    report = assess_selector_gate(
        candidate(),
        [xml("feed_anchor"), xml("feed_anchor")],
        package="com.zhiliaoapp.musically",
    )
    assert report.passed is True
    assert report.counts == (1, 1)


def test_selector_gate_rejects_missing_or_duplicate_selector():
    report = assess_selector_gate(
        candidate(),
        [xml("feed_anchor"), xml("feed_anchor", "feed_anchor")],
        package="com.zhiliaoapp.musically",
    )
    assert report.passed is False
    assert report.counts == (1, 2)


def test_selector_gate_requires_repeated_fresh_samples():
    with pytest.raises(ValueError):
        assess_selector_gate(candidate(), [xml("feed_anchor")])
