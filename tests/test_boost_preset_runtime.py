from pathlib import Path

import pytest

from genfarmer_automation.boost_preset_runtime import (
    build_warm_scroll_command,
    expected_warm_scroll_status,
)


def test_build_warm_scroll_command_uses_candidates_without_genfarm():
    cmd = build_warm_scroll_command(
        python_executable="python",
        root=Path("/repo"),
        candidates=Path("evidence/candidates.json"),
        candidate=8,
        device="device-1",
        videos=3,
        seed=42,
        preferred_hierarchy_port=8912,
        apply=True,
    )
    joined = " ".join(cmd)
    assert "tiktok_boost_warm_scroll.py" in joined
    assert "evidence/candidates.json" in joined
    assert "--videos 3" in joined
    assert "--seed 42" in joined
    assert "--apply" in cmd
    assert ".genfarm" not in joined


def test_build_warm_scroll_command_dry_run_omits_apply():
    cmd = build_warm_scroll_command(
        python_executable="python",
        root=Path("/repo"),
        candidates=Path("candidates.json"),
        candidate=1,
        device="device-1",
        videos=1,
        seed=7,
        preferred_hierarchy_port=8912,
        apply=False,
    )
    assert "--apply" not in cmd
    assert expected_warm_scroll_status(apply=False) == "DRY_RUN_READY"
    assert expected_warm_scroll_status(apply=True) == "PASS"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"videos": 0},
        {"candidate": 0},
        {"device": ""},
        {"preferred_hierarchy_port": 70000},
    ],
)
def test_build_warm_scroll_command_rejects_invalid_inputs(kwargs):
    values = {
        "python_executable": "python",
        "root": Path("/repo"),
        "candidates": Path("candidates.json"),
        "candidate": 8,
        "device": "device-1",
        "videos": 3,
        "seed": 42,
        "preferred_hierarchy_port": 8912,
        "apply": True,
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        build_warm_scroll_command(**values)
