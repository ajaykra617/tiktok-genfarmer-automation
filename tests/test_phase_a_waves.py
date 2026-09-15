from pathlib import Path

import pytest

from genfarmer_automation.phase_a_waves import (
    PhaseAWaveError,
    build_task_command,
    load_phase_a_runtime,
    validate_runtime_for_plan,
)
from genfarmer_automation.schedule_policy import load_schedule_plan


def _runtime_payload():
    return {
        "devices": {
            "GF#7": {
                "adb_id": "device-7:5555",
                "media_dirs": ["approved-media/gf7"],
                "account_key": "acct-7",
            }
        },
        "proxies": {"proxy-1": {"http_url": "http://proxy.local:4001"}},
        "defaults": {
            "preset_config": "config/tiktok-boost-presets.example.json",
            "reservations": "evidence/leases.private",
            "history": "evidence/history.private.json",
            "preferred_hierarchy_port": 8912,
        },
    }


def _plan(device="GF#7", proxy="proxy-1", app="tiktok", mode="boost_prepare"):
    return load_schedule_plan(
        {
            "interval_minutes": [0, 0],
            "waves": [
                {
                    "name": "w1",
                    "tasks": [
                        {
                            "device": device,
                            "app": app,
                            "mode": mode,
                            "proxy_id": proxy,
                            "preset": "phase_a_standard",
                        }
                    ],
                }
            ],
        }
    )


def test_runtime_resolves_relative_media_paths(tmp_path):
    runtime = load_phase_a_runtime(_runtime_payload(), root=tmp_path)
    assert runtime.devices["GF#7"].media_dirs == (tmp_path / "approved-media/gf7",)
    assert runtime.defaults.preset_config == tmp_path / "config/tiktok-boost-presets.example.json"


def test_validate_runtime_accepts_phase_a_plan(tmp_path):
    runtime = load_phase_a_runtime(_runtime_payload(), root=tmp_path)
    validate_runtime_for_plan(_plan(), runtime)


def test_validate_runtime_rejects_unknown_device(tmp_path):
    runtime = load_phase_a_runtime(_runtime_payload(), root=tmp_path)
    with pytest.raises(PhaseAWaveError, match="missing from runtime"):
        validate_runtime_for_plan(_plan(device="GF#8"), runtime)


def test_validate_runtime_rejects_non_tiktok_app(tmp_path):
    runtime = load_phase_a_runtime(_runtime_payload(), root=tmp_path)
    with pytest.raises(PhaseAWaveError, match="only supports"):
        validate_runtime_for_plan(_plan(app="reddit"), runtime)


def test_build_task_command_maps_private_runtime_values(tmp_path):
    runtime = load_phase_a_runtime(_runtime_payload(), root=tmp_path)
    task = _plan().waves[0].tasks[0]
    cmd = build_task_command(
        task,
        runtime,
        python_executable="python",
        root=tmp_path,
        seed=42,
        apply=True,
    )
    joined = " ".join(str(part) for part in cmd)
    assert "tiktok_boost_prepare_preset.py" in joined
    assert "--device device-7:5555" in joined
    assert "--proxy-id proxy-1" in joined
    assert "--proxy-host proxy.local" in joined
    assert "--proxy-port 4001" in joined
    assert "--media-dir" in cmd
    assert "--ready" in cmd
    assert "--apply" in cmd
