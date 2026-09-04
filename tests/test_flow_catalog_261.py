from genfarmer_automation.flow_catalog_261 import (
    GENFARMER_VERSION,
    OBSERVED_EDGE_PATTERNS,
    VERIFIED_ACTIONS,
    get_action_spec,
    is_verified_action,
)


def test_verified_actions_match_first_semantic_catalog():
    assert GENFARMER_VERSION == "2.6.1"
    assert set(VERIFIED_ACTIONS) == {
        "custom-context-menu:ContextMenu",
        "custom:Adb",
        "custom:DeepSeek",
        "custom:Pause",
        "custom:Screenshot",
        "helper:Variables",
        "input:Start",
    }


def test_pause_spec_records_fixed_timeout_mode():
    pause = get_action_spec("custom:Pause")
    assert pause.observed_timeout_type == "fixed"
    assert pause.option_types["timeoutType"] == "str"


def test_verified_lookup():
    assert is_verified_action("custom", "Screenshot")
    assert not is_verified_action("custom", "Tap")


def test_edge_patterns_include_start_and_success_chain():
    assert len(OBSERVED_EDGE_PATTERNS) == 2
    assert OBSERVED_EDGE_PATTERNS[0]["target_handle"] == "successNode"
    assert OBSERVED_EDGE_PATTERNS[1]["source_handle"] == "successNode"
