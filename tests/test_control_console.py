from pathlib import Path

import pytest

from genfarmer_automation.control_console import (
    build_boost_command,
    build_warmup_command,
    parse_adb_devices,
)


def test_parse_adb_devices_long_listing():
    rows = parse_adb_devices(
        "List of devices attached\n"
        "10.0.0.1:5555 device product:foo model:Pixel_4_XL transport_id:7\n"
        "10.0.0.2:5555 offline product:bar model:Other transport_id:8\n"
    )
    assert [row.serial for row in rows] == ["10.0.0.1:5555", "10.0.0.2:5555"]
    assert rows[0].state == "device"
    assert rows[0].model == "Pixel_4_XL"
    assert rows[1].state == "offline"


def test_build_warmup_command_is_argument_list():
    cmd = build_warmup_command(
        python_exe="python",
        root=Path("C:/repo"),
        preset_file=Path("C:/repo/config/presets.json"),
        preset="standard",
        compiled=Path("C:/Downloads/Browse One.genfarm"),
        candidates=Path("C:/repo/evidence/private/candidates.json"),
        candidate=8,
        device="device:5555",
        apply=True,
    )
    assert cmd[0] == "python"
    assert "standard" in cmd
    assert cmd[-1] == "--apply"
    assert "C:/Downloads/Browse One.genfarm" in cmd


def test_build_boost_requires_paired_explore_fields():
    with pytest.raises(ValueError):
        build_boost_command(
            python_exe="python",
            root=Path("."),
            device="dev",
            media=Path("x.mp4"),
            candidates=Path("c.json"),
            candidate=8,
            explore_type="keyword",
            explore_value=None,
        )


def test_build_boost_ready_without_publish():
    cmd = build_boost_command(
        python_exe="python",
        root=Path("."),
        device="dev",
        media=Path("x.mp4"),
        candidates=Path("c.json"),
        candidate=8,
        explore_type="keyword",
        explore_value="technology",
        ready=True,
        publish=False,
        apply=True,
    )
    assert "--ready" in cmd
    assert "--publish" not in cmd
    assert "--apply" in cmd
