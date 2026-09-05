#!/usr/bin/env python3
"""Read-only ADB/UIAutomator probe for the Chrome qualification fixture.

Captures the current Device #1 UI hierarchy and screenshot, then reports only
fixture-related nodes such as the qualification label, input hint, submit button,
and success/scroll markers. No taps, typing, or app state changes are performed.
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
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TARGET_TERMS = (
    "GF Browser Qualification",
    "Qualification message",
    "Type GENFARMER-OK",
    "Submit qualification",
    "SUCCESS",
    "Scroll target",
)


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


def adb(device: str, *args: str, timeout: int = 30, binary: bool = False):
    proc = subprocess.run(
        ["adb", "-s", device, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        raise RuntimeError(err or f"adb exited {proc.returncode}")
    return proc.stdout if binary else proc.stdout.decode(errors="replace").strip()


def dump_ui(device: str) -> str:
    remote = "/sdcard/window_dump_gf_chrome_fixture.xml"
    adb(device, "shell", "uiautomator", "dump", remote, timeout=30)
    xml = adb(device, "exec-out", "cat", remote, timeout=15)
    try:
        adb(device, "shell", "rm", "-f", remote, timeout=10)
    except Exception:
        pass
    start = xml.find("<?xml")
    if start < 0:
        start = xml.find("<hierarchy")
    if start < 0:
        raise RuntimeError("Could not locate UI hierarchy XML")
    return xml[start:]


def center(bounds: str) -> tuple[int, int] | None:
    nums = [int(x) for x in re.findall(r"\d+", bounds)]
    if len(nums) != 4:
        return None
    x1, y1, x2, y2 = nums
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def safe_node(node: ET.Element) -> dict[str, object]:
    text = (node.attrib.get("text") or "").strip()
    desc = (node.attrib.get("content-desc") or "").strip()
    bounds = node.attrib.get("bounds", "")
    return {
        "text": text,
        "content_desc": desc,
        "resource_id": node.attrib.get("resource-id", ""),
        "class": node.attrib.get("class", ""),
        "clickable": node.attrib.get("clickable", ""),
        "focusable": node.attrib.get("focusable", ""),
        "bounds": bounds,
        "center": center(bounds),
    }


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Read-only UIAutomator probe for Chrome qualification fixture")
    ap.add_argument("--device", default=os.getenv("DEFAULT_DEVICE_ADB"), help="ADB target; defaults to DEFAULT_DEVICE_ADB")
    args = ap.parse_args()
    if not args.device:
        print("ERROR: pass --device or configure DEFAULT_DEVICE_ADB", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"chrome-fixture-ui-probe-{stamp}"
    private_dir = out_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)

    try:
        state = adb(args.device, "get-state")
        if state != "device":
            raise RuntimeError(f"ADB state is {state!r}, expected 'device'")
        wm_size = adb(args.device, "shell", "wm", "size")
        activity = adb(args.device, "shell", "dumpsys", "window", "windows", timeout=20)
        xml = dump_ui(args.device)
        screenshot = adb(args.device, "exec-out", "screencap", "-p", binary=True)
    except FileNotFoundError:
        print("ERROR: adb not found in PATH", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    (private_dir / "window.xml").write_text(xml, encoding="utf-8")
    (private_dir / "screen.png").write_bytes(screenshot)

    root = ET.fromstring(xml)
    matches: list[dict[str, object]] = []
    all_webish: list[dict[str, object]] = []
    for node in root.iter("node"):
        item = safe_node(node)
        hay = f"{item['text']} {item['content_desc']}".strip().lower()
        if any(term.lower() in hay for term in TARGET_TERMS):
            matches.append(item)
        cls = str(item["class"])
        if cls in {"android.webkit.WebView", "android.widget.EditText", "android.widget.Button"}:
            all_webish.append(item)

    current_activity = None
    for line in activity.splitlines():
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            if "com.android.chrome" in line:
                current_activity = line.strip()
                break

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "device": args.device,
        "state": state,
        "wm_size": wm_size,
        "chrome_focused": bool(current_activity),
        "fixture_match_count": len(matches),
        "fixture_matches": matches,
        "webish_node_count": len(all_webish),
        "webish_nodes": all_webish,
        "privacy": "fixture-only UI hierarchy report; raw XML/screenshot remain under ignored private evidence",
    }
    shareable = out_dir / "chrome-fixture-ui-probe.shareable.json"
    shareable.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("CHROME FIXTURE UIAUTOMATOR PROBE")
    print("=" * 78)
    print(f"ADB target: {args.device}")
    print(f"State: {state}")
    print(f"Screen: {wm_size}")
    print(f"Chrome focused: {'YES' if current_activity else 'NO/UNKNOWN'}")
    print(f"Fixture matches: {len(matches)}")
    for item in matches:
        label = item['text'] or item['content_desc'] or '<unlabeled>'
        print(
            f" - {label!r} class={item['class']} clickable={item['clickable']} "
            f"focusable={item['focusable']} bounds={item['bounds']} center={item['center']}"
        )
    print(f"Web/EditText/Button nodes: {len(all_webish)}")
    for item in all_webish:
        label = item['text'] or item['content_desc'] or '<unlabeled>'
        print(
            f" - {label!r} class={item['class']} clickable={item['clickable']} "
            f"focusable={item['focusable']} bounds={item['bounds']} center={item['center']}"
        )
    if matches:
        print("Selector strategy: UIAutomator sees fixture content; prefer selector/XPath where stable, coordinates as fallback.")
    else:
        print("Selector strategy: fixture content not exposed in UIAutomator dump; use coordinates first for this Chrome qualification.")
    print(f"Private evidence: {private_dir.relative_to(ROOT)}")
    print(f"Shareable result: {shareable.relative_to(ROOT)}")
    print("Read-only: no tap, typing, launch, or setting change was performed.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
