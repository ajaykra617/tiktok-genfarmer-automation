#!/usr/bin/env python3
"""Persistent app-only self-healing wrapper for the passive TikTok client demo.

The wrapped demo stops at READY_FOR_PUBLISH and performs no final publish or
engagement action. A device may be retried indefinitely only when --persistent
is explicitly supplied. Every recovery cycle is bounded, reboot is never
attempted, and cooldowns prevent a bad phone from entering a hot restart loop.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.device_app_recovery import recover_tiktok_without_reboot  # noqa: E402
from genfarmer_automation.device_self_healing import (  # noqa: E402
    DeviceWorkerState,
    SelfHealingPolicy,
    retryable_client_failure,
)
from genfarmer_automation.warmup_session import load_shareable  # noqa: E402


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _last_error(output: str) -> str | None:
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("ERROR:"):
            return line[6:].strip()
    return lines[-1] if lines else None


def _client_command(args) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "tiktok_client_demo_production.py"),
        str(args.candidates),
        "--candidate", str(args.candidate),
        "--device", args.device,
        "--proxy-id", args.proxy_id,
        "--media", str(args.media),
        "--keyword", args.keyword,
        "--hashtag", args.hashtag,
        "--videos", str(args.videos),
        "--watch-min", str(args.watch_min),
        "--watch-max", str(args.watch_max),
        "--dwell", str(args.dwell),
        "--seed", str(args.seed),
        "--max-app-restarts", str(args.max_app_restarts),
        "--preferred-hierarchy-port", str(args.preferred_hierarchy_port),
        "--apply",
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Persistent non-reboot TikTok device self-healing worker")
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--device", required=True)
    ap.add_argument("--proxy-id", required=True)
    ap.add_argument("--media", type=Path, required=True)
    ap.add_argument("--keyword", default="technology")
    ap.add_argument("--hashtag", default="technology")
    ap.add_argument("--videos", type=int, default=3)
    ap.add_argument("--watch-min", type=float, default=4.0)
    ap.add_argument("--watch-max", type=float, default=7.0)
    ap.add_argument("--dwell", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=43)
    ap.add_argument("--max-app-restarts", type=int, default=3)
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--max-cycles", type=int, default=6, help="bounded attempts when --persistent is absent")
    ap.add_argument("--persistent", action="store_true", help="keep retrying with capped cooldown until success/Ctrl+C")
    ap.add_argument("--child-timeout", type=float, default=1200.0)
    args = ap.parse_args()

    if not 1 <= args.max_cycles <= 100:
        ap.error("--max-cycles must be 1..100")
    if not 60 <= args.child_timeout <= 3600:
        ap.error("--child-timeout must be 60..3600 seconds")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"persistent-device-worker-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "persistent-device-worker.shareable.json"
    policy = SelfHealingPolicy()

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "device_private": True,
        "persistent": bool(args.persistent),
        "reboot_enabled": False,
        "data_clear_enabled": False,
        "global_adb_restart_enabled": False,
        "publishing_ui_entered": False,
        "final_post_action": False,
        "engagement_actions": 0,
        "cycles": [],
    }

    cycle = 0
    consecutive_failures = 0
    try:
        while args.persistent or cycle < args.max_cycles:
            cycle += 1
            print("=" * 78)
            print(f"DEVICE WORKER CYCLE {cycle}")
            print(f"State: {DeviceWorkerState.RUNNING.value}")
            print("=" * 78)

            try:
                proc = subprocess.run(
                    _client_command(args),
                    cwd=ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=args.child_timeout,
                    check=False,
                )
                output = proc.stdout or ""
                returncode = proc.returncode
            except subprocess.TimeoutExpired as exc:
                output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                output += "\nERROR: client demo subprocess exceeded worker deadline"
                returncode = 124

            (private / f"cycle-{cycle:04d}.log").write_text(output, encoding="utf-8", errors="replace")
            payload = load_shareable(ROOT, output)
            child_status = payload.get("status") if isinstance(payload, dict) else None
            reason = payload.get("reason") if isinstance(payload, dict) else None
            reason = str(reason) if reason else (_last_error(output) or f"child exited {returncode}")

            if returncode == 0 and child_status == "READY_FOR_PUBLISH":
                record = {
                    "cycle": cycle,
                    "state": DeviceWorkerState.COMPLETE.value,
                    "client_status": child_status,
                    "recovery_used": False,
                }
                result["cycles"].append(record)
                result.update({
                    "status": "READY_FOR_PUBLISH",
                    "completed_cycle": cycle,
                    "consecutive_failures_before_success": consecutive_failures,
                    "reboot_recommended": False,
                })
                _write_json(shareable, result)
                print("DEVICE WORKER RESULT: READY_FOR_PUBLISH")
                print(f"Completed cycle: {cycle}")
                print("Reboot: NOT USED")
                print(f"Shareable result: {shareable.relative_to(ROOT)}")
                return 0

            consecutive_failures += 1
            if not retryable_client_failure(reason):
                result["cycles"].append({
                    "cycle": cycle,
                    "state": "blocked_configuration",
                    "client_status": child_status,
                    "reason": reason,
                    "recovery_used": False,
                })
                result.update({"status": "BLOCKED_NONRETRYABLE", "reason": reason})
                _write_json(shareable, result)
                print(f"ERROR: non-retryable client failure: {reason}", file=sys.stderr)
                return 2

            reboot_recommended = policy.reboot_approval_recommended(consecutive_failures)
            print(f"Client cycle blocked: {reason}")
            print(f"State: {DeviceWorkerState.APP_RECOVERY.value}")
            recovery = recover_tiktok_without_reboot(
                args.device,
                private / "app-recovery",
            )
            cooldown = policy.cooldown_for_failure(consecutive_failures)
            state = (
                DeviceWorkerState.REBOOT_APPROVAL_RECOMMENDED
                if reboot_recommended
                else DeviceWorkerState.COOLDOWN
            )
            record = {
                "cycle": cycle,
                "state": state.value,
                "client_status": child_status,
                "reason": reason,
                "recovery_used": True,
                "app_recovery_success": recovery.success,
                "force_stop_attempts": recovery.force_stop_attempts,
                "process_gone": recovery.process_gone,
                "stable_foreground": recovery.stable_foreground,
                "app_recovery_reason": recovery.reason,
                "reboot_recommended": reboot_recommended,
                "reboot_attempted": False,
                "cooldown_seconds": cooldown,
            }
            result["cycles"].append(record)
            result["last_state"] = state.value
            result["reboot_recommended"] = reboot_recommended
            _write_json(shareable, result)

            if reboot_recommended:
                print("REBOOT APPROVAL RECOMMENDED: repeated app recovery failures; reboot is disabled")
            print(
                f"App recovery: {'PASS' if recovery.success else 'FAILED'}; "
                f"cooldown={cooldown:.1f}s; reboot=NOT ATTEMPTED"
            )

            if not args.persistent and cycle >= args.max_cycles:
                break
            if cooldown:
                time.sleep(cooldown)

    except KeyboardInterrupt:
        result.update({
            "status": "STOPPED_BY_OPERATOR",
            "last_state": DeviceWorkerState.COOLDOWN.value,
        })
        _write_json(shareable, result)
        print("\nPersistent worker stopped by operator. Reboot was not attempted.")
        print(f"Shareable result: {shareable.relative_to(ROOT)}")
        return 130

    result.update({
        "status": "BLOCKED_AFTER_BOUNDED_CYCLES",
        "completed_cycles": cycle,
        "reason": "bounded worker cycles exhausted without READY_FOR_PUBLISH",
    })
    _write_json(shareable, result)
    print("ERROR: bounded worker cycles exhausted", file=sys.stderr)
    print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
