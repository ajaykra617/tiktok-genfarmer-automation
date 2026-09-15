#!/usr/bin/env python3
"""Run TikTok Boost Phase A tasks in concurrent waves with hard barriers.

Each wave is validated before launch. Tasks inside a wave run concurrently; the
next wave never starts until every task in the current wave reaches its expected
Phase A terminal state. Apply mode additionally requires a real external-IP
egress check through every configured HTTP proxy before any device task starts.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.phase_a_waves import (  # noqa: E402
    PhaseAWaveError,
    build_task_command,
    load_phase_a_runtime,
    validate_runtime_for_plan,
)
from genfarmer_automation.proxy_readiness import (  # noqa: E402
    ProxyReadinessError,
    probe_http_proxy,
)
from genfarmer_automation.schedule_policy import (  # noqa: E402
    SchedulePolicyError,
    load_schedule_plan,
    plan_summary,
)
from genfarmer_automation.warmup_session import load_shareable  # noqa: E402


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_task(cmd: list[str], *, timeout: float) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout or ""
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return 124, str(output) + f"\nERROR: task timed out after {timeout}s\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Concurrent barrier executor for TikTok Boost Phase A")
    ap.add_argument("--schedule", type=Path, required=True, help="logical wave schedule JSON")
    ap.add_argument("--runtime", type=Path, required=True, help="ignored local runtime JSON with device/proxy/media values")
    ap.add_argument("--ip-check-url", help="external IP endpoint used through each HTTP proxy")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--task-timeout", type=float, default=1200.0)
    ap.add_argument("--skip-interval", action="store_true", help="qualification only: skip configured between-wave wait")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.task_timeout <= 0:
        print("ERROR: --task-timeout must be positive", file=sys.stderr)
        return 2
    if args.apply and not args.ip_check_url:
        print("ERROR: apply mode requires --ip-check-url so proxy egress/public IP is verified", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence" / f"boost-phase-a-waves-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "boost-phase-a-waves.shareable.json"

    result: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "seed": args.seed,
        "publishing_deferred": True,
        "engagement_actions": 0,
        "waves": [],
    }

    try:
        schedule_payload = json.loads(args.schedule.read_text(encoding="utf-8"))
        runtime_payload = json.loads(args.runtime.read_text(encoding="utf-8"))
        if not isinstance(schedule_payload, dict) or not isinstance(runtime_payload, dict):
            raise PhaseAWaveError("schedule/runtime roots must be JSON objects")
        plan = load_schedule_plan(schedule_payload)
        runtime = load_phase_a_runtime(runtime_payload, root=ROOT)
        validate_runtime_for_plan(plan, runtime)
        result["plan"] = plan_summary(plan)

        rng = random.Random(args.seed)
        expected = "READY_FOR_PUBLISH" if args.apply else "DRY_RUN_READY"

        for wave_index, wave in enumerate(plan.waves, start=1):
            print(f"[{wave_index}/{len(plan.waves)}] preflighting {wave.name} ({len(wave.tasks)} task(s))")
            proxy_private: dict[str, Any] = {}
            proxy_seen: set[str] = set()
            for task in wave.tasks:
                if task.proxy_id in proxy_seen:
                    continue
                proxy_seen.add(task.proxy_id)
                proxy = runtime.proxies[task.proxy_id]
                readiness = probe_http_proxy(
                    proxy.http_url,
                    check_url=args.ip_check_url if args.apply else None,
                    timeout=8.0,
                )
                if not readiness.tcp_reachable:
                    raise ProxyReadinessError(f"proxy {task.proxy_id!r} TCP endpoint is unreachable")
                if args.apply and not readiness.ready:
                    raise ProxyReadinessError(f"proxy {task.proxy_id!r} did not prove external HTTP(S) egress")
                proxy_private[task.proxy_id] = {
                    "tcp_reachable": readiness.tcp_reachable,
                    "egress_verified": readiness.egress_verified,
                    "external_ip": readiness.external_ip,
                }
            _write_json(private / f"wave-{wave_index:02d}-proxy-readiness.private.json", proxy_private)

            wave_result: dict[str, Any] = {
                "name": wave.name,
                "tasks": [],
                "proxy_tcp_ready": True,
                "proxy_egress_verified": bool(args.apply),
                "barrier_passed": False,
            }
            futures = {}
            with ThreadPoolExecutor(max_workers=len(wave.tasks)) as pool:
                for task_index, task in enumerate(wave.tasks, start=1):
                    task_seed = args.seed + wave_index * 1000 + task_index
                    cmd = build_task_command(
                        task,
                        runtime,
                        python_executable=sys.executable,
                        root=ROOT,
                        seed=task_seed,
                        apply=args.apply,
                    )
                    future = pool.submit(_run_task, cmd, timeout=args.task_timeout)
                    futures[future] = (task_index, task, task_seed)

                task_rows: list[dict[str, Any]] = []
                failed = False
                for future in as_completed(futures):
                    task_index, task, task_seed = futures[future]
                    returncode, output = future.result()
                    (private / f"wave-{wave_index:02d}-task-{task_index:02d}.log").write_text(
                        output, encoding="utf-8", errors="replace"
                    )
                    child = load_shareable(ROOT, output)
                    status = str(child.get("status")) if child else "MISSING_RESULT"
                    passed = returncode == 0 and status == expected
                    failed = failed or not passed
                    task_rows.append(
                        {
                            "task_index": task_index,
                            "device_private": True,
                            "proxy_id_private": True,
                            "app": task.app,
                            "mode": task.mode,
                            "preset": task.preset,
                            "seed": task_seed,
                            "status": status,
                            "passed": passed,
                        }
                    )
                    print(f"  task {task_index}: {'PASS' if passed else 'BLOCKED'} status={status}")

            task_rows.sort(key=lambda item: item["task_index"])
            wave_result["tasks"] = task_rows
            if failed:
                wave_result["status"] = "BLOCKED"
                result["waves"].append(wave_result)
                result["status"] = "BLOCKED"
                result["blocked_wave"] = wave.name
                _write_json(shareable, result)
                print(f"ERROR: wave {wave.name!r} failed; later waves were not started", file=sys.stderr)
                print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
                return 1

            wave_result["status"] = "PASS"
            wave_result["barrier_passed"] = True
            result["waves"].append(wave_result)
            print(f"  barrier PASS for {wave.name}")

            if wave_index < len(plan.waves):
                wait_minutes = rng.uniform(plan.interval_min_minutes, plan.interval_max_minutes)
                wave_result["next_wave_wait_minutes"] = round(wait_minutes, 3)
                wave_result["interval_skipped"] = bool(args.skip_interval)
                if not args.skip_interval and wait_minutes > 0:
                    print(f"  waiting {wait_minutes:.2f} minute(s) before next wave")
                    time.sleep(wait_minutes * 60.0)

        result["status"] = "PASS"
        result["completed_waves"] = len(plan.waves)
        result["all_barriers_passed"] = True
        result["publish_action_performed"] = False
        _write_json(shareable, result)
        print("=" * 78)
        print("BOOST PHASE A WAVE EXECUTOR")
        print("=" * 78)
        print("Status:                     PASS")
        print(f"Waves completed:            {len(plan.waves)}/{len(plan.waves)}")
        print("All barriers:               PASS")
        print(f"Proxy egress required:      {'YES' if args.apply else 'NO (dry-run)'}")
        print("Publishing UI:              DEFERRED / NOT ENTERED")
        print("Final Post action:          NONE")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except (
        OSError,
        json.JSONDecodeError,
        SchedulePolicyError,
        PhaseAWaveError,
        ProxyReadinessError,
        ValueError,
    ) as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        _write_json(shareable, result)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
