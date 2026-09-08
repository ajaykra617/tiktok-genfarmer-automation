#!/usr/bin/env python3
"""Plan or perform one bounded TikTok foreground recovery.

Dry-run by default. With --apply, the script may only relaunch the already
qualified TikTok component. It never taps UI, dismisses prompts, installs apps,
or guesses through interrupts. Success requires a fresh post-launch observation
proving TikTok is actually foreground.
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

from genfarmer_automation.adb_observer import AdbObserver  # noqa: E402
from genfarmer_automation.tiktok_runtime import (  # noqa: E402
    ForegroundDecision,
    TikTokRuntime,
    plan_foreground,
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
    ap = argparse.ArgumentParser(description="Dry-run or perform bounded TikTok foreground recovery")
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB from .env")
    ap.add_argument("--apply", action="store_true", help="allow one explicit TikTok relaunch if needed")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not device:
        print("ERROR: pass --device or configure DEFAULT_DEVICE_ADB in .env", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
    out = ROOT / "evidence" / f"tiktok-ensure-foreground-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)

    observer = AdbObserver(device)
    before = observer.observe()
    observer.capture_screenshot(private / "before.png")
    plan = plan_foreground(before)

    success = plan.decision is ForegroundDecision.READY
    attempts = 0
    after = before
    reason = plan.reason

    if args.apply and plan.decision is ForegroundDecision.NEEDS_LAUNCH:
        result = TikTokRuntime(device, observer=observer).ensure_foreground()
        success = result.success
        attempts = result.attempts
        after = result.final
        reason = result.reason
        observer.capture_screenshot(private / "after.png")

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "decision": plan.decision.value,
        "success": success,
        "attempts": attempts,
        "before": before.to_dict(),
        "after": after.to_dict(),
        "reason": reason,
    }
    (private / "result.private.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    shareable = {
        "timestamp_utc": report["timestamp_utc"],
        "mode": report["mode"],
        "decision": report["decision"],
        "success": success,
        "attempts": attempts,
        "before_tiktok_foreground": before.tiktok_foreground,
        "after_tiktok_foreground": after.tiktok_foreground,
        "before_interrupt": before.interrupt.value,
        "after_interrupt": after.interrupt.value,
        "reason": reason,
    }
    shareable_path = out / "tiktok-ensure-foreground.shareable.json"
    shareable_path.write_text(json.dumps(shareable, indent=2), encoding="utf-8")

    print("=" * 78)
    print("TIKTOK ENSURE FOREGROUND")
    print("=" * 78)
    print(f"Initial decision:  {plan.decision.value}")
    print(f"Initial foreground: {'YES' if before.tiktok_foreground else 'NO'}")
    print(f"Initial interrupt:  {before.interrupt.value}")
    print(f"Mode:               {'APPLY' if args.apply else 'DRY-RUN'}")
    if args.apply:
        print(f"Launch attempts:    {attempts}")
        print(f"Final foreground:   {'YES' if after.tiktok_foreground else 'NO'}")
        print(f"Final interrupt:    {after.interrupt.value}")
        print(f"Result:             {'PASS' if success else 'FAIL'}")
    else:
        if plan.decision is ForegroundDecision.NEEDS_LAUNCH:
            print("Plan: one explicit relaunch of the qualified TikTok component; rerun with --apply to execute.")
        elif plan.decision is ForegroundDecision.BLOCKED_INTERRUPT:
            print("Plan: STOP. Known interrupt is foreground; no blind recovery is allowed.")
        elif plan.decision is ForegroundDecision.DEVICE_UNAVAILABLE:
            print("Plan: STOP. ADB/device state must recover first.")
        else:
            print("Plan: no recovery needed; TikTok foreground is already proven.")
    print(f"Reason:             {reason}")
    print(f"Private evidence:   {private.relative_to(ROOT)}")
    print(f"Shareable result:   {shareable_path.relative_to(ROOT)}")
    print("=" * 78)
    return 0 if (success or not args.apply) else 1


if __name__ == "__main__":
    raise SystemExit(main())
