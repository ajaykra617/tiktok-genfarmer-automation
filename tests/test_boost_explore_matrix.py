import pytest

from genfarmer_automation.boost_explore_matrix import (
    BoostExploreMatrixError,
    child_passed,
    is_transient_hierarchy_failure,
    matrix_summary,
    normalize_sources,
)


def test_normalize_sources_preserves_order_and_deduplicates():
    sources = normalize_sources(
        [
            ("keyword", "technology"),
            ("hashtag", "technology"),
            ("keyword", "Technology"),
        ]
    )
    assert [(item.source_type, item.value) for item in sources] == [
        ("keyword", "technology"),
        ("hashtag", "technology"),
    ]


def test_normalize_sources_rejects_empty_matrix():
    with pytest.raises(BoostExploreMatrixError, match="at least one"):
        normalize_sources([])


def test_child_passed_requires_zero_returncode_and_pass_status():
    assert child_passed(0, {"status": "PASS"}) is True
    assert child_passed(1, {"status": "PASS"}) is False
    assert child_passed(0, {"status": "BLOCKED"}) is False
    assert child_passed(0, None) is False


def test_transient_hierarchy_failure_is_retryable():
    payload = {
        "status": "BLOCKED",
        "reason": "no healthy hierarchy source after helper-service recovery and compressed/standard uiautomator fallback",
    }
    assert is_transient_hierarchy_failure(payload) is True


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"status": "PASS"},
        {"status": "BLOCKED", "reason": "configured query was not proven"},
        {"status": "BLOCKED"},
    ],
)
def test_non_hierarchy_failures_are_not_retryable(payload):
    assert is_transient_hierarchy_failure(payload) is False


def test_matrix_summary_is_pass_only_when_every_requested_source_passes():
    passed = matrix_summary([{"passed": True}, {"passed": True}])
    assert passed["status"] == "PASS"
    assert passed["passed_sources"] == 2
    assert passed["blocked_sources"] == 0
    assert passed["engagement_actions"] == 0

    blocked = matrix_summary([{"passed": True}, {"passed": False}])
    assert blocked["status"] == "BLOCKED"
    assert blocked["passed_sources"] == 1
    assert blocked["blocked_sources"] == 1
