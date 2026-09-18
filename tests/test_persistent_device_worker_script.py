import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "tiktok_persistent_device_worker.py"


def load_script():
    spec = importlib.util.spec_from_file_location("tiktok_persistent_device_worker_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_persistent_worker_wraps_only_pre_publish_demo():
    module = load_script()
    args = SimpleNamespace(
        candidates=Path("candidates.json"),
        candidate=8,
        device="device:5555",
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
        preferred_hierarchy_port=8912,
    )

    cmd = module._client_command(args)

    assert "tiktok_client_demo_production.py" in cmd[1]
    assert "--apply" in cmd
    assert "--publish" not in cmd
    assert "reboot" not in " ".join(cmd).casefold()


def test_last_error_prefers_explicit_error_line():
    module = load_script()
    assert module._last_error("hello\nERROR: hierarchy unavailable\nShareable result: x") == "hierarchy unavailable"
