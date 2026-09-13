import pytest

from genfarmer_automation.live_feed_anchor import (
    LiveFeedAnchorError,
    patch_script_by_sentinel,
    sentinel_locations,
    unique_sentinel_location,
)


SENTINEL = "//*[@resource-id='__GF_SCHEMA_PROBE__']"
REAL = "//android.view.View[@resource-id='feed_anchor']"


def app_with_value(value=SENTINEL):
    return {
        "id": "app-1",
        "name": "old",
        "script": {
            "flow": {
                "nodes": [
                    {"id": "a", "data": {"action": "Start", "options": {}}},
                    {
                        "id": "b",
                        "data": {
                            "action": "ElementExists",
                            "options": {"xpath": value, "nodeTimeout": "30"},
                        },
                    },
                    {"id": "c", "data": {"action": "Stop", "options": {}}},
                ],
                "edges": [],
            }
        },
    }


def test_finds_sentinel_only_inside_elementexists_data():
    app = app_with_value()
    app["description"] = SENTINEL
    assert sentinel_locations(app, SENTINEL) == [(1, ("options", "xpath"))]


def test_unique_sentinel_location_fails_closed_when_missing():
    with pytest.raises(LiveFeedAnchorError):
        unique_sentinel_location(app_with_value("other"), SENTINEL)


def test_patch_script_replaces_existing_sentinel_path_only():
    app = app_with_value()
    script, path = patch_script_by_sentinel(app, sentinel=SENTINEL, replacement=REAL)
    assert path == ("options", "xpath")
    assert script["flow"]["nodes"][1]["data"]["options"]["xpath"] == REAL
    assert app["script"]["flow"]["nodes"][1]["data"]["options"]["xpath"] == SENTINEL


def test_ambiguous_sentinel_is_rejected():
    app = app_with_value()
    app["script"]["flow"]["nodes"][1]["data"]["shadow"] = SENTINEL
    with pytest.raises(LiveFeedAnchorError):
        patch_script_by_sentinel(app, sentinel=SENTINEL, replacement=REAL)
