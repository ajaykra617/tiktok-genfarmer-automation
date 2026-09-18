#!/usr/bin/env python3
"""Read-only concurrent ADB fleet probe.

Use this before blaming TikTok or GenFarmer for an ADB timeout message.
It drives the same self-healing transport used by production actions/observers,
but performs read-only operations only. Multiple devices are probed concurrently
so we can distinguish host/shared adb-server trouble, one device transport
failing while peers remain healthy, and a healthy ADB transport where only
Android input/UI commands are wedged.

No app is launched/stopped, no input is injected, and no global kill-server
operation is performed."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_transport import AdbTransport, AdbTransportError  # noqa: E402


def _parse_device(raw: str) -> tuple[str, str]:
    value = raw.strip()
    if not value:
        raise argparse.ArgumentTypeError("--device cannot be empty")
    if "=" in value:
        name, serial = value.split("=", 1)
        name = name.strip()
        serial = serial.strip()
        if not name or not serial:
            raise argparse.ArgumentTypeError("use --device NAME=SERIAL")
        return name, serial
    return value, value


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * fraction
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    weight = index - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _host_info() -> dict[str, object]:
    path = shutil.which("adb")
    version = ""
    error = None
    if path:
        try:
            proc = subprocess.run(
                [path, "version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5.0,
                check=False,
            )
            version = proc.stdout.decode("utf-8", errors="replace").strip()
            if proc.returncode != 0:
                error = proc.stderr.decode("utf-8", errors="replace").strip() or f"exit-{proc.returncode}"
        except Exception as exc:
            error = str(exc)
    else:
        error = "adb-not-found"
    return {"path": path, "version": version, "error": error}


def _probe_device(name: str, serial: str, *, cycles: int, interval: float, timeout: float) -> dict[str, object]:
    transport = AdbTransport(serial, timeout=timeout, health_timeout=min(timeout, 3.0), read_retries=1)
    rows: list[dict[str, object]] = []
    latencies: list[float] = []
    recoveries = 0
    failures = 0

    for index in range(1, cycles + 1):
        started = time.monotonic()
        row: dict[str, object] = {"cycle": index}
        try:
            health = transport.ensure_ready()
            result = transport.run(
                ["shell", "dumpsys", "window", "windows"],
                timeout=timeout,
                mutation=False,
            )
            elapsed = time.monotonic() - started
            latencies.append(elapsed)
            if result.recovered:
                recoveries += 1
            row.update({
                "ok": True,
                "elapsed_seconds": round(elapsed, 4),
                "state": health.state,
                "shell_ok": health.shell_ok,
                "command_attempts": result.attempts,
                "command_recovered": result.recovered,
            })
        except AdbTransportError as exc:
            elapsed = time.monotonic() - started
            failures += 1
            row.update({
                "ok": False,
                "elapsed_seconds": round(elapsed, 4),
                "error": str(exc),
                "failure_kind": exc.kind.value,
                "transport_healthy": exc.transport_healthy,
                "mutation_ambiguous": exc.mutation_ambiguous,
            })
        rows.append(row)
        if interval and index < cycles:
            time.sleep(interval)

    return {
        "name": name,
        "serial": serial,
        "cycles": cycles,
        "passes": cycles - failures,
        "failures": failures,
        "recoveries": recoveries,
        "latency_seconds": {
            "mean": round(statistics.fmean(latencies), 4) if latencies else None,
            "p50": round(_percentile(latencies, 0.50), 4) if latencies else None,
            "p95": round(_percentile(latencies, 0.95), 4) if latencies else None,
            "max": round(max(latencies), 4) if latencies else None,
        },
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Concurrent read-only ADB fleet reliability probe")
    ap.add_argument(
        "--device", action="append", required=True, type=_parse_device, metavar="NAME=SERIAL",
        help="repeat for each device, e.g. --device GF1=192.168.4.138:5555",
    )
    ap.add_argument("--cycles", type=int, default=30)
    ap.add_argument("--interval", type=float, default=0.35)
    ap.add_argument("--timeout", type=float, default=5.0)
    args = ap.parse_args()

    if not 1 <= args.cycles <= 500:
        ap.error("--cycles must be 1..500")
    if not 0 <= args.interval <= 30:
        ap.error("--interval must be 0..30")
    if not 0.5 <= args.timeout <= 30:
        ap.error("--timeout must be 0.5..30")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence" / f"adb-fleet-probe-{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    payload: dict[str, object] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "host": _host_info(),
        "cycles": args.cycles,
        "interval_seconds": args.interval,
        "timeout_seconds": args.timeout,
        "devices": [],
    }

    print("=" * 78)
    print("ADB FLEET RELIABILITY PROBE (READ-ONLY)")
    print("=" * 78)
    print(f"Devices: {len(args.device)}  Cycles/device: {args.cycles}")

    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=len(args.device)) as pool:
        futures = {
            pool.submit(_probe_device, name, serial, cycles=args.cycles, interval=args.interval, timeout=args.timeout): (name, serial)
            for name, serial in args.device
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: str(item["name"]))
    payload["devices"] = results
    path = out / "adb-fleet-probe.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    failures = 0
    for result in results:
        failures += int(result["failures"])
        lat = result["latency_seconds"]
        print(
            f"{result['name']}: {result['passes']}/{result['cycles']} PASS "
            f"failures={result['failures']} recoveries={result['recoveries']} "
            f"p95={lat['p95']}s max={lat['max']}s"
        )

    print(f"Evidence: {path.relative_to(ROOT)}")
    print("=" * 78)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
