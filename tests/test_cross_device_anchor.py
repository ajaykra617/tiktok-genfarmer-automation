from genfarmer_automation.cross_device_anchor import (
    evaluate_cross_device_candidates,
    survivor_ranks,
)
from genfarmer_automation.feed_anchor_qualification import candidates_from_payload


def _candidate(value: str):
    return candidates_from_payload([
        {
            "kind": "resource-id",
            "xpath": f"//android.view.View[@resource-id='{value}']",
            "class_name": "android.view.View",
            "occurrences": [1, 1, 1],
            "present_in_all": True,
            "unique_in_all": True,
            "score": 125,
        }
    ])[0]


def _xml(*values: str) -> str:
    nodes = "".join(
        f'<node package="com.zhiliaoapp.musically" class="android.view.View" resource-id="{value}" />'
        for value in values
    )
    return f'<hierarchy rotation="0">{nodes}</hierarchy>'


def test_sweep_preserves_source_rank_and_finds_cross_device_survivor():
    candidates = [_candidate("missing"), _candidate("stable"), _candidate("duplicate")]
    snapshots = [
        _xml("stable", "duplicate", "duplicate"),
        _xml("stable", "duplicate", "duplicate"),
        _xml("stable", "duplicate", "duplicate"),
    ]
    results = evaluate_cross_device_candidates(
        candidates,
        snapshots,
        package="com.zhiliaoapp.musically",
    )
    assert [item.source_rank for item in results] == [1, 2, 3]
    assert results[0].counts == (0, 0, 0)
    assert results[1].counts == (1, 1, 1)
    assert results[1].passed is True
    assert results[2].counts == (2, 2, 2)
    assert survivor_ranks(results) == (2,)


def test_sweep_requires_multiple_snapshots():
    try:
        evaluate_cross_device_candidates([_candidate("stable")], [_xml("stable")])
    except ValueError as exc:
        assert "at least two" in str(exc)
    else:
        raise AssertionError("single target snapshot should fail closed")
