#!/usr/bin/env python3
"""Discover the active GenFarmer/openatx Android hierarchy endpoint automatically.

GenFarmer's packaged source contains atx-agent/UiAutomator2 hierarchy support,
but the helper is not listening on the usual 7912/6790 ports in the current lab
session. This probe derives candidate ports from runtime evidence on the
selected Android device (listening sockets and helper process command lines),
then temporarily ADB-forwards only those ports and performs read-only HTTP
probes. If `/dump/hierarchy` is found, it captures repeated XML snapshots and
runs the existing conservative selector learner.

No helper is installed or restarted. No WebDriver session is created. No app UI
action is performed. Every temporary ADB forward is removed before exit.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_observer import AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.android_listener_discovery import (  # noqa: E402
    extract_ports_from_cmdline,
    parse_proc_net_tcp,
    parse_ss_listeners,
    prioritized_candidate_ports,
)
from genfarmer_automation.atx_bridge import extract_atx_hierarchy_xml  # noqa: E402
from genfarmer_automation.ui_xml import UiXmlError, learn_selector_candidates, parse_ui_xml  # noqa: E402

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"
HELPER_RE = re.compile(r"(?i)(atx|uiautomator|automation|appium|genfarmer|minicap|minitouch)")


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


def adb(device: str, *args: str, timeout: float = 10.0) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["adb", "-s", device, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("adb was not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"adb command timed out after {timeout}s") from exc


def proc_text(proc: subprocess.CompletedProcess[bytes]) -> str:
    return proc.stdout.decode("utf-8", errors="replace").strip()


def create_forward(device: str, remote_port: int) -> int | None:
    proc = adb(device, "forward", "tcp:0", f"tcp:{remote_port}", timeout=6.0)
    if proc.returncode != 0:
        return None
    value = proc_text(proc)
    return int(value) if value.isdigit() and 1 <= int(value) <= 65535 else None


def remove_forward(device: str, local_port: int) -> None:
    adb(device, "forward", "--remove", f"tcp:{local_port}", timeout=4.0)


def http_get(url: str, timeout: float) -> tuple[int, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": "genfarmer-runtime-port-discovery/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    raw = body.decode("utf-8", errors="replace").strip()
    if not raw:
        return status, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def runtime_evidence(device: str) -> dict[str, Any]:
    ss = adb(device, "shell", "ss", "-ltn", timeout=8.0)
    tcp = adb(device, "shell", "cat", "/proc/net/tcp", timeout=8.0)
    tcp6 = adb(device, "shell", "cat", "/proc/net/tcp6", timeout=8.0)
    ps = adb(device, "shell", "ps", "-A", timeout=8.0)

    ss_text = proc_text(ss) if ss.returncode == 0 else ""
    tcp_text = proc_text(tcp) if tcp.returncode == 0 else ""
    tcp6_text = proc_text(tcp6) if tcp6.returncode == 0 else ""
    ps_text = proc_text(ps) if ps.returncode == 0 else ""

    ports: list[int] = []
    for value in (*parse_ss_listeners(ss_text), *parse_proc_net_tcp(tcp_text), *parse_proc_net_tcp(tcp6_text)):
        if value not in ports:
            ports.append(value)

    helper_lines = [line for line in ps_text.splitlines() if HELPER_RE.search(line)]
    cmdlines: list[str] = []
    pid_re = re.compile(r"^\S+\s+(?P<pid>\d+)\b")
    for line in helper_lines:
        match = pid_re.match(line.strip())
        if not match:
            continue
        pid = match.group("pid")
        cmd = adb(device, "shell", "cat", f"/proc/{pid}/cmdline", timeout=4.0)
        if cmd.returncode != 0:
            continue
        value = proc_text(cmd).replace("\x00", " ").strip()
        if value:
            cmdlines.append(value)

    hints: list[int] = []
    for line in [*helper_lines, *cmdlines]:
        for port in extract_ports_from_cmdline(line):
            if port not in hints:
                hints.append(port)

    return {
        "observed_listener_ports": ports,
        "helper_process_lines": helper_lines,
        "helper_cmdlines": cmdlines,
        "cmdline_port_hints": hints,
        "ss_available": bool(ss_text),
        "proc_tcp_available": bool(tcp_text or tcp6_text),
    }


def capture_hierarchy(base: str, timeout: float) -> str | None:
    response = http_get(base + "/dump/hierarchy", timeout=timeout)
    if response is None:
        return None
    xml = extract_atx_hierarchy_xml(response[1])
    if xml is None:
        return None
    try:
        parse_ui_xml(xml)
    except UiXmlError:
        return None
    return xml


def main() -> int:
    ap = argparse.ArgumentParser(description="Discover active GenFarmer/openatx hierarchy port from Android runtime evidence")
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB")
    ap.add_argument("--max-ports", type=int, default=24, help="maximum runtime-derived ports to test, 1..64")
    ap.add_argument("--http-timeout", type=float, default=0.8)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--interval", type=float, default=0.35)
    args = ap.parse_args()

    if not 1 <= args.max_ports <= 64:
        print("ERROR: --max-ports must be 1..64", file=sys.stderr)
        return 2
    if not 0.2 <= args.http_timeout <= 5.0:
        print("ERROR: --http-timeout must be 0.2..5.0 seconds", file=sys.stderr)
        return 2
    if not 2 <= args.samples <= 8:
        print("ERROR: --samples must be 2..8", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not device:
        print("ERROR: configure DEFAULT_DEVICE_ADB or pass --device", file=sys.stderr)
        return 2

    observation = AdbObserver(device).observe()
    if observation.adb_state != "device" or not observation.tiktok_foreground or observation.interrupt is not InterruptKind.NONE:
        print("ERROR: TikTok foreground/no-interrupt precondition not proven", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
    out = ROOT / "evidence" / f"tiktok-uia2-runtime-discovery-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable_path = out / "tiktok-uia2-runtime-discovery.shareable.json"

    evidence = runtime_evidence(device)
    (private / "runtime-evidence.private.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    candidates = prioritized_candidate_ports(
        evidence["observed_listener_ports"],
        evidence["cmdline_port_hints"],
        max_ports=args.max_ports,
    )

    attempts: list[dict[str, Any]] = []
    selected_port: int | None = None
    first_xml: str | None = None

    for remote_port in candidates:
        local_port = create_forward(device, remote_port)
        if local_port is None:
            attempts.append({"remote_port": remote_port, "forwarded": False})
            continue
        try:
            base = f"http://127.0.0.1:{local_port}"
            reachable_paths: list[str] = []
            for path in ("/version", "/status", "/"):
                if http_get(base + path, timeout=args.http_timeout) is not None:
                    reachable_paths.append(path)
            xml = capture_hierarchy(base, timeout=max(2.0, args.http_timeout * 4)) if reachable_paths else None
            attempts.append({
                "remote_port": remote_port,
                "forwarded": True,
                "http_reachable": bool(reachable_paths),
                "reachable_path_count": len(reachable_paths),
                "hierarchy_xml": xml is not None,
            })
            if xml is not None:
                selected_port = remote_port
                first_xml = xml
                break
        finally:
            remove_forward(device, local_port)

    snapshots: list[str] = []
    selectors = []
    if selected_port is not None:
        selected_forward = create_forward(device, selected_port)
        if selected_forward is not None:
            try:
                base = f"http://127.0.0.1:{selected_forward}"
                for index in range(args.samples):
                    xml = first_xml if index == 0 and first_xml is not None else capture_hierarchy(base, timeout=8.0)
                    if xml is None:
                        break
                    snapshots.append(xml)
                    (private / f"ui-{index + 1:02d}.xml").write_text(xml, encoding="utf-8")
                    if index + 1 < args.samples and args.interval:
                        time.sleep(args.interval)
            finally:
                remove_forward(device, selected_forward)

    if len(snapshots) >= 2:
        selectors = learn_selector_candidates(snapshots, package=TIKTOK_PACKAGE)
        (private / "candidates.private.json").write_text(
            json.dumps([item.to_dict() for item in selectors], ensure_ascii=False, indent=2), encoding="utf-8"
        )

    (private / "attempts.private.json").write_text(json.dumps(attempts, indent=2), encoding="utf-8")

    if len(snapshots) >= 2 and selectors:
        status = "SOURCE_AND_SELECTORS_CAPTURED"
        reason = "runtime-derived helper port exposed repeated valid hierarchy XML and stable selectors"
        exit_code = 0
    elif len(snapshots) >= 2:
        status = "SOURCE_CAPTURED_NO_SAFE_SELECTOR"
        reason = "runtime-derived helper port exposed hierarchy XML but no stable selector survived repeated samples"
        exit_code = 1
    elif selected_port is not None:
        status = "HIERARCHY_ENDPOINT_UNSTABLE"
        reason = "a hierarchy endpoint was discovered once but repeated XML capture was not reliable"
        exit_code = 1
    elif any(item.get("http_reachable") for item in attempts):
        status = "HELPER_HTTP_FOUND_NO_HIERARCHY"
        reason = "runtime-derived helper HTTP endpoint(s) were found, but none exposed /dump/hierarchy"
        exit_code = 1
    else:
        status = "NO_RUNTIME_HIERARCHY_ENDPOINT"
        reason = "no runtime-derived Android listener exposed a readable hierarchy endpoint"
        exit_code = 1

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "observed_listener_count": len(evidence["observed_listener_ports"]),
        "helper_process_count": len(evidence["helper_process_lines"]),
        "cmdline_port_hint_count": len(evidence["cmdline_port_hints"]),
        "candidate_port_count": len(candidates),
        "http_endpoint_count": sum(1 for item in attempts if item.get("http_reachable")),
        "hierarchy_port_found": selected_port is not None,
        "selected_remote_port": selected_port,
        "xml_samples": len(snapshots),
        "stable_candidate_count": len(selectors),
        "top_candidate_kind": selectors[0].kind if selectors else None,
        "selector_values_private": True,
        "reason": reason,
        "no_webdriver_session_created": True,
        "app_ui_actions": 0,
    }
    shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("=" * 78)
    print("TIKTOK GENFARMER UI RUNTIME DISCOVERY")
    print("=" * 78)
    print(f"Status:                    {status}")
    print(f"Observed TCP listeners:    {result['observed_listener_count']}")
    print(f"Helper processes:          {result['helper_process_count']}")
    print(f"Command-line port hints:   {result['cmdline_port_hint_count']}")
    print(f"Candidate ports tested:    {result['candidate_port_count']}")
    print(f"HTTP helper endpoints:     {result['http_endpoint_count']}")
    print(f"Hierarchy endpoint found:  {'YES' if selected_port is not None else 'NO'}")
    if selected_port is not None:
        print(f"Hierarchy device port:     {selected_port}")
    print(f"XML samples captured:      {len(snapshots)}")
    print(f"Stable selector candidates:{len(selectors):4d}")
    if selectors:
        for index, candidate in enumerate(selectors[:8], 1):
            print(
                f"Candidate {index:02d}: kind={candidate.kind}, score={candidate.score}, "
                f"unique={'YES' if candidate.unique_in_all else 'NO'}, occurrences={candidate.occurrences}"
            )
    print(f"Reason:                    {reason}")
    print("New WebDriver session:     NO")
    print("App UI actions:            NONE")
    print(f"Private evidence:          {private.relative_to(ROOT)}")
    print(f"Shareable result:          {shareable_path.relative_to(ROOT)}")
    print("=" * 78)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
