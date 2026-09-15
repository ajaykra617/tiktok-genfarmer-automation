import pytest

from genfarmer_automation.boost_sources import (
    BoostSourceError,
    choose_source,
    load_preset,
    load_source_pool,
    normalize_source,
    preset_summary,
)


def test_source_normalization_strips_hash_and_at_prefixes():
    assert normalize_source("hashtag", "#technology").value == "technology"
    assert normalize_source("account", "@example").value == "example"


def test_link_requires_http_or_https():
    with pytest.raises(BoostSourceError, match="http"):
        normalize_source("link", "tiktok.com/example")


def test_source_pool_deduplicates_normalized_entries():
    sources = load_source_pool(
        [
            {"type": "hashtag", "value": "#Technology"},
            {"type": "hashtag", "value": "technology"},
            {"type": "keyword", "value": "technology"},
        ]
    )
    assert len(sources) == 2
    assert [item.source_type for item in sources] == ["hashtag", "keyword"]


def test_seeded_random_selection_is_reproducible():
    sources = load_source_pool(
        [
            {"type": "keyword", "value": "one"},
            {"type": "keyword", "value": "two"},
            {"type": "keyword", "value": "three"},
        ]
    )
    first, index1 = choose_source(sources, selection="random", seed=42)
    second, index2 = choose_source(sources, selection="random", seed=42)
    assert first == second
    assert index1 == index2


def test_empty_pool_returns_no_source():
    source, index = choose_source((), selection="random", seed=1)
    assert source is None
    assert index is None


def test_load_preset_and_summary():
    preset = load_preset(
        {
            "presets": {
                "standard": {
                    "warm_scroll_videos": 3,
                    "lease_minutes": 90,
                    "explore": {
                        "selection": "random",
                        "sources": [
                            {"type": "keyword", "value": "technology"},
                            {"type": "hashtag", "value": "#technology"},
                        ],
                    },
                }
            }
        },
        "standard",
    )
    summary = preset_summary(preset)
    assert summary["warm_scroll_videos"] == 3
    assert summary["explore_sources"] == 2
    assert summary["publishing_deferred"] is True


def test_invalid_preset_bounds_fail_closed():
    with pytest.raises(BoostSourceError, match="warm_scroll_videos"):
        load_preset({"presets": {"bad": {"warm_scroll_videos": 21}}}, "bad")
