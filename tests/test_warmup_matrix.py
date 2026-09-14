from genfarmer_automation.warmup_matrix import build_matrix


def test_default_matrix_returns_to_for_you_before_context_features():
    rows = build_matrix()
    assert [row.feature for row in rows] == ["following", "for-you", "comments", "profile"]


def test_matrix_adds_explicit_niche_sources():
    rows = build_matrix(keyword="technology", hashtag="#android")
    assert [(row.feature, row.value) for row in rows[-2:]] == [
        ("keyword", "technology"),
        ("hashtag", "android"),
    ]
