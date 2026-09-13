#!/usr/bin/env python3
"""Launch a saved authorized Boost preset through the Boost session controller."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Launch saved TikTok Boost preset")
    ap.add_argument("preset_file", type=Path)
    ap.add_argument("preset")
    ap.add_argument("--device", required=True)
    ap.add_argument("--media", type=Path, required=True)
    ap.add_argument("--caption", default="")
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--account-key")
    ap.add_argument("--ready", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    try:
        data = json.loads(args.preset_file.read_text(encoding="utf-8"))
        preset = data[args.preset]
        if not isinstance(preset, dict):
            raise TypeError("preset is not an object")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"ERROR: invalid preset: {exc}", file=sys.stderr)
        return 2

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "tiktok_boost_session.py"),
        "--device", args.device,
        "--media", str(args.media),
        "--caption", args.caption,
        "--candidates", str(args.candidates),
        "--candidate", str(preset.get("candidate", args.candidate)),
    ]
    if preset.get("explore_type") and preset.get("explore_value"):
        cmd.extend(["--explore-type", str(preset["explore_type"]), "--explore-value", str(preset["explore_value"])])
    if args.account_key:
        cmd.extend(["--account-key", args.account_key])
    if args.ready or preset.get("account_ready_required") is False:
        cmd.append("--ready")
    if args.publish and bool(preset.get("publish", True)):
        cmd.append("--publish")
    if args.apply:
        cmd.append("--apply")

    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
