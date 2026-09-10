#!/usr/bin/env python3
"""Read-only probe for an existing GenFarmer/Appium UI hierarchy channel.

Why this exists: Android's standalone ``uiautomator dump`` can exit 137 while
another automation client already owns the UiAutomation channel.  Instead of
killing that client or creating a competing session, this probe checks whether
an *already-running* Appium/UiAutomator2-compatible server/session can provide
``/source``.

The probe may create one temporary ADB TCP forward to device port 6790 and
removes it before exit.  It never creates a WebDriver session, taps, swipes,
installs software, stops GenFarmer, or changes TikTok state.
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
from typing import Any
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_observer import AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.ui_source_bridge import (  # noqa: E402
    appium_base_candidates,
    extract_session_ids,
    extract_source_xml,
    session_source_paths,
)
from genfarmer_automation.ui_xml import UiXmlError, parse_ui_xml  # noqa: E402

REMOTE_UIA2_PORT = 6790
HELPER_RE = re.compile(r"(?i)(appium|uiautomator|atx|genfarmer|minicap|minitouch)")


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


def adb(device: str | None, *args: str, timeout: float = 10.0) -> subprocess.CompletedProcess[bytes]:
    command = ["adb"]
    if device:
        command.extend(["-s", device])
    command.extend(args)
    try:
        return subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("adb was not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"adb command timed out after {timeout}s: {' '.join(args)}") from exc


def text(proc: subprocess.CompletedProcess[bytes]) -> str:
    return proc.stdout.decode("utf-8", errors="replace").strip()


def list_forwards() -> list[dict[str, str]]:
    proc = adb(None, "forward", "--list")
    if proc.returncode != 0:
        return []
    out: list[dict[str, str]] = []
    for line in text(proc).splitlines():
        parts = line.split()
        if len(parts) == 3:
            out.append({"serial": parts[0], "local": parts[1], "remote": parts[2]})
    return out


def local_tcp_port(spec: str) -> int | None:
    if not spec.startswith("tcp:"):
        return None
    value = spec[4:]
    return int(value) if value.isdigit() and 1 <= int(value) <= 65535 else None


def http_get(url: str, timeout: float = 2.5) -> tuple[int, Any] | None:
    request = urllib.request.Request(url, headers={"User-Agent": "genfarmer-automation-ui-source-probe/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = int(response.status)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None
    raw = body.decode("utf-8", errors="replace").strip()
    if not raw:
        return status, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def helper_diagnostics(device: str) -> dict[str, Any]:
    packages_proc = adb(device, "shell", "pm", "list", "packages", timeout=12.0)
    ps_proc = adb(device, "shell", "ps", "-A", timeout=12.0)
    packages = [line.strip() for line in text(packages_proc).splitlines() if HELPER_RE.search(line)]
    processes = [line.strip() for line in text(ps_proc).splitlines() if HELPER_RE.search(line)]
    return {
        "helper_package_lines": packages,
        "helper_process_lines": processes,
        "target_forwards": [item for item in list_forwards() if item.get("serial") == device],
    }


def create_temp_forward(device: str) -> int | None:
    proc = adb(device, "forward", "tcp:0", f"tcp:{REMOTE_UIA2_PORT}")
    if proc.returncode != 0:
        return None
    value = text(proc).strip()
    return int(value) if value.isdigit() and 1 <= int(value) <= 65535 else None


def remove_temp_forward(device: str, port: int) -> None:
    adb(device, "forward", "--remove", f"tcp:{port}", timeout=5.0)


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe an existing UiAutomator2/Appium session for read-only UI source")
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB")
    ap.add_argument("--no-temp-forward", action="store_true", help="do not create a temporary tcp forward to device port 6790")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not device:
        print("ERROR: configure DEFAULT_DEVICE_ADB or pass --device", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
    out = ROOT / "evidence" / f"tiktok-ui-source-bridge-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable_path = out / "tiktok-ui-source-bridge.shareable.json"

    temp_port: int | None = None
    result: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "STARTED",
        "existing_session_only": True,
        "new_webdriver_session_created": False,
        "temporary_forward_created": False,
        "endpoint_reachable": False,
        "existing_session_count": 0,
        "xml_captured": False,
    }

    try:
        observation = AdbObserver(device).observe()
        if observation.adb_state != "device" or not observation.tiktok_foreground or observation.interrupt is not InterruptKind.NONE:
            raise RuntimeError("TikTok foreground/no-interrupt precondition not proven")

        diagnostics = helper_diagnostics(device)
        (private / "helper-diagnostics.private.json").write_text(
            json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        result["helper_package_candidates"] = len(diagnostics["helper_package_lines"])
        result["helper_process_candidates"] = len(diagnostics["helper_process_lines"])

        ports: list[int] = []
        for item in diagnostics["target_forwards"]:
            if item.get("remote") != f"tcp:{REMOTE_UIA2_PORT}":
                continue
            port = local_tcp_port(item.get("local", ""))
            if port is not None and port not in ports:
                ports.append(port)

        if not ports and not args.no_temp_forward:
            temp_port = create_temp_forward(device)
            if temp_port is not None:
                ports.append(temp_port)
                result["temporary_forward_created"] = True

        attempts: list[dict[str, Any]] = []
        captured_xml: str | None = None
        captured_base: str | None = None
        all_session_ids: list[str] = []

        for port in ports:
            for base in appium_base_candidates(port):
                status_response = http_get(base + "/status")
                attempt: dict[str, Any] = {
                    "port": port,
                    "base_suffix": "/wd/hub" if base.endswith("/wd/hub") else "/",
                    "status_reachable": status_response is not None,
                    "sessions_reachable": False,
                    "session_count": 0,
                    "source_success": False,
                }
                if status_response is None:
                    attempts.append(attempt)
                    continue
                result["endpoint_reachable"] = True
                status_payload = status_response[1]
                session_ids = list(extract_session_ids(status_payload))

                sessions_response = http_get(base + "/sessions")
                if sessions_response is not None:
                    attempt["sessions_reachable"] = True
                    for sid in extract_session_ids(sessions_response[1]):
                        if sid not in session_ids:
                            session_ids.append(sid)
                attempt["session_count"] = len(session_ids)
                for sid in session_ids:
                    if sid not in all_session_ids:
                        all_session_ids.append(sid)

                for source_url in session_source_paths(base, session_ids):
                    source_response = http_get(source_url, timeout=4.0)
                    if source_response is None:
                        continue
                    xml = extract_source_xml(source_response[1])
                    if xml is None:
                        continue
                    try:
                        parse_ui_xml(xml)
                    except UiXmlError:
                        continue
                    captured_xml = xml
                    captured_base = attempt["base_suffix"]
                    attempt["source_success"] = True
                    break
                attempts.append(attempt)
                if captured_xml is not None:
                    break
            if captured_xml is not None:
                break

        result["existing_session_count"] = len(all_session_ids)
        result["attempt_count"] = len(attempts)
        result["source_base_suffix"] = captured_base
        (private / "endpoint-attempts.private.json").write_text(
            json.dumps(attempts, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if captured_xml is not None:
            (private / "ui-source.xml").write_text(captured_xml, encoding="utf-8")
            root = parse_ui_xml(captured_xml)
            node_count = sum(1 for _ in root.iter("node"))
            result["xml_captured"] = True
            result["xml_node_count"] = node_count
            result["status"] = "SOURCE_CAPTURED"
            result["reason"] = "reused an existing automation session to read UI hierarchy without starting a competing session"
            exit_code = 0
        elif result["endpoint_reachable"]:
            result["status"] = "EXISTING_SERVER_NO_SOURCE"
            result["reason"] = "an Appium/UiAutomator2-compatible endpoint was reachable, but no existing session exposed valid UI XML"
            exit_code = 1
        else:
            result["status"] = "NO_EXISTING_UIA2_ENDPOINT"
            result["reason"] = "no existing UiAutomator2/Appium endpoint was reachable on device port 6790; inspect GenFarmer packaged implementation next"
            exit_code = 1

        shareable = {
            key: value for key, value in result.items()
            if key not in {"device", "session_ids"}
        }
        shareable_path.write_text(json.dumps(shareable, indent=2), encoding="utf-8")

        print("=" * 78)
        print("TIKTOK EXISTING UI-SOURCE BRIDGE PROBE")
        print("=" * 78)
        print(f"Status:                    {result['status']}")
        print(f"UiAutomator2 endpoint:     {'YES' if result['endpoint_reachable'] else 'NO'}")
        print(f"Existing sessions found:   {result['existing_session_count']}")
        print(f"Valid XML captured:        {'YES' if result['xml_captured'] else 'NO'}")
        if result.get("xml_node_count") is not None:
            print(f"XML node count:             {result['xml_node_count']}")
        print(f"Helper package candidates: {result.get('helper_package_candidates', 0)}")
        print(f"Helper process candidates: {result.get('helper_process_candidates', 0)}")
        print(f"Temporary ADB forward:     {'YES (removed on exit)' if result['temporary_forward_created'] else 'NO'}")
        print("New WebDriver session:     NO")
        print(f"Reason:                    {result['reason']}")
        print(f"Private evidence:          {private.relative_to(ROOT)}")
        print(f"Shareable result:          {shareable_path.relative_to(ROOT)}")
        print("=" * 78)
        return exit_code
    except (RuntimeError, OSError, ValueError) as exc:
        result["status"] = "ERROR"
        result["reason"] = str(exc)
        shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if temp_port is not None:
            remove_temp_forward(device, temp_port)


if __name__ == "__main__":
    raise SystemExit(main())
