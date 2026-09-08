#!/usr/bin/env python3
"""Read-only coarse readiness/interrupt probe for the TikTok device.

This is the first outer-supervisor sensor. It does not tap, dismiss dialogs,
launch apps, or change permissions. It only checks ADB state/foreground window
and optionally captures a screenshot into ignored local evidence.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_observer import (  # noqa: E402
    AdbObservationError,
    AdbObserver,
    InterruptKind,
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only TikTok resilience state probe")
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB from .env")
    ap.add_argument("--no-screenshot", action="store_true")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not device:
        print("ERROR: pass --device or configure DEFAULT_DEVICE_ADB", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
    out = ROOT / "evidence" / f"tiktok-resilience-probe-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)

    try:
        observer = AdbObserver(device)
        observation = observer.observe()
        if not args.no_screenshot:
            observer.capture_screenshot(private / "screen.png")

        if observation.interrupt is not InterruptKind.NONE:
            status = "BLOCKED_INTERRUPT"
            exit_code = 3
        elif observation.tiktok_foreground:
            status = "READY_COARSE"
            exit_code = 0
        else:
            status = "NOT_READY_FOREGROUND"
            exit_code = 4

        result = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "observation": observation.to_dict(),
            "read_only": True,
        }
        (private / "observation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        shareable = out / "tiktok-resilience-probe.shareable.json"
        shareable.write_text(
            json.dumps(
                {
                    "timestamp_utc": result["timestamp_utc"],
                    "status": status,
                    "adb_state": observation.adb_state,
                    "tiktok_foreground": observation.tiktok_foreground,
                    "interrupt": observation.interrupt.value,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        print("=" * 78)
        print("TIKTOK RESILIENCE PROBE")
        print("=" * 78)
        print(f"Status:              {status}")
        print(f"ADB state:           {observation.adb_state}")
        print(f"Foreground package:  {observation.foreground_package or '<unknown>'}")
        print(f"Foreground activity: {observation.foreground_activity or '<unknown>'}")
        print(f"TikTok foreground:   {'YES' if observation.tiktok_foreground else 'NO'}")
        print(f"Interrupt:            {observation.interrupt.value}")
        if observation.interrupt is InterruptKind.ANDROID_PERMISSION_DIALOG:
            print("Decision: stop before app actions; learn/use a verified permission-dialog selector handler.")
        elif observation.interrupt is not InterruptKind.NONE:
            print("Decision: stop before app actions; no blind tap/recovery is allowed for this state.")
        elif observation.tiktok_foreground:
            print("Decision: coarse readiness passed; selector-level feed precondition is still required before browse_one.")
        else:
            print("Decision: TikTok is not foreground; supervisor should recover/launch from a known checkpoint.")
        print(f"Private evidence:    {private.relative_to(ROOT)}")
        print(f"Shareable result:    {shareable.relative_to(ROOT)}")
        print("Read-only: no device or GenFarmer state was changed.")
        print("=" * 78)
        return exit_code
    except (AdbObservationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
