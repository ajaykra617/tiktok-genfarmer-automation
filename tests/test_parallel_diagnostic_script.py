import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "tiktok_parallel_diagnostic.py"


def load_script():
    spec = importlib.util.spec_from_file_location("parallel_diagnostic_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_device_requires_name_and_serial():
    module = load_script()
    assert module._parse_device("GF1=192.168.4.138:5555") == ("GF1", "192.168.4.138:5555")
    with pytest.raises(Exception):
        module._parse_device("192.168.4.138:5555")


def test_parallel_launcher_worker_command_remains_pre_publish_and_non_reboot():
    module = load_script()
    args = SimpleNamespace(
        candidates=Path("candidates.json"),
        candidate=8,
        proxy_id="proxy-1",
        media=Path("media.mp4"),
        keyword="technology",
        hashtag="technology",
        videos=3,
        watch_min=4.0,
        watch_max=7.0,
        dwell=3.0,
        seed=43,
        max_app_restarts=3,
        max_cycles=2,
        preferred_hierarchy_port=8912,
    )
    cmd = module._worker_command(args, "device:5555")
    joined = " ".join(cmd).casefold()
    assert "tiktok_persistent_device_worker.py" in cmd[1]
    assert "--publish" not in cmd
    assert "reboot" not in joined
