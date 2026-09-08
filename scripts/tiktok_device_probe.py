#!/usr/bin/env python3
"""Read-only TikTok installation/activity probe for one Android device.

The probe discovers likely TikTok package variants, launcher activities, version
metadata and current foreground activity. It does not launch, stop, tap, type,
install, log in, or modify device/app state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_HINTS = ("tiktok", "musically", "ugc.trill", "ugc.aweme")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def adb(device: str, *args: str, timeout: int = 30) -> str:
    proc = subprocess.run(
        ["adb", "-s", device, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        raise RuntimeError(err or f"adb exited {proc.returncode}")
    return proc.stdout.decode(errors="replace").strip()


def package_metadata(device: str, package: str) -> dict[str, str | None]:
    dump = adb(device, "shell", "dumpsys", "package", package, timeout=30)
    version_name = None
    version_code = None
    for line in dump.splitlines():
        line = line.strip()
        if line.startswith("versionName=") and version_name is None:
            version_name = line.split("=", 1)[1].strip()
        if line.startswith("versionCode=") and version_code is None:
            version_code = line.split("=", 1)[1].split()[0].strip()
    return {"version_name": version_name, "version_code": version_code}


def resolve_launcher(device: str, package: str) -> str | None:
    proc = subprocess.run(
        [
            "adb", "-s", device, "shell", "cmd", "package", "resolve-activity",
            "--brief", "-a", "android.intent.action.MAIN", "-c",
            "android.intent.category.LAUNCHER", package,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )
    if proc.returncode != 0:
        return None
    text = proc.stdout.decode(errors="replace").strip()
    if not text or text.lower().startswith("no activity"):
        return None
    return text.splitlines()[-1].strip()


def current_focus(device: str) -> str | None:
    text = adb(device, "shell", "dumpsys", "window", "windows", timeout=20)
    for line in text.splitlines():
        stripped = line.strip()
        if "mCurrentFocus" in stripped:
            return stripped
    return None


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Read-only TikTok install/activity probe")
    ap.add_argument("--device", default=os.getenv("DEFAULT_DEVICE_ADB"))
    ap.add_argument("--json", action="store_true", help="print JSON only")
    args = ap.parse_args()
    if not args.device:
        print("ERROR: pass --device or configure DEFAULT_DEVICE_ADB", file=sys.stderr)
        return 2

    try:
        state = adb(args.device, "get-state")
        if state != "device":
            raise RuntimeError(f"ADB state is {state!r}, expected 'device'")

        package_lines = adb(args.device, "shell", "pm", "list", "packages")
        packages = sorted(
            line.split(":", 1)[1].strip()
            for line in package_lines.splitlines()
            if line.startswith("package:")
            and any(hint in line.lower() for hint in PACKAGE_HINTS)
        )

        candidates = []
        for package in packages:
            item: dict[str, object] = {"package": package}
            item.update(package_metadata(args.device, package))
            item["launcher_activity"] = resolve_launcher(args.device, package)
            candidates.append(item)

        focus = current_focus(args.device)
        result = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "device": args.device,
            "adb_state": state,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "current_focus": focus,
            "read_only": True,
        }

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        print("=" * 78)
        print("TIKTOK DEVICE QUALIFICATION PROBE")
        print("=" * 78)
        print(f"ADB target: {args.device}")
        print(f"State: {state}")
        print(f"TikTok-like packages found: {len(candidates)}")
        for item in candidates:
            print(f" - package: {item['package']}")
            print(f"   version: {item.get('version_name')} ({item.get('version_code')})")
            print(f"   launcher: {item.get('launcher_activity') or 'unresolved'}")
        print(f"Current focus: {focus or 'unknown'}")
        print("Read-only: no app/device state was changed.")
        print("=" * 78)
        if not candidates:
            print("ERROR: no likely TikTok package was discovered", file=sys.stderr)
            return 1
        return 0
    except FileNotFoundError:
        print("ERROR: adb not found in PATH", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
