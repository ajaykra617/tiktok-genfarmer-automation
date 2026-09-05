#!/usr/bin/env python3
"""ADB preflight for the single-device Chrome qualification lane.

Default mode is read-only: confirms the target ADB device and lists installed
browser-like packages plus the resolved HTTP VIEW activity when Android exposes
one. ``--launch-url`` is an explicit opt-in smoke action that opens the supplied
URL on the authorized test device.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

KNOWN_BROWSER_PACKAGES = (
    "com.android.chrome",
    "org.chromium.chrome",
    "com.android.browser",
    "com.sec.android.app.sbrowser",
    "com.microsoft.emmx",
    "org.mozilla.firefox",
    "com.brave.browser",
    "com.kiwibrowser.browser",
)


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


def run(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", check=check)


def adb_path() -> str:
    return os.getenv("ADB_PATH") or "adb"


def main() -> int:
    ap = argparse.ArgumentParser(description="ADB preflight for the authorized Chrome qualification device")
    ap.add_argument("--device", help="ADB serial; defaults to DEFAULT_DEVICE_ADB from .env")
    ap.add_argument("--launch-url", help="Explicitly open this URL via Android VIEW intent")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    serial = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not serial:
        print("ERROR: provide --device or DEFAULT_DEVICE_ADB in .env", file=sys.stderr)
        return 2

    adb = adb_path()
    try:
        state = run([adb, "-s", serial, "get-state"])
    except FileNotFoundError:
        print("ERROR: adb not found; set ADB_PATH or add adb to PATH", file=sys.stderr)
        return 2
    if state.returncode != 0 or state.stdout.strip() != "device":
        print(f"ERROR: ADB target is not ready: {serial}", file=sys.stderr)
        if state.stderr.strip():
            print(state.stderr.strip(), file=sys.stderr)
        return 1

    packages = run([adb, "-s", serial, "shell", "pm", "list", "packages"])
    installed = set()
    for line in packages.stdout.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            installed.add(line.split(":", 1)[1].strip())

    browser_hits = [pkg for pkg in KNOWN_BROWSER_PACKAGES if pkg in installed]
    fuzzy = sorted(pkg for pkg in installed if any(token in pkg.lower() for token in ("chrome", "chromium", "browser", "firefox", "brave")))
    for pkg in fuzzy:
        if pkg not in browser_hits:
            browser_hits.append(pkg)

    resolve = run([
        adb, "-s", serial, "shell", "cmd", "package", "resolve-activity", "--brief",
        "-a", "android.intent.action.VIEW", "-d", "http://example.invalid/",
    ])
    resolved_activity = resolve.stdout.strip() or "<not-resolved>"

    print("=" * 78)
    print("CHROME / BROWSER DEVICE PREFLIGHT")
    print("=" * 78)
    print(f"ADB target: {serial}")
    print(f"State: {state.stdout.strip()}")
    print("Browser-like packages:")
    if browser_hits:
        for pkg in browser_hits:
            print(f" - {pkg}")
    else:
        print(" - none recognized")
    print(f"Resolved HTTP VIEW activity: {resolved_activity}")

    if args.launch_url:
        launched = run([
            adb, "-s", serial, "shell", "am", "start", "-W",
            "-a", "android.intent.action.VIEW", "-d", args.launch_url,
        ])
        print("Launch smoke: requested")
        print(f"Launch return code: {launched.returncode}")
        for line in launched.stdout.splitlines():
            if line.startswith(("Status:", "Activity:", "ThisTime:", "TotalTime:", "WaitTime:")):
                print(f" {line}")
        if launched.returncode != 0:
            if launched.stderr.strip():
                print(launched.stderr.strip(), file=sys.stderr)
            return 1
    else:
        print("Launch smoke: skipped (read-only mode)")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
