#!/usr/bin/env python3
"""Launch a saved warm-up preset through the full session controller."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Launch saved TikTok warm-up preset")
    ap.add_argument("preset_file", type=Path)
    ap.add_argument("preset")
    ap.add_argument("compiled", type=Path)
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--device", required=True)
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--strict-selector", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    try:
        data = json.loads(args.preset_file.read_text(encoding="utf-8"))
        preset = data[args.preset]
        if not isinstance(preset, dict):
            raise TypeError("preset is not an object")
        required = (
            "videos",
            "watch_min_seconds",
            "watch_max_seconds",
            "max_session_minutes",
            "step_retries",
            "failure_budget",
        )
        missing = [key for key in required if key not in preset]
        if missing:
            raise ValueError(f"preset missing keys: {', '.join(missing)}")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"ERROR: invalid preset: {exc}", file=sys.stderr)
        return 2

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "tiktok_warmup_session.py"),
        str(args.compiled),
        str(args.candidates),
        "--candidate", str(args.candidate),
        "--device", args.device,
        "--videos", str(preset["videos"]),
        "--watch-min", str(preset["watch_min_seconds"]),
        "--watch-max", str(preset["watch_max_seconds"]),
        "--max-session-minutes", str(preset["max_session_minutes"]),
        "--step-retries", str(preset["step_retries"]),
        "--failure-budget", str(preset["failure_budget"]),
    ]
    if args.seed is not None:
        cmd.extend(["--seed", str(args.seed)])
    if args.strict_selector:
        cmd.append("--strict-selector")
    if args.apply:
        cmd.append("--apply")

    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
