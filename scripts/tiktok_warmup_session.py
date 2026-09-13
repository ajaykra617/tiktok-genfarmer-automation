#!/usr/bin/env python3
"""Run a full, checkpointed passive TikTok warm-up session.

The session controller deliberately composes the already-qualified
`tiktok_warmup_step.py` primitive instead of duplicating its safety logic.
Each logical video gets a deterministic watch delay, bounded retries, a private
checkpoint, and a shareable summary. No likes, follows, replies, DMs, or other
engagement actions are performed.
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

from genfarmer_automation.warmup_session import (  # noqa: E402
    WarmupSessionError,
    build_plan,
    completed_index,
    load_shareable,
    step_passed,
)


def _write_json(path: Path, value) -> None:
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

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "device_private": True,
        "candidate_index": args.candidate,
        "plan": plan.to_dict(),
        "passive_only": True,
        "engagement_actions": 0,
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

    resume_at = 0
    failures = 0
    step_records: list[dict] = []
    if args.resume:
        try:
            previous = json.loads(args.resume.read_text(encoding="utf-8"))
            resume_at = completed_index(previous, total=plan.video_count)
            failures = int(previous.get("failed_attempts", 0))
            old_records = previous.get("steps", [])
            if isinstance(old_records, list):
                step_records = list(old_records)
        except (OSError, json.JSONDecodeError, ValueError, WarmupSessionError) as exc:
            print(f"ERROR: invalid resume checkpoint: {exc}", file=sys.stderr)
            return 2

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
        print(f"Watch range:                {args.watch_min:.1f}-{args.watch_max:.1f}s")
        print(f"Session cap:                {args.max_session_minutes:.1f} min")
        print(f"Seed:                       {seed}")
        print("Mutation:                   NONE")
        print(f"Shareable result:           {shareable_path.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    started = time.monotonic()
    full_selector_steps = sum(1 for row in step_records if row.get("verification_level") == "full_selector")
    degraded_steps = sum(1 for row in step_records if row.get("verification_level") == "foreground_continuity")
    genfarmer_steps = sum(1 for row in step_records if row.get("action_backend") == "genfarmer")
    adb_steps = sum(1 for row in step_records if row.get("action_backend") == "adb_fallback")

    try:
        for index in range(resume_at, plan.video_count):
            if time.monotonic() - started >= plan.max_session_seconds:
                raise RuntimeError("session deadline reached before all requested videos completed")

            watch = plan.watch_seconds[index]
            remaining = plan.max_session_seconds - (time.monotonic() - started)
            if watch >= remaining:
                raise RuntimeError("next watch interval would exceed session deadline")

            print(f"[{index + 1}/{plan.video_count}] watching current feed item for {watch:.2f}s")
            time.sleep(watch)

            passed = False
            last_output = ""
            last_payload = None
            for attempt in range(plan.step_retries + 1):
                if time.monotonic() - started >= plan.max_session_seconds:
                    raise RuntimeError("session deadline reached during step retry")
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
                if failures > plan.failure_budget:
                    raise RuntimeError("session failure budget exceeded")
                if attempt < plan.step_retries:
                    print(f"  retrying bounded warm-up step ({attempt + 1}/{plan.step_retries})")
                    time.sleep(1.0)

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
            }
            step_records.append(record)
            checkpoint = {
                "seed": seed,
                "completed_steps": index + 1,
                "failed_attempts": failures,
                "steps": step_records,
                "plan": plan.to_dict(),
            }
            _write_json(checkpoint_path, checkpoint)
            print(f"  PASS verification={verification} backend={backend}")

        elapsed = round(time.monotonic() - started, 2)
        summary.update(
            {
                "status": "PASS",
                "requested_steps": plan.video_count,
                "completed_steps": plan.video_count,
                "failed_attempts": failures,
                "elapsed_seconds": elapsed,
                "full_selector_steps": full_selector_steps,
                "foreground_continuity_steps": degraded_steps,
                "genfarmer_steps": genfarmer_steps,
                "adb_fallback_steps": adb_steps,
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
        print(f"Failed attempts recovered:  {failures}")
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
