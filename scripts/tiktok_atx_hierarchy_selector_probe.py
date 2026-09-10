#!/usr/bin/env python3
"""Reuse GenFarmer's existing atx-agent path to learn stable TikTok selectors.

The standalone Android ``uiautomator dump`` path is known to exit 137 on the
current lab device while GenFarmer's own packaged implementation contains
openatx/UiAutomator2 support.  This probe therefore forwards the existing
atx-agent device port, reads ``/version`` and ``/dump/hierarchy``, validates the
returned XML, and runs the same conservative selector learner used elsewhere.

It does not install helpers, create a WebDriver session, tap, swipe, or stop
GenFarmer.  Exact XML and XPath values are written only below ignored private
evidence.
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
from genfarmer_automation.atx_bridge import (  # noqa: E402
    atx_base_url,
    extract_atx_hierarchy_xml,
    extract_atx_version,
)
from genfarmer_automation.ui_xml import (  # noqa: E402
    UiXmlError,
    learn_selector_candidates,
    parse_ui_xml,
)

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"
DEFAULT_REMOTE_PORT = 7912


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


def create_forward(device: str, remote_port: int) -> int:
    proc = adb(device, "forward", "tcp:0", f"tcp:{remote_port}")
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or f"could not forward device tcp:{remote_port}")
    value = proc_text(proc)
    if not value.isdigit() or not (1 <= int(value) <= 65535):
        raise RuntimeError(f"adb returned an invalid local forward port: {value!r}")
    return int(value)


def remove_forward(device: str, local_port: int) -> None:
    adb(device, "forward", "--remove", f"tcp:{local_port}", timeout=5.0)


def http_get(url: str, timeout: float = 12.0) -> tuple[int, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": "genfarmer-automation-atx-probe/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            status = int(response.status)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return status, None
    try:
        return status, json.loads(text)
    except json.JSONDecodeError:
        return status, text


def main() -> int:
    ap = argparse.ArgumentParser(description="Read hierarchy through an existing atx-agent and learn stable TikTok selectors")
    ap.add_argument("--device", help="ADB target; defaults to DEFAULT_DEVICE_ADB")
    ap.add_argument("--remote-port", type=int, default=DEFAULT_REMOTE_PORT)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--interval", type=float, default=0.4)
    ap.add_argument("--include-text", action="store_true")
    args = ap.parse_args()

    if not 1 <= args.remote_port <= 65535:
        print("ERROR: --remote-port must be 1..65535", file=sys.stderr)
        return 2
    if not 2 <= args.samples <= 8:
        print("ERROR: --samples must be 2..8", file=sys.stderr)
        return 2
    if args.interval < 0:
        print("ERROR: --interval must be non-negative", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    device = args.device or os.getenv("DEFAULT_DEVICE_ADB")
    if not device:
        print("ERROR: configure DEFAULT_DEVICE_ADB or pass --device", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", device)
    out = ROOT / "evidence" / f"tiktok-atx-hierarchy-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable_path = out / "tiktok-atx-hierarchy.shareable.json"

    local_port: int | None = None
    result: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "remote_port": args.remote_port,
        "status": "STARTED",
        "atx_agent_reachable": False,
        "xml_captured": False,
        "samples": 0,
        "selector_values_private": True,
        "new_webdriver_session_created": False,
    }

    try:
        observation = AdbObserver(device).observe()
        if observation.adb_state != "device" or not observation.tiktok_foreground or observation.interrupt is not InterruptKind.NONE:
            raise RuntimeError("TikTok foreground/no-interrupt precondition not proven")

        local_port = create_forward(device, args.remote_port)
        base = atx_base_url(local_port)

        version_response = http_get(base + "/version", timeout=3.0)
        if version_response is None:
            result["status"] = "ATX_AGENT_NOT_REACHABLE"
            result["reason"] = f"no HTTP response from existing helper on device tcp:{args.remote_port}"
            raise RuntimeError(result["reason"])

        result["atx_agent_reachable"] = True
        version = extract_atx_version(version_response[1])
        result["version_present"] = version is not None
        if version is not None:
            (private / "version.private.txt").write_text(version, encoding="utf-8")

        snapshots: list[str] = []
        for index in range(args.samples):
            hierarchy_response = http_get(base + "/dump/hierarchy", timeout=15.0)
            if hierarchy_response is None:
                result["status"] = "ATX_AGENT_NO_HIERARCHY"
                result["reason"] = "atx-agent was reachable but /dump/hierarchy did not return a usable response"
                raise RuntimeError(result["reason"])
            xml = extract_atx_hierarchy_xml(hierarchy_response[1])
            if xml is None:
                result["status"] = "ATX_AGENT_NO_HIERARCHY"
                result["reason"] = "atx-agent /dump/hierarchy response did not contain XML"
                raise RuntimeError(result["reason"])
            parse_ui_xml(xml)
            snapshots.append(xml)
            (private / f"ui-{index + 1:02d}.xml").write_text(xml, encoding="utf-8")
            if index + 1 < args.samples and args.interval:
                time.sleep(args.interval)

        result["xml_captured"] = True
        result["samples"] = len(snapshots)
        node_counts = [sum(1 for _ in parse_ui_xml(xml).iter("node")) for xml in snapshots]
        result["node_counts"] = node_counts

        candidates = learn_selector_candidates(
            snapshots,
            package=TIKTOK_PACKAGE,
            include_text=args.include_text,
        )
        (private / "candidates.private.json").write_text(
            json.dumps([item.to_dict() for item in candidates], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["candidate_count"] = len(candidates)
        result["top_candidate_kind"] = candidates[0].kind if candidates else None
        result["top_candidate_unique_in_all"] = candidates[0].unique_in_all if candidates else False
        result["top_candidate_score"] = candidates[0].score if candidates else None

        if candidates:
            result["status"] = "SOURCE_AND_SELECTORS_CAPTURED"
            result["reason"] = "existing atx-agent returned valid repeated hierarchy XML and stable selector candidates were learned"
            exit_code = 0
        else:
            result["status"] = "SOURCE_CAPTURED_NO_SAFE_SELECTOR"
            result["reason"] = "hierarchy XML was captured but no stable resource-id/content-desc selector survived the repeated samples"
            exit_code = 1

        shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("=" * 78)
        print("TIKTOK ATX-AGENT HIERARCHY / SELECTOR PROBE")
        print("=" * 78)
        print(f"Status:                   {result['status']}")
        print(f"atx-agent reachable:      {'YES' if result['atx_agent_reachable'] else 'NO'}")
        print(f"Version response present: {'YES' if result.get('version_present') else 'NO'}")
        print(f"XML samples captured:     {result['samples']}")
        print(f"XML node counts:          {', '.join(map(str, result.get('node_counts', []))) or '<none>'}")
        print(f"Stable candidates:        {result.get('candidate_count', 0)}")
        for index, candidate in enumerate(candidates[:10], 1):
            print(
                f"Candidate {index:02d}: kind={candidate.kind}, score={candidate.score}, "
                f"unique={'YES' if candidate.unique_in_all else 'NO'}, occurrences={candidate.occurrences}"
            )
        print("New WebDriver session:    NO")
        print("App UI actions:           NONE")
        print(f"Reason:                   {result['reason']}")
        print(f"Private XML/candidates:   {private.relative_to(ROOT)}")
        print(f"Shareable result:         {shareable_path.relative_to(ROOT)}")
        print("=" * 78)
        return exit_code

    except (RuntimeError, UiXmlError, OSError, ValueError) as exc:
        if result.get("status") == "STARTED":
            result["status"] = "ERROR"
            result["reason"] = str(exc)
        shareable_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("=" * 78)
        print("TIKTOK ATX-AGENT HIERARCHY / SELECTOR PROBE")
        print("=" * 78)
        print(f"Status: {result.get('status')}")
        print(f"Reason: {result.get('reason', str(exc))}")
        print("No WebDriver session, tap, swipe, install, or GenFarmer stop was attempted.")
        print(f"Shareable result: {shareable_path.relative_to(ROOT)}")
        print("=" * 78)
        return 1
    finally:
        if local_port is not None:
            remove_forward(device, local_port)


if __name__ == "__main__":
    raise SystemExit(main())
