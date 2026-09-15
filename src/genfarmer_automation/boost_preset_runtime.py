"""Runtime helpers for saved TikTok Boost Phase A presets.

Warm-scroll preset execution deliberately uses the qualified standalone
`tiktok_boost_warm_scroll.py` controller.  This keeps Boost Phase A independent
from a compiled `.genfarm` export while preserving deterministic seed/evidence
behavior and the existing no-publish boundary.
"""
from __future__ import annotations

from pathlib import Path


def build_warm_scroll_command(
    *,
    python_executable: str,
    root: Path,
    candidates: Path,
    candidate: int,
    device: str,
    videos: int,
    seed: int,
    preferred_hierarchy_port: int,
    apply: bool,
) -> list[str]:
    if videos <= 0:
        raise ValueError("warm-scroll videos must be positive")
    if candidate <= 0:
        raise ValueError("candidate index must be positive")
    if not str(device).strip():
        raise ValueError("device must be non-empty")
    if not 1 <= int(preferred_hierarchy_port) <= 65535:
        raise ValueError("preferred hierarchy port must be 1..65535")

    cmd = [
        python_executable,
        str(root / "scripts" / "tiktok_boost_warm_scroll.py"),
        str(candidates),
        "--candidate", str(candidate),
        "--device", device,
        "--videos", str(videos),
        "--watch-min", "5",
        "--watch-max", "10",
        "--max-session-minutes", "8",
        "--seed", str(seed),
        "--preferred-hierarchy-port", str(preferred_hierarchy_port),
    ]
    if apply:
        cmd.append("--apply")
    return cmd


def expected_warm_scroll_status(*, apply: bool) -> str:
    return "PASS" if apply else "DRY_RUN_READY"
