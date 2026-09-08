#!/usr/bin/env python3
"""Qualify one passive TikTok browse transition with false-success protection.

Dry-run by default. The probe first measures *control drift* while doing nothing.
Only when the current screen is quiet enough does ``--apply`` perform one
bounded device-relative upward swipe, then require TikTok to remain foreground,
require no known interrupt, and require a conservative persistent visual
transition. The ADB swipe is a lab qualification executor only; production
browsing should use the already-qualified GenFarmer Simple/Up Swipe node while
reusing the same Python pre/post verification logic.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_actions import AdbActions, AdbActionError  # noqa: E402
from genfarmer_automation.adb_observer import AdbObserver, AdbObservationError, InterruptKind  # noqa: E402
from genfarmer_automation.screen_transition import (  # noqa: E402
    TransitionDecision,
    TransitionReport,
    assess_visual_transition,
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


def collect_frames(observer: AdbObserver, count: int, interval: float):
    frames = []
    for index in range(count):
        frames.append(observer.capture_raw_frame())
        if index + 1 < count and interval:
            time.sleep(interval)
    return frames


def report_dict(report: TransitionReport) -> dict[str, object]:
    value = asdict(report)
    value["decision"] = report.decision.value
    return value


def ready(observation) -> bool:
    return (
        observation.adb_state == "device"
        and observation.tiktok_foreground
        and observation.interrupt is InterruptKind.NONE
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Qualify one TikTok browse transition")
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB from .env")
    ap.add_argument("--apply", action="store_true", help="perform exactly one lab swipe")
    ap.add_argument("--frames", type=int, default=3, help="frames per observation window")
    ap.add_argument("--frame-interval", type=float, default=0.25)
    ap.add_argument("--control-gap", type=float, default=1.0)
    ap.add_argument("--post-settle", type=float, default=0.9)
    ap.add_argument("--duration-ms", type=int, default=450)
    args = ap.parse_args()

    if args.frames < 2 or args.frames > 8:
        print("ERROR: --frames must be 2..8", file=sys.stderr)
        return 2
    if min(args.frame_interval, args.control_gap, args.post_settle) < 0:
        print("ERROR: timing values must be non-negative", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not device:
        print("ERROR: pass --device or configure DEFAULT_DEVICE_ADB", file=sys.stderr)
        return 2

    safe_device = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in device)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence" / f"tiktok-browse-one-transition-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)

    observer = AdbObserver(device)
    actions = AdbActions(device)
    result: dict[str, object] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "status": "started",
        "action_executor": "adb-relative-swipe-lab-only" if args.apply else "none",
    }

    try:
        initial = observer.observe()
        result["initial"] = initial.to_dict()
        observer.capture_screenshot(private / "initial.png")
        if not ready(initial):
            result["status"] = "BLOCKED_NOT_READY"
            result["reason"] = "TikTok foreground/no-interrupt precondition not proven"
            exit_code = 1
            control = None
            action_report = None
        else:
            before = collect_frames(observer, args.frames, args.frame_interval)
            if args.control_gap:
                time.sleep(args.control_gap)
            control_frames = collect_frames(observer, args.frames, args.frame_interval)
            control = assess_visual_transition(before, control_frames)
            result["control"] = report_dict(control)

            # If doing nothing already looks like a full transition, visual-only
            # evidence cannot distinguish a real swipe on this content right now.
            if control.decision is TransitionDecision.PROVEN_CHANGED:
                result["status"] = "INCONCLUSIVE_CONTROL_DRIFT"
                result["reason"] = "screen changed enough without any action; visual proof is unsafe for this sample"
                exit_code = 1
                action_report = None
            elif not args.apply:
                result["status"] = "DRY_RUN_READY"
                result["reason"] = "control drift stayed below the transition gate; rerun with --apply for one bounded lab swipe"
                exit_code = 0
                action_report = None
            else:
                immediate = observer.observe()
                if not ready(immediate):
                    result["status"] = "BLOCKED_BEFORE_ACTION"
                    result["reason"] = "foreground/interrupt state changed before the action"
                    exit_code = 1
                    action_report = None
                else:
                    width = control_frames[-1].width
                    height = control_frames[-1].height
                    actions.swipe_up_relative(
                        width=width,
                        height=height,
                        duration_ms=args.duration_ms,
                    )
                    if args.post_settle:
                        time.sleep(args.post_settle)
                    post_observation = observer.observe()
                    result["post_observation"] = post_observation.to_dict()
                    observer.capture_screenshot(private / "after.png")
                    if not ready(post_observation):
                        result["status"] = "BLOCKED_AFTER_ACTION"
                        result["reason"] = "TikTok foreground/no-interrupt postcondition failed after swipe"
                        exit_code = 1
                        action_report = None
                    else:
                        after = collect_frames(observer, args.frames, args.frame_interval)
                        adaptive_changed_ratio = max(
                            0.15,
                            float(control.changed_ratio_of_stable) + 0.10,
                        )
                        action_report = assess_visual_transition(
                            control_frames,
                            after,
                            min_changed_ratio=adaptive_changed_ratio,
                        )
                        result["action_transition"] = report_dict(action_report)
                        result["adaptive_min_changed_ratio"] = adaptive_changed_ratio
                        if action_report.decision is TransitionDecision.PROVEN_CHANGED:
                            result["status"] = "PASS_VISUAL_TRANSITION"
                            result["reason"] = (
                                "one swipe produced persistent distributed visual change above measured control drift; "
                                "this is secondary evidence, not yet selector-level proof of feed identity"
                            )
                            exit_code = 0
                        else:
                            result["status"] = "INCONCLUSIVE_AFTER_ACTION"
                            result["reason"] = "swipe executed but conservative visual postcondition was not proven"
                            exit_code = 1

        shareable = out / "tiktok-browse-one-transition.shareable.json"
        shareable.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print("=" * 78)
        print("TIKTOK BROWSE_ONE TRANSITION PROBE")
        print("=" * 78)
        print(f"Mode:                 {'APPLY' if args.apply else 'DRY-RUN'}")
        print(f"Status:               {result['status']}")
        if control is not None:
            print(f"Control stable ratio: {control.baseline_stable_ratio * 100:.1f}%")
            print(f"Control changed ratio:{control.changed_ratio_of_stable * 100:6.1f}%")
        if action_report is not None:
            print(f"Action changed ratio: {action_report.changed_ratio_of_stable * 100:.1f}%")
            print(f"Changed cells:        {action_report.changed_cells}/{action_report.occupied_cells}")
            print(f"Transition decision:  {action_report.decision.value}")
        print(f"Reason:               {result.get('reason', '')}")
        if not args.apply and result["status"] == "DRY_RUN_READY":
            print("Next:                 rerun the same command with --apply for exactly one lab swipe")
        print("Safety:               production action execution remains GenFarmer Simple/Up; this ADB swipe is lab qualification only")
        print(f"Private evidence:     {private.relative_to(ROOT)}")
        print(f"Shareable result:     {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return exit_code
    except (AdbObservationError, AdbActionError, OSError, ValueError) as exc:
        result["status"] = "ERROR"
        result["reason"] = str(exc)
        (out / "tiktok-browse-one-transition.shareable.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
