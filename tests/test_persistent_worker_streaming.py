import importlib.util
from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "tiktok_persistent_device_worker.py"


def load_script():
    spec = importlib.util.spec_from_file_location("persistent_worker_stream_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_child_streamer_tees_output_to_memory_and_file(tmp_path):
    module = load_script()
    log = tmp_path / "child.log"
    returncode, output, timed_out = module._run_child_streamed(
        [sys.executable, "-c", "print(\'trace-line\')"],
        cwd=ROOT,
        timeout=10.0,
        env=os.environ.copy(),
        log_path=log,
    )
    assert returncode == 0
    assert timed_out is False
    assert "trace-line" in output
    assert "trace-line" in log.read_text(encoding="utf-8")
