#!/usr/bin/env python3
"""Inventory Android devices currently visible to ADB.

No client-specific device addresses are stored in the repository. The script
reads the live ADB server and prints a sanitized device inventory at runtime.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass


@dataclass
class DeviceInfo:
    adb_id: str
    state: str
    manufacturer: str = ""
    model: str = ""
    android: str = ""
    sdk: str = ""


def run_adb(*args: str, timeout: int = 15) -> str:
    proc = subprocess.run(
        ["adb", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"adb exited {proc.returncode}")
    return proc.stdout.strip()


def get_prop(device: str, name: str) -> str:
    try:
        return run_adb("-s", device, "shell", "getprop", name).strip()
    except Exception:
        return ""


def discover() -> list[DeviceInfo]:
    output = run_adb("devices")
    devices: list[DeviceInfo] = []

    for raw in output.splitlines()[1:]:
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split()
        if len(parts) < 2:
            continue

        adb_id, state = parts[0], parts[1]
        info = DeviceInfo(adb_id=adb_id, state=state)

        if state == "device":
            info.manufacturer = get_prop(adb_id, "ro.product.manufacturer")
            info.model = get_prop(adb_id, "ro.product.model")
            info.android = get_prop(adb_id, "ro.build.version.release")
            info.sdk = get_prop(adb_id, "ro.build.version.sdk")

        devices.append(info)

    return devices


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory devices visible to ADB")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    try:
        devices = discover()
    except FileNotFoundError:
        print("ERROR: adb was not found in PATH", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([asdict(d) for d in devices], indent=2))
        return 0

    print(f"ADB devices discovered: {len(devices)}")
    print("-" * 90)
    for i, d in enumerate(devices, start=1):
        details = " ".join(x for x in [d.manufacturer, d.model] if x).strip()
        version = f"Android {d.android} / SDK {d.sdk}" if d.android else ""
        print(f"{i:02d}. {d.adb_id:<24} {d.state:<12} {details} {version}".rstrip())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
