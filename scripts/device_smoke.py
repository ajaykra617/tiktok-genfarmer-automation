#!/usr/bin/env python3
"""Safe single-device Android smoke test.

The test launches Android Settings, captures evidence, reads the UI hierarchy,
optionally performs one read-only navigation tap (About phone/System), returns
Home, and writes a JSON result. It does not install apps, modify accounts, or
change network settings.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


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


def get_prop(device: str, name: str) -> str:
    return adb(device, "shell", "getprop", name).strip()


def capture_png(device: str, path: Path) -> None:
    path.write_bytes(adb(device, "exec-out", "screencap", "-p", binary=True))


def dump_ui(device: str) -> str:
    remote = "/sdcard/window_dump_genfarmer.xml"
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


def nodes_from_xml(xml: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml)
    nodes: list[dict[str, str]] = []
    for node in root.iter("node"):
        text = (node.attrib.get("text") or "").strip()
        desc = (node.attrib.get("content-desc") or "").strip()
        if text or desc:
            nodes.append(
                {
                    "text": text,
                    "description": desc,
                    "resource_id": node.attrib.get("resource-id", ""),
                    "class": node.attrib.get("class", ""),
                    "clickable": node.attrib.get("clickable", ""),
                    "bounds": node.attrib.get("bounds", ""),
                }
            )
    return nodes


def bounds_center(bounds: str) -> tuple[int, int] | None:
    values = [int(x) for x in re.findall(r"\d+", bounds)]
    if len(values) != 4:
        return None
    x1, y1, x2, y2 = values
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def safe_navigation(device: str, nodes: list[dict[str, str]]) -> dict | None:
    # Deliberately limited to read-only Settings destinations.
    priorities = ("about phone", "device information", "my phone", "system")
    for wanted in priorities:
        for node in nodes:
            label = f"{node['text']} {node['description']}".strip().lower()
            if wanted not in label:
                continue
            center = bounds_center(node["bounds"])
            if not center:
                continue
            x, y = center
            adb(device, "shell", "input", "tap", str(x), str(y))
            return {"matched": wanted, "label": label, "x": x, "y": y}
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe Android device smoke test")
    parser.add_argument("--device", required=True, help="ADB device ID, e.g. HOST:5555")
    parser.add_argument("--evidence-dir", default="evidence", help="Evidence root")
    parser.add_argument(
        "--no-navigation",
        action="store_true",
        help="Launch/read Settings only; do not perform the optional safe tap",
    )
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = Path(args.evidence_dir) / f"smoke-{safe_device}-{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "timestamp_utc": stamp,
        "device": args.device,
        "workflow": "android-settings-smoke",
        "success": False,
        "evidence_dir": str(out),
    }

    print("=" * 64)
    print("SAFE ANDROID DEVICE SMOKE TEST")
    print("=" * 64)
    print(f"Device: {args.device}")
    print(f"Evidence: {out}")

    try:
        state = adb(args.device, "get-state")
        if state != "device":
            raise RuntimeError(f"ADB state is {state!r}, expected 'device'")

        result["device_info"] = {
            "manufacturer": get_prop(args.device, "ro.product.manufacturer"),
            "model": get_prop(args.device, "ro.product.model"),
            "android": get_prop(args.device, "ro.build.version.release"),
            "sdk": get_prop(args.device, "ro.build.version.sdk"),
        }
        print("ADB state: device")
        print("Device info:", result["device_info"])

        adb(args.device, "shell", "am", "start", "-a", "android.settings.SETTINGS")
        time.sleep(2.5)

        before_png = out / "settings-before.png"
        before_xml = out / "settings-before.xml"
        capture_png(args.device, before_png)
        xml = dump_ui(args.device)
        before_xml.write_text(xml, encoding="utf-8")
        nodes = nodes_from_xml(xml)

        print(f"Visible labeled UI nodes: {len(nodes)}")
        for node in nodes[:20]:
            print(" -", node["text"] or node["description"])

        action = None
        if not args.no_navigation:
            action = safe_navigation(args.device, nodes)
            if action:
                print(f"Safe navigation: {action['label']!r}")
                time.sleep(1.5)
                after_png = out / "settings-after.png"
                after_xml = out / "settings-after.xml"
                capture_png(args.device, after_png)
                after_xml.write_text(dump_ui(args.device), encoding="utf-8")
            else:
                print("No known read-only navigation target found; launch verification still passes.")

        adb(args.device, "shell", "input", "keyevent", "KEYCODE_HOME")
        time.sleep(0.8)
        capture_png(args.device, out / "home-final.png")

        result["semantic_action"] = action
        result["success"] = True
        print("SMOKE TEST PASSED")
        return_code = 0

    except FileNotFoundError:
        result["error"] = "adb was not found in PATH"
        print("ERROR: adb was not found in PATH", file=sys.stderr)
        return_code = 2
    except Exception as exc:
        result["error"] = str(exc)
        print(f"SMOKE TEST FAILED: {exc}", file=sys.stderr)
        return_code = 1
    finally:
        (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Result: {out / 'result.json'}")

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
