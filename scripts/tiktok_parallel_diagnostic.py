#!/usr/bin/env python3
"""Run bounded self-healing TikTok diagnostics on multiple devices concurrently.

Each device gets its own persistent-worker process, evidence tree and interaction
trace. Child output is streamed line-by-line with a device prefix so timing and
failure-domain differences are visible in one console without mixing evidence.

This launcher does not reboot devices, clear application data, restart the global
ADB server, publish, or perform engagement actions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import os
import queue
import re
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.interaction_trace import console_safe_text  # noqa: E402


def _parse_device(raw: str) -> tuple[str, str]:
    value = raw.strip()
    if "=" not in value:
        raise argparse.ArgumentTypeError("use --device NAME=SERIAL")
    name, serial = value.split("=", 1)
    name = name.strip()
    serial = serial.strip()
    if not name or not serial:
        raise argparse.ArgumentTypeError("use --device NAME=SERIAL")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise argparse.ArgumentTypeError("device NAME must contain only letters, digits, dot, underscore, hyphen")
    return name, serial


def _worker_command(args, serial: str) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "tiktok_persistent_device_worker.py"),
        str(args.candidates),
        "--candidate", str(args.candidate),
        "--device", serial,
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
        "--max-cycles", str(args.max_cycles),
        "--preferred-hierarchy-port", str(args.preferred_hierarchy_port),
    ] + (
        ["--ai-advisor", "--ai-timeout", str(args.ai_timeout)]
        if getattr(args, "ai_advisor", False)
        else []
    )


def _worker_exit_status(returncode: int) -> str:
    if returncode == 0:
        return "READY_FOR_PUBLISH"
    if returncode == 3:
        return "WAITING_RESOURCE"
    return "FAILED"


def main() -> int:
    ap = argparse.ArgumentParser(description="Parallel multi-device TikTok diagnostic runner")
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--device", action="append", required=True, type=_parse_device, metavar="NAME=SERIAL")
    ap.add_argument("--candidate", type=int, default=8)
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
    ap.add_argument("--max-cycles", type=int, default=2)
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument(
        "--ai-advisor",
        action="store_true",
        help="enable constrained ModCon recovery advice in each device worker",
    )
    ap.add_argument("--ai-timeout", type=float, default=20.0)
    args = ap.parse_args()

    names = [name for name, _serial in args.device]
    if len(set(names)) != len(names):
        ap.error("device names must be unique")
    if not 1 <= len(args.device) <= 20:
        ap.error("1..20 devices are supported")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence" / f"parallel-diagnostic-{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    events: queue.Queue[tuple[str, str | None]] = queue.Queue()
    procs: dict[str, subprocess.Popen[str]] = {}
    logs: dict[str, object] = {}
    readers: list[threading.Thread] = []

    def reader(name: str, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                events.put((name, line))
        finally:
            events.put((name, None))

    try:
        for name, serial in args.device:
            log = (out / f"{name}.log").open("w", encoding="utf-8", errors="replace")
            logs[name] = log
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8:backslashreplace"
            proc = subprocess.Popen(
                _worker_command(args, serial),
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                env=env,
                encoding="utf-8",
                errors="backslashreplace",
            )
            procs[name] = proc
            thread = threading.Thread(target=reader, args=(name, proc), daemon=True, name=f"reader-{name}")
            thread.start()
            readers.append(thread)
            print(console_safe_text(f"[{name}] START serial={serial} pid={proc.pid}"), flush=True)

        finished: set[str] = set()
        while len(finished) < len(procs):
            name, line = events.get()
            if line is None:
                finished.add(name)
                continue
            print(console_safe_text(f"[{name}] {line}"), end="", flush=True)
            log = logs[name]
            log.write(line)
            log.flush()

    except KeyboardInterrupt:
        print("\nStopping parallel diagnostic workers...", flush=True)
        for proc in procs.values():
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
        for proc in procs.values():
            try:
                proc.wait(timeout=5.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        return 130
    finally:
        for log in logs.values():
            try:
                log.close()
            except Exception:
                pass

    failures = 0
    resource_waits = 0
    print("=" * 78)
    print("PARALLEL DIAGNOSTIC RESULT")
    print("=" * 78)
    for name, serial in args.device:
        returncode = procs[name].wait()
        status = _worker_exit_status(returncode)
        if status == "WAITING_RESOURCE":
            resource_waits += 1
        elif status == "FAILED":
            failures += 1
        print(f"{name}: serial={serial} status={status} exit={returncode}")
    print(f"Combined logs: {out.relative_to(ROOT)}")
    print("=" * 78)
    if failures:
        return 1
    if resource_waits:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
