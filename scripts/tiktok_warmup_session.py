#!/usr/bin/env python3
"""Run a full, checkpointed passive TikTok warm-up session.

The controller composes the qualified `tiktok_warmup_step.py` primitive while
owning session-level watch timing, checkpoints, bounded retries, and recovery.
Watch time only advances while TikTok is actually foreground and free of known
interrupts. A TikTok Android permission dialog is handled conservatively by
selecting the exact runtime-derived deny control; permissions are never granted.

No likes, follows, replies, DMs, or other engagement actions are performed.
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
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_observer import AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.permission_recovery import recover_tiktok_permission_dialog  # noqa: E402
from genfarmer_automation.tiktok_runtime import TikTokRuntime  # noqa: E402
from genfarmer_automation.warmup_session import (  # noqa: E402
    WarmupSessionError,
    WarmupSessionPlan,
    build_plan,
    completed_index,
    load_shareable,
    step_passed,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_step(
    *,
    compiled: Path,
    candidates: Path,
    candidate: int,
    device: str,
    preferred_port: int,
    strict_selector: bool,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "tiktok_warmup_step.py"),
        str(compiled),
        str(candidates),
        "--candidate",
        str(candidate),
        "--device",
        device,
        "--preferred-hierarchy-port",
        str(preferred_port),
        "--post-settle",
        "1.0",
        "--apply",
    ]
    if strict_selector:
        cmd.append("--strict-selector")
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120.0,
        check=False,
    )


def _checkpoint_plan(value: Mapping[str, Any]) -> WarmupSessionPlan:
    plan = value.get("plan")
    if not isinstance(plan, Mapping):
        raise WarmupSessionError("checkpoint plan is missing")
    try:
        video_count = int(plan["video_count"])
        watch_seconds = tuple(float(item) for item in plan["watch_seconds"])
        seed = int(plan["seed"])
        max_session_seconds = float(plan["max_session_seconds"])
        step_retries = int(plan["step_retries"])
        failure_budget = int(plan["failure_budget"])
    except (KeyError, TypeError, ValueError) as exc:
        raise WarmupSessionError("checkpoint plan fields are invalid") from exc

    if not 1 <= video_count <= 500 or len(watch_seconds) != video_count:
        raise WarmupSessionError("checkpoint plan video schedule is invalid")
    if any(value < 0 for value in watch_seconds):
        raise WarmupSessionError("checkpoint watch schedule contains a negative duration")
    if not 0 < max_session_seconds <= 3600:
        raise WarmupSessionError("checkpoint session deadline is invalid")
    if not 0 <= step_retries <= 5 or not 0 <= failure_budget <= 20:
        raise WarmupSessionError("checkpoint retry/failure budget is invalid")

    return WarmupSessionPlan(
        video_count=video_count,
        watch_seconds=watch_seconds,
        seed=seed,
        max_session_seconds=max_session_seconds,
        step_retries=step_retries,
        failure_budget=failure_budget,
    )


def _ensure_watch_ready(device: str, observer: AdbObserver) -> int:
    """Return number of permission dialogs recovered while reaching feed-ready state."""
    recovered_permissions = 0
    for _ in range(3):
        obs = observer.observe()
        if obs.interrupt is InterruptKind.ANDROID_PERMISSION_DIALOG:
            result = recover_tiktok_permission_dialog(device, observer=observer)
            if not result.success:
                raise RuntimeError(f"permission-dialog recovery failed: {result.reason}")
            recovered_permissions += int(result.handled)
            continue
        if obs.interrupt is not InterruptKind.NONE:
            raise RuntimeError(f"watch blocked by Android interrupt: {obs.interrupt.value}")
        if obs.adb_state != "device":
            raise RuntimeError("ADB device is not ready during watch")
        if obs.tiktok_foreground:
            return recovered_permissions

        foreground = TikTokRuntime(
            device,
            observer=observer,
            settle_seconds=0.5,
            poll_seconds=0.25,
            max_polls=6,
        ).ensure_foreground()
        if not foreground.success:
            raise RuntimeError(f"TikTok foreground recovery failed during watch: {foreground.reason}")
    raise RuntimeError("TikTok watch readiness was not restored within bounded recovery attempts")


def _watch_active_tiktok(
    device: str,
    seconds: float,
    *,
    observer: AdbObserver,
    session_started: float,
    max_session_seconds: float,
) -> int:
    """Accumulate requested watch time only while TikTok is healthy/foreground."""
    remaining = float(seconds)
    recoveries = 0
    while remaining > 0:
        if time.monotonic() - session_started >= max_session_seconds:
            raise RuntimeError("session deadline reached during watch interval")
        recoveries += _ensure_watch_ready(device, observer)
        chunk = min(1.0, remaining)
        deadline_remaining = max_session_seconds - (time.monotonic() - session_started)
        if chunk >= deadline_remaining:
            raise RuntimeError("watch interval would exceed session deadline")
        time.sleep(chunk)
        remaining = max(0.0, remaining - chunk)
    recoveries += _ensure_watch_ready(device, observer)
    return recoveries


def main() -> int:
    ap = argparse.ArgumentParser(description="Full checkpointed TikTok warm-up session")
    ap.add_argument("compiled", type=Path)
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--device", required=True)
    ap.add_argument("--videos", type=int, default=12)
    ap.add_argument("--watch-min", type=float, default=7.0)
    ap.add_argument("--watch-max", type=float, default=18.0)
    ap.add_argument("--max-session-minutes", type=float, default=30.0)
    ap.add_argument("--step-retries", type=int, default=1)
    ap.add_argument("--failure-budget", type=int, default=2)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--strict-selector", action="store_true")
    ap.add_argument("--resume", type=Path, help="private checkpoint JSON from an interrupted session")
    ap.add_argument("--rest-only", action="store_true", help="record an intentional rest session; no app action")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    previous: Mapping[str, Any] | None = None
    resume_at = 0
    failures = 0
    failure_budget_base = 0
    step_records: list[dict[str, Any]] = []

    if args.resume:
        try:
            raw_previous = json.loads(args.resume.read_text(encoding="utf-8"))
            if not isinstance(raw_previous, Mapping):
                raise WarmupSessionError("checkpoint root must be an object")
            previous = raw_previous
            plan = _checkpoint_plan(previous)
            resume_at = completed_index(previous, total=plan.video_count)
            failures = int(previous.get("failed_attempts", 0))
            failure_budget_base = failures
            old_records = previous.get("steps", [])
            if isinstance(old_records, list):
                step_records = [dict(item) for item in old_records if isinstance(item, Mapping)]
            seed = plan.seed
        except (OSError, json.JSONDecodeError, ValueError, WarmupSessionError) as exc:
            print(f"ERROR: invalid resume checkpoint: {exc}", file=sys.stderr)
            return 2
    else:
        seed = args.seed if args.seed is not None else int(time.time())
        try:
            plan = build_plan(
                video_count=args.videos,
                watch_min_seconds=args.watch_min,
                watch_max_seconds=args.watch_max,
                seed=seed,
                max_session_minutes=args.max_session_minutes,
                step_retries=args.step_retries,
                failure_budget=args.failure_budget,
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-warmup-session-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    checkpoint_path = private / "checkpoint.private.json"
    shareable_path = out / "tiktok-warmup-session.shareable.json"

    summary: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "device_private": True,
        "candidate_index": args.candidate,
        "plan": plan.to_dict(),
        "passive_only": True,
        "engagement_actions": 0,
        "resumed": args.resume is not None,
    }

    if args.rest_only:
        summary.update({"status": "REST_SESSION", "completed_steps": 0, "requested_steps": plan.video_count})
        _write_json(shareable_path, summary)
        print("=" * 78)
        print("TIKTOK WARM-UP SESSION")
        print("=" * 78)
        print("Status:                     REST_SESSION")
        print("App actions:                NONE")
        print(f"Shareable result:           {shareable_path.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    if not args.apply:
        summary.update(
            {
                "status": "DRY_RUN_READY",
                "resume_at": resume_at,
                "requested_steps": plan.video_count,
                "watch_seconds": list(plan.watch_seconds),
            }
        )
        _write_json(shareable_path, summary)
        print("=" * 78)
        print("TIKTOK WARM-UP SESSION")
        print("=" * 78)
        print("Mode:                       DRY-RUN")
        print("Status:                     DRY_RUN_READY")
        print(f"Videos:                     {plan.video_count}")
        print(f"Resume at:                  {resume_at}")
        print(f"Session cap:                {plan.max_session_seconds / 60.0:.1f} min")
        print(f"Seed:                       {seed}")
        print("Mutation:                   NONE")
        print(f"Shareable result:           {shareable_path.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    started = time.monotonic()
    observer = AdbObserver(args.device)
    full_selector_steps = sum(1 for row in step_records if row.get("verification_level") == "full_selector")
    degraded_steps = sum(1 for row in step_records if row.get("verification_level") == "foreground_continuity")
    genfarmer_steps = sum(1 for row in step_records if row.get("action_backend") == "genfarmer")
    adb_steps = sum(1 for row in step_records if row.get("action_backend") == "adb_fallback")
    permission_recoveries = sum(int(row.get("permission_recoveries", 0)) for row in step_records)

    try:
        for index in range(resume_at, plan.video_count):
            if time.monotonic() - started >= plan.max_session_seconds:
                raise RuntimeError("session deadline reached before all requested videos completed")

            watch = plan.watch_seconds[index]
            print(f"[{index + 1}/{plan.video_count}] watching active TikTok feed for {watch:.2f}s")
            step_permission_recoveries = _watch_active_tiktok(
                args.device,
                watch,
                observer=observer,
                session_started=started,
                max_session_seconds=plan.max_session_seconds,
            )
            if step_permission_recoveries:
                permission_recoveries += step_permission_recoveries
                print(f"  recovered {step_permission_recoveries} TikTok permission dialog(s) during watch")

            passed = False
            last_output = ""
            last_payload: Mapping[str, Any] | None = None
            for attempt in range(plan.step_retries + 1):
                if time.monotonic() - started >= plan.max_session_seconds:
                    raise RuntimeError("session deadline reached during step retry")
                extra_recoveries = _ensure_watch_ready(args.device, observer)
                step_permission_recoveries += extra_recoveries
                permission_recoveries += extra_recoveries
                try:
                    proc = _run_step(
                        compiled=args.compiled,
                        candidates=args.candidates,
                        candidate=args.candidate,
                        device=args.device,
                        preferred_port=args.preferred_hierarchy_port,
                        strict_selector=args.strict_selector,
                    )
                    last_output = proc.stdout or ""
                    last_payload = load_shareable(ROOT, last_output)
                    passed = step_passed(proc.returncode, last_payload)
                except subprocess.TimeoutExpired as exc:
                    last_output = f"step subprocess timed out: {exc}"
                    last_payload = None
                    passed = False

                if passed:
                    break
                failures += 1
                if failures - failure_budget_base > plan.failure_budget:
                    raise RuntimeError("session failure budget exceeded")
                if attempt < plan.step_retries:
                    retry_recoveries = _ensure_watch_ready(args.device, observer)
                    step_permission_recoveries += retry_recoveries
                    permission_recoveries += retry_recoveries
                    print(f"  retrying bounded warm-up step ({attempt + 1}/{plan.step_retries})")
                    time.sleep(0.5)

            (private / f"step-{index + 1:03d}.log").write_text(last_output, encoding="utf-8", errors="replace")
            if not passed or last_payload is None:
                raise RuntimeError(f"warm-up step {index + 1} did not reach PASS")

            verification = str(last_payload.get("verification_level", "unknown"))
            backend = str(last_payload.get("action_backend", "unknown"))
            full_selector_steps += verification == "full_selector"
            degraded_steps += verification == "foreground_continuity"
            genfarmer_steps += backend == "genfarmer"
            adb_steps += backend == "adb_fallback"

            record = {
                "step": index + 1,
                "watch_seconds": watch,
                "status": "PASS",
                "verification_level": verification,
                "action_backend": backend,
                "permission_recoveries": step_permission_recoveries,
            }
            step_records.append(record)
            checkpoint = {
                "seed": seed,
                "completed_steps": index + 1,
                "failed_attempts": failures,
                "failed_attempts_this_invocation": failures - failure_budget_base,
                "steps": step_records,
                "plan": plan.to_dict(),
            }
            _write_json(checkpoint_path, checkpoint)
            print(
                f"  PASS verification={verification} backend={backend} "
                f"permission_recoveries={step_permission_recoveries}"
            )

        elapsed = round(time.monotonic() - started, 2)
        summary.update(
            {
                "status": "PASS",
                "requested_steps": plan.video_count,
                "completed_steps": plan.video_count,
                "failed_attempts": failures,
                "failed_attempts_this_invocation": failures - failure_budget_base,
                "elapsed_seconds": elapsed,
                "full_selector_steps": full_selector_steps,
                "foreground_continuity_steps": degraded_steps,
                "genfarmer_steps": genfarmer_steps,
                "adb_fallback_steps": adb_steps,
                "permission_recoveries": permission_recoveries,
                "checkpoint_private": True,
            }
        )
        _write_json(shareable_path, summary)

        print("=" * 78)
        print("TIKTOK WARM-UP SESSION")
        print("=" * 78)
        print("Status:                     PASS")
        print(f"Completed videos:           {plan.video_count}/{plan.video_count}")
        print(f"Full-selector steps:        {full_selector_steps}")
        print(f"Continuity-only steps:      {degraded_steps}")
        print(f"GenFarmer actions:          {genfarmer_steps}")
        print(f"ADB fallback actions:       {adb_steps}")
        print(f"Permission recoveries:      {permission_recoveries}")
        print(f"Failed attempts total:      {failures}")
        print(f"Failed attempts this run:   {failures - failure_budget_base}")
        print(f"Elapsed:                    {elapsed:.2f}s")
        print(f"Private checkpoint:         {checkpoint_path.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable_path.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except RuntimeError as exc:
        checkpoint = {
            "seed": seed,
            "completed_steps": len(step_records),
            "failed_attempts": failures,
            "failed_attempts_this_invocation": failures - failure_budget_base,
            "steps": step_records,
            "plan": plan.to_dict(),
            "blocked_reason": str(exc),
        }
        _write_json(checkpoint_path, checkpoint)
        summary.update(
            {
                "status": "BLOCKED",
                "requested_steps": plan.video_count,
                "completed_steps": len(step_records),
                "failed_attempts": failures,
                "failed_attempts_this_invocation": failures - failure_budget_base,
                "permission_recoveries": permission_recoveries,
                "reason": str(exc),
                "checkpoint_private": True,
            }
        )
        _write_json(shareable_path, summary)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Resume checkpoint: {checkpoint_path.relative_to(ROOT)}", file=sys.stderr)
        print(f"Shareable result: {shareable_path.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
