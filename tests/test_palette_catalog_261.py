from genfarmer_automation.palette_catalog_261 import (
    PALETTE_261,
    RESOLVED_ACTIONS_261,
    SPECIAL_LIVE_NODES_261,
    UNRESOLVED_PALETTE_261,
    by_action,
    by_label,
)


def test_palette_row_count_and_unresolved_count():
    assert len(PALETTE_261) == 60
    assert len(RESOLVED_ACTIONS_261) == 60
    assert len(UNRESOLVED_PALETTE_261) == 0


def test_labels_and_constants_are_unique():
    assert len({item.label for item in PALETTE_261}) == len(PALETTE_261)
    assert len({item.constant for item in PALETTE_261}) == len(PALETTE_261)


def test_resolved_actions_are_unique():
    actions = [item.action for item in PALETTE_261 if item.action]
    assert len(actions) == len(set(actions))


def test_known_live_anchors_and_special_nodes():
    assert by_label("ADB shell command").action == "Adb"
    assert by_label("Sleep").action == "Pause"
    assert by_label("Screenshot").action == "Screenshot"
    assert by_label("HTTP").action == "HTTP"
    assert by_label("Log").action == "Log"
    assert by_label("Random").action == "Random"
    assert by_label("Stop").action == "Stop"
    for label in ("HTTP", "Log", "Random", "Stop"):
        assert by_label(label).provenance == "live-flow-anchor"
    assert by_action("TypeText").label == "Type text"
    assert SPECIAL_LIVE_NODES_261 == ("Start", "Variables", "ContextMenu")


def test_no_palette_rows_remain_unresolved():
    assert UNRESOLVED_PALETTE_261 == ()
