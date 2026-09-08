#!/usr/bin/env python3
"""Measure how visually stable the current TikTok screen is over a short window.

This is a read-only diagnostic. It does not swipe, tap, dismiss dialogs, or claim
that a feed transition succeeded. The goal is to learn whether screenshot-based
postcondition evidence is viable on the current device while TikTok video
content is animating.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_observer import AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.screen_state import (  # noqa: E402
    ScreenStateError,
    measure_temporal_stability,
    parse_android_raw_screencap,
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


def adb_raw_screencap(device: str, timeout: float = 15.0) -> bytes:
    try:
        proc = subprocess.run(
            ["adb", "-s", device, "exec-out", "screencap"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("adb was not found in PATH") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        raise RuntimeError(err or f"adb exited {proc.returncode}")
    return proc.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only TikTok feed visual stability probe")
    ap.add_argument("--device")
    ap.add_argument("--frames", type=int, default=4)
    ap.add_argument("--interval", type=float, default=0.35)
    ap.add_argument("--threshold", type=int, default=16)
    args = ap.parse_args()

    if args.frames < 2:
        ap.error("--frames must be >= 2")
    if args.interval < 0:
        ap.error("--interval must be >= 0")

    load_dotenv(ROOT / ".env")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not device:
        print("ERROR: pass --device or configure DEFAULT_DEVICE_ADB", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in device)
    out = ROOT / "evidence" / f"tiktok-feed-stability-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)

    result: dict[str, object] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "device": device,
        "read_only": True,
        "frames": args.frames,
        "interval_seconds": args.interval,
        "threshold": args.threshold,
        "status": "failed",
    }

    try:
        observer = AdbObserver(device)
        observation = observer.observe()
        result["observation"] = observation.to_dict()

        print("=" * 78)
        print("TIKTOK FEED VISUAL STABILITY PROBE")
        print("=" * 78)
        print(f"ADB state:           {observation.adb_state}")
        print(f"TikTok foreground:   {'YES' if observation.tiktok_foreground else 'NO'}")
        print(f"Interrupt:            {observation.interrupt.value}")

        if observation.adb_state != "device":
            raise RuntimeError("ADB device is not ready")
        if observation.interrupt is not InterruptKind.NONE:
            raise RuntimeError(f"known interrupt is foreground: {observation.interrupt.value}")
        if not observation.tiktok_foreground:
            raise RuntimeError("TikTok is not foreground; run tiktok_ensure_foreground.py --apply first")

        # Preserve one ordinary screenshot locally for human review, but never
        # expose it in the shareable JSON.
        observer.capture_screenshot(private / "screen.png")

        frames = []
        for index in range(args.frames):
            raw = adb_raw_screencap(device)
            frames.append(parse_android_raw_screencap(raw))
            if index + 1 < args.frames and args.interval:
                time.sleep(args.interval)

        report = measure_temporal_stability(
            frames,
            per_point_range_threshold=args.threshold,
        )
        result.update(
            {
                "status": "ok",
                "screen_width": frames[0].width,
                "screen_height": frames[0].height,
                "sample_points": report.total_points,
                "stable_points": report.stable_points,
                "stable_ratio": round(report.stable_ratio, 6),
            }
        )

        shareable = out / "tiktok-feed-stability.shareable.json"
        shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print(f"Screen:              {frames[0].width}x{frames[0].height}")
        print(f"Sample points:       {report.total_points}")
        print(f"Stable points:       {report.stable_points}")
        print(f"Stable ratio:        {report.stable_ratio:.1%}")
        print("Interpretation: this is diagnostic only; it does NOT prove a feed transition.")
        if report.stable_ratio >= 0.25:
            print("Signal: enough temporally-stable screen area exists to test a conservative before/after visual postcondition.")
        else:
            print("Signal: animated content dominates; selector/accessibility evidence should remain the primary postcondition path.")
        print(f"Private evidence:    {private.relative_to(ROOT)}")
        print(f"Shareable result:    {shareable.relative_to(ROOT)}")
        print("Read-only: no device or GenFarmer state was changed.")
        print("=" * 78)
        return 0
    except (RuntimeError, ScreenStateError, OSError, ValueError) as exc:
        result["error"] = str(exc)
        shareable = out / "tiktok-feed-stability.shareable.json"
        shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
