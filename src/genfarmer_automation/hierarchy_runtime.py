"""Resilient Android hierarchy capture for TikTok supervision.

The preferred source is GenFarmer's already-running openatx/UiAutomator helper.
A port is treated only as a hint: it is probed quickly and, if stale or wedged,
runtime listener evidence is scanned for another working hierarchy endpoint.

If no helper endpoint is healthy, the module falls back to a bounded standard
``adb shell uiautomator dump`` capture.  The fallback creates one temporary XML
file under /data/local/tmp and deletes it immediately after reading it.  It does
not tap, swipe, install packages, start a WebDriver session, or alter app data.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
import time
from typing import Any
import urllib.error
import urllib.request

from .android_listener_discovery import (
    parse_proc_net_tcp,
    parse_ss_listeners,
    prioritized_candidate_ports,
)
from .atx_bridge import extract_atx_hierarchy_xml
from .ui_xml import UiXmlError, parse_ui_xml


class HierarchyRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class HierarchyBatch:
    snapshots: tuple[str, ...]
    provider: str
    remote_port: int | None
    attempts: tuple[str, ...]


def _adb(device: str, *args: str, timeout: float = 8.0) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["adb", "-s", device, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HierarchyRuntimeError("adb was not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise HierarchyRuntimeError(f"adb command timed out after {timeout:.1f}s") from exc


def _text(proc: subprocess.CompletedProcess[bytes]) -> str:
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _create_forward(device: str, remote_port: int) -> int:
    proc = _adb(device, "forward", "tcp:0", f"tcp:{remote_port}", timeout=5.0)
    if proc.returncode != 0:
        raise HierarchyRuntimeError("could not create temporary hierarchy ADB forward")
    value = _text(proc)
    if not value.isdigit():
        raise HierarchyRuntimeError("ADB did not return a local forward port")
    port = int(value)
    if not 1 <= port <= 65535:
        raise HierarchyRuntimeError("ADB returned an invalid local forward port")
    return port


def _remove_forward(device: str, local_port: int) -> None:
    try:
        _adb(device, "forward", "--remove", f"tcp:{local_port}", timeout=3.0)
    except Exception:
        pass


def _http_hierarchy(local_port: int, *, timeout: float) -> str:
    req = urllib.request.Request(
        f"http://127.0.0.1:{local_port}/dump/hierarchy",
        headers={"User-Agent": "tiktok-hierarchy-runtime/1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace").strip()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HierarchyRuntimeError(f"helper hierarchy request failed: {exc}") from exc

    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        payload = raw
    xml = extract_atx_hierarchy_xml(payload)
    if xml is None:
        raise HierarchyRuntimeError("helper response did not contain hierarchy XML")
    try:
        parse_ui_xml(xml)
    except UiXmlError as exc:
        raise HierarchyRuntimeError(f"helper returned invalid hierarchy XML: {exc}") from exc
    return xml


def _capture_helper_once(device: str, remote_port: int, *, timeout: float) -> str:
    local_port = _create_forward(device, remote_port)
    try:
        return _http_hierarchy(local_port, timeout=timeout)
    finally:
        _remove_forward(device, local_port)


def runtime_listener_ports(device: str) -> tuple[int, ...]:
    observed: list[int] = []
    commands = (
        ("shell", "ss", "-ltn"),
        ("shell", "cat", "/proc/net/tcp"),
        ("shell", "cat", "/proc/net/tcp6"),
    )
    for index, command in enumerate(commands):
        try:
            proc = _adb(device, *command, timeout=5.0)
        except HierarchyRuntimeError:
            continue
        if proc.returncode != 0:
            continue
        text = _text(proc)
        values = parse_ss_listeners(text) if index == 0 else parse_proc_net_tcp(text)
        for port in values:
            if port not in observed:
                observed.append(port)
    return tuple(observed)


def candidate_ports(device: str, preferred_port: int | None, *, max_ports: int = 16) -> tuple[int, ...]:
    observed = runtime_listener_ports(device)
    preferred: tuple[int, ...] = ()
    if preferred_port is not None and 1 <= preferred_port <= 65535:
        preferred = (preferred_port,)
    common = (*preferred, 8912, 7912, 7913, 9008, 6790)
    return prioritized_candidate_ports(
        observed,
        preferred,
        common_hints=common,
        max_ports=max_ports,
    )


def discover_helper_port(
    device: str,
    *,
    preferred_port: int | None = None,
    probe_timeout: float = 1.5,
    max_ports: int = 16,
) -> tuple[int | None, tuple[str, ...]]:
    attempts: list[str] = []
    for port in candidate_ports(device, preferred_port, max_ports=max_ports):
        try:
            _capture_helper_once(device, port, timeout=probe_timeout)
        except HierarchyRuntimeError as exc:
            attempts.append(f"helper:{port}:fail:{type(exc).__name__}")
            continue
        attempts.append(f"helper:{port}:pass")
        return port, tuple(attempts)
    return None, tuple(attempts)


def _extract_embedded_xml(text: str) -> str | None:
    if not text:
        return None
    starts = []
    for marker in ("<?xml", "<hierarchy"):
        idx = text.find(marker)
        if idx >= 0:
            starts.append(idx)
    if not starts:
        return None
    start = min(starts)
    end_marker = "</hierarchy>"
    end = text.rfind(end_marker)
    if end < start:
        return None
    xml = text[start : end + len(end_marker)].strip()
    try:
        parse_ui_xml(xml)
    except UiXmlError:
        return None
    return xml


def capture_uiautomator_once(device: str, *, timeout: float = 12.0) -> str:
    try:
        proc = _adb(device, "exec-out", "uiautomator", "dump", "/dev/tty", timeout=timeout)
        combined = (
            proc.stdout.decode("utf-8", errors="replace")
            + "\n"
            + proc.stderr.decode("utf-8", errors="replace")
        )
        xml = _extract_embedded_xml(combined)
        if proc.returncode == 0 and xml is not None:
            return xml
    except HierarchyRuntimeError:
        pass

    remote = "/data/local/tmp/gf_window_dump.xml"
    try:
        _adb(device, "shell", "rm", "-f", remote, timeout=3.0)
        proc = _adb(device, "shell", "uiautomator", "dump", remote, timeout=timeout)
        if proc.returncode != 0:
            raise HierarchyRuntimeError("uiautomator dump failed")
        cat = _adb(device, "exec-out", "cat", remote, timeout=5.0)
        if cat.returncode != 0:
            raise HierarchyRuntimeError("could not read uiautomator dump")
        xml = _extract_embedded_xml(cat.stdout.decode("utf-8", errors="replace"))
        if xml is None:
            raise HierarchyRuntimeError("uiautomator dump did not contain valid hierarchy XML")
        return xml
    finally:
        try:
            _adb(device, "shell", "rm", "-f", remote, timeout=3.0)
        except Exception:
            pass


def capture_hierarchy_batch(
    device: str,
    *,
    count: int = 2,
    interval: float = 0.25,
    preferred_port: int | None = None,
    helper_timeout: float = 2.0,
    max_ports: int = 16,
) -> HierarchyBatch:
    if not 1 <= count <= 8:
        raise ValueError("count must be 1..8")
    if interval < 0:
        raise ValueError("interval must be >= 0")

    attempts: list[str] = []
    port, discovery_attempts = discover_helper_port(
        device,
        preferred_port=preferred_port,
        probe_timeout=min(helper_timeout, 1.5),
        max_ports=max_ports,
    )
    attempts.extend(discovery_attempts)

    if port is not None:
        snapshots: list[str] = []
        helper_ok = True
        for index in range(count):
            try:
                snapshots.append(_capture_helper_once(device, port, timeout=helper_timeout))
            except HierarchyRuntimeError as exc:
                attempts.append(f"helper:{port}:sample-{index + 1}:fail:{type(exc).__name__}")
                helper_ok = False
                break
            if index + 1 < count and interval:
                time.sleep(interval)
        if helper_ok and len(snapshots) == count:
            return HierarchyBatch(tuple(snapshots), "genfarmer-helper", port, tuple(attempts))

    snapshots = []
    for index in range(count):
        last_error: Exception | None = None
        for retry in range(2):
            try:
                snapshots.append(capture_uiautomator_once(device))
                attempts.append(f"uiautomator:sample-{index + 1}:pass")
                last_error = None
                break
            except HierarchyRuntimeError as exc:
                last_error = exc
                attempts.append(f"uiautomator:sample-{index + 1}:retry-{retry + 1}:fail")
                if retry == 0:
                    time.sleep(0.35)
        if last_error is not None:
            raise HierarchyRuntimeError(
                "no healthy hierarchy source: helper endpoint unavailable and uiautomator fallback failed"
            ) from last_error
        if index + 1 < count and interval:
            time.sleep(interval)

    return HierarchyBatch(tuple(snapshots), "adb-uiautomator", None, tuple(attempts))
