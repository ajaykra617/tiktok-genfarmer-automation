from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace


def _load_script_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "tiktok_warmup_step.py"
    spec = spec_from_file_location("tiktok_warmup_step_script", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_best_effort_selector_captures_repeated_snapshots(monkeypatch):
    module = _load_script_module()
    seen = {}

    def fake_capture(device, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            snapshots=("<hierarchy />", "<hierarchy />"),
            provider="test-provider",
        )

    def fake_assess(candidate, snapshots, **kwargs):
        assert len(tuple(snapshots)) == 2
        return SimpleNamespace(passed=True, counts=(1, 1))

    monkeypatch.setattr(module, "capture_hierarchy_batch", fake_capture)
    monkeypatch.setattr(module, "assess_selector_gate", fake_assess)

    passed, provider, counts, error = module.best_effort_selector(
        "device-7", object(), preferred_port=8912
    )

    assert seen["count"] == 2
    assert passed is True
    assert provider == "test-provider"
    assert counts == (1, 1)
    assert error is None
