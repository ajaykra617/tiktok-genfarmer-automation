#!/usr/bin/env python3
"""Run a short qualified passive TikTok warm scroll without a .genfarm export.

This controller is for Boost Phase A preparation. It bootstraps the already-
qualified For You feed through the passive warm-up feature runner, then performs
bounded device-relative swipes. Every swipe is guarded by the qualified feed
anchor before and after the action. No likes, follows, replies, DMs, Create UI,
or Post action are performed.
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

from genfarmer_automation.adb_actions import AdbActions, AdbActionError  # noqa: E402
from genfarmer_automation.adb_observer import AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.feed_anchor_qualification import candidates_from_payload  # noqa: E402
from genfarmer_automation.hierarchy_runtime import HierarchyRuntimeError, capture_hierarchy_batch  # noqa: E402
from genfarmer_automation.permission_recovery import recover_tiktok_permission_dialog  # noqa: E402
from genfarmer_automation.selector_gate import assess_selector_gate  # noqa: E402
from genfarmer_automation.tiktok_runtime import TikTokRuntime  # noqa: E402
from genfarmer_automation.warm_scroll import (  # noqa: E402
    WarmScrollError,
    build_warm_scroll_plan,
    is_transient_bootstrap_failure,
)
from genfarmer_automation.warmup_session import load_shareable  # noqa: E402

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _ready(observer: AdbObserver) -> bool:
    obs = observer.observe()
    return obs.adb_state == "device" and obs.tiktok_foreground and obs.interrupt is InterruptKind.NONE


def _ensure_ready(device: str, observer: AdbObserver) -> int:
    recoveries = 0
    for _ in range(3):
        obs = observer.observe()
        if obs.interrupt is InterruptKind.ANDROID_PERMISSION_DIALOG:
            recovered = recover_tiktok_permission_dialog(device, observer=observer)
            if not recovered.success:
                raise RuntimeError(f"permission recovery failed: {recovered.reason}")
            recoveries += int(recovered.handled)
            continue
        if obs.interrupt is not InterruptKind.NONE:
            raise RuntimeError(f"Android interrupt blocks warm scroll: {obs.interrupt.value}")
        if obs.adb_state != "device":
            raise RuntimeError("ADB device is not ready")
        if obs.tiktok_foreground:
            return recoveries
        restored = TikTokRuntime(device, observer=observer).ensure_foreground()
        if not restored.success:
            raise RuntimeError(f"TikTok foreground recovery failed: {restored.reason}")
    if not _ready(observer):
        raise RuntimeError("TikTok foreground/no-interrupt state was not restored")
    return recoveries


def _feed_gate(device: str, candidate, preferred_port: int):
    batch = capture_hierarchy_batch(
        device,
        count=2,
        interval=0.12,
        preferred_port=preferred_port,
        helper_timeout=4.0,
        max_ports=12,
    )
    gate = assess_selector_gate(candidate, batch.snapshots, package=TIKTOK_PACKAGE)
    if not gate.passed:
        raise RuntimeError(f"qualified For You feed anchor failed with counts={gate.counts}")
    return gate, batch


def _bootstrap_fyp(candidates: Path, candidate: int, device: str, preferred_port: int, private: Path) -> int:
    """Bootstrap qualified FYP, retrying once only for hierarchy unavailability."""
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "tiktok_warmup_feature.py"),
        str(candidates),
        "--candidate", str(candidate),
        "--device", device,
        "--feature", "for-you",
        "--dwell-min", "0",
        "--dwell-max", "0",
        "--preferred-hierarchy-port", str(preferred_port),
        "--seed", "1",
        "--apply",
    ]

    final_payload = None
    final_output = ""
    final_returncode = 1
    retries = 0

    for attempt in range(1, 3):
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180.0,
            check=False,
        )
        output = proc.stdout or ""
        (private / f"bootstrap-fyp-attempt-{attempt:02d}.log").write_text(
            output, encoding="utf-8", errors="replace"
        )
        payload = load_shareable(ROOT, output)
        final_payload = payload if isinstance(payload, dict) else None
        final_output = output
        final_returncode = proc.returncode

        if final_returncode == 0 and isinstance(final_payload, dict) and final_payload.get("status") == "PASS":
            (private / "bootstrap-fyp.log").write_text(output, encoding="utf-8", errors="replace")
            return retries

        if attempt >= 2 or not is_transient_bootstrap_failure(final_payload):
            break

        retries += 1
        print("FYP bootstrap: transient hierarchy failure; retrying once")
        time.sleep(1.25)

    (private / "bootstrap-fyp.log").write_text(final_output, encoding="utf-8", errors="replace")
    reason = final_payload.get("reason") if isinstance(final_payload, dict) else None
    if isinstance(reason, str) and reason.strip():
        raise RuntimeError(f"qualified For You bootstrap did not reach PASS: {reason}")
    raise RuntimeError("qualified For You bootstrap did not reach PASS")


def main() -> int:
    ap = argparse.ArgumentParser(description="Short qualified passive TikTok Boost warm scroll")
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--device", required=True)
    ap.add_argument("--videos", type=int, default=3)
    ap.add_argument("--watch-min", type=float, default=5.0)
    ap.add_argument("--watch-max", type=float, default=10.0)
    ap.add_argument("--max-session-minutes", type=float, default=8.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-boost-warm-scroll-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-boost-warm-scroll.shareable.json"

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "device_private": True,
        "candidate_index": args.candidate,
        "passive_only": True,
        "engagement_actions": 0,
        "publishing_ui_entered": False,
    }

    try:
        plan = build_warm_scroll_plan(
            videos=args.videos,
            watch_min_seconds=args.watch_min,
            watch_max_seconds=args.watch_max,
            seed=args.seed,
            max_session_minutes=args.max_session_minutes,
        )
        raw = json.loads(args.candidates.read_text(encoding="utf-8"))
        candidates = candidates_from_payload(raw)
        if not 1 <= args.candidate <= len(candidates):
            raise RuntimeError("candidate file does not contain requested candidate")
        candidate = candidates[args.candidate - 1]
        result["plan"] = {
            "videos": plan.videos,
            "watch_seconds": list(plan.watch_seconds),
            "seed": plan.seed,
            "max_session_seconds": plan.max_session_seconds,
        }

        if not args.apply:
            result["status"] = "DRY_RUN_READY"
            _write_json(shareable, result)
            print("Status:                     DRY_RUN_READY")
            print(f"Videos:                     {plan.videos}")
            print("Mutation:                   NONE")
            print(f"Shareable result:           {shareable.relative_to(ROOT)}")
            return 0

        observer = AdbObserver(args.device)
        actions = AdbActions(args.device)
        permission_recoveries = _ensure_ready(args.device, observer)
        bootstrap_retries = _bootstrap_fyp(
            args.candidates,
            args.candidate,
            args.device,
            args.preferred_hierarchy_port,
            private,
        )
        started = time.monotonic()
        providers: set[str] = set()

        for index, watch_seconds in enumerate(plan.watch_seconds, start=1):
            if time.monotonic() - started >= plan.max_session_seconds:
                raise RuntimeError("warm-scroll session deadline reached")
            permission_recoveries += _ensure_ready(args.device, observer)
            pre_gate, pre_batch = _feed_gate(args.device, candidate, args.preferred_hierarchy_port)
            providers.add(pre_batch.provider)
            print(f"[{index}/{plan.videos}] feed PASS; watching {watch_seconds:.2f}s")

            remaining = float(watch_seconds)
            while remaining > 0:
                if time.monotonic() - started >= plan.max_session_seconds:
                    raise RuntimeError("warm-scroll session deadline reached during watch")
                permission_recoveries += _ensure_ready(args.device, observer)
                chunk = min(1.0, remaining)
                time.sleep(chunk)
                remaining -= chunk

            frame = observer.capture_raw_frame()
            actions.swipe_up_relative(width=frame.width, height=frame.height)
            time.sleep(1.0)
            permission_recoveries += _ensure_ready(args.device, observer)
            post_gate, post_batch = _feed_gate(args.device, candidate, args.preferred_hierarchy_port)
            providers.add(post_batch.provider)
            print(f"  PASS pre={pre_gate.counts} post={post_gate.counts}")

        observer.capture_screenshot(private / "after.png")
        result.update(
            {
                "status": "PASS",
                "completed_videos": plan.videos,
                "permission_recoveries": permission_recoveries,
                "bootstrap_transient_retries": bootstrap_retries,
                "hierarchy_providers": sorted(providers),
                "action_backend": "adb_relative_swipe",
            }
        )
        _write_json(shareable, result)
        print("=" * 78)
        print("TIKTOK BOOST WARM SCROLL")
        print("=" * 78)
        print("Status:                     PASS")
        print(f"Completed videos:           {plan.videos}/{plan.videos}")
        print(f"Bootstrap retries:          {bootstrap_retries}")
        print("Feed verification:          QUALIFIED ANCHOR BEFORE/AFTER EACH SWIPE")
        print("Engagement actions:         NONE")
        print("Publishing UI:              NOT ENTERED")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except (OSError, json.JSONDecodeError, ValueError, RuntimeError, WarmScrollError, HierarchyRuntimeError, AdbActionError) as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        _write_json(shareable, result)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
