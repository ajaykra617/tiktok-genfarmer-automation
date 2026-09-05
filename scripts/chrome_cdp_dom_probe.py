#!/usr/bin/env python3
"""Read-only Chrome DevTools Protocol probe for the qualification fixture.

Purpose:
- avoid guessed screen coordinates;
- obtain exact DOM selectors/XPaths from the live Chrome tab;
- obtain exact element bounding boxes in CSS pixels;
- report browser/device metrics needed for deterministic coordinate mapping if
  GenFarmer's selector/XPath mode cannot operate on Chrome content.

No click, tap, typing, navigation, or GenFarmer mutation is performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

try:
    import websocket  # type: ignore
except ImportError:  # pragma: no cover
    websocket = None

ROOT = Path(__file__).resolve().parents[1]
ELEMENTS = {
    "message": "gf-message",
    "submit": "gf-submit",
    "success": "gf-success",
    "scroll_target": "gf-scroll-target",
}


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


def run(*args: str, timeout: int = 20) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)


def adb(device: str, *args: str, timeout: int = 20) -> str:
    proc = run("adb", "-s", device, *args, timeout=timeout)
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        raise RuntimeError(err or f"adb exited {proc.returncode}")
    return proc.stdout.decode(errors="replace").strip()


def get_json(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def cdp_eval(ws, expression: str, msg_id: int) -> dict:
    ws.send(json.dumps({
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        },
    }))
    while True:
        raw = ws.recv()
        msg = json.loads(raw)
        if msg.get("id") == msg_id:
            if "error" in msg:
                raise RuntimeError(f"CDP Runtime.evaluate error: {msg['error']}")
            result = msg.get("result", {}).get("result", {})
            if result.get("subtype") == "error":
                raise RuntimeError(f"CDP expression failed: {result}")
            return result.get("value") or {}


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Read-only Chrome CDP DOM probe for GF fixture")
    ap.add_argument("--device", default=os.getenv("DEFAULT_DEVICE_ADB"))
    ap.add_argument("--port", type=int, default=9223, help="temporary localhost CDP forward port")
    args = ap.parse_args()
    if not args.device:
        print("ERROR: pass --device or configure DEFAULT_DEVICE_ADB", file=sys.stderr)
        return 2
    if websocket is None:
        print('ERROR: websocket-client is required. Run: python -m pip install -e ".[dev]"', file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"chrome-cdp-dom-probe-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        state = adb(args.device, "get-state")
        if state != "device":
            raise RuntimeError(f"ADB state is {state!r}, expected 'device'")
        wm_size = adb(args.device, "shell", "wm", "size")

        # Refresh this tool-owned forward only. No global adb state is changed.
        run("adb", "-s", args.device, "forward", "--remove", f"tcp:{args.port}", timeout=10)
        proc = run(
            "adb", "-s", args.device, "forward",
            f"tcp:{args.port}", "localabstract:chrome_devtools_remote",
            timeout=10,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace").strip()
            raise RuntimeError(err or "could not create Chrome DevTools adb forward")

        targets = None
        last_exc = None
        for _ in range(10):
            try:
                targets = get_json(f"http://127.0.0.1:{args.port}/json/list")
                break
            except Exception as exc:  # noqa: PERF203
                last_exc = exc
                time.sleep(0.25)
        if not isinstance(targets, list):
            raise RuntimeError(f"Chrome DevTools /json/list unavailable: {last_exc}")

        candidates = [
            t for t in targets
            if isinstance(t, dict)
            and t.get("type") == "page"
            and str(t.get("title", "")) == "GF Browser Qualification"
        ]
        if not candidates:
            pages = [t for t in targets if isinstance(t, dict) and t.get("type") == "page"]
            summary = [{"title": p.get("title"), "url": p.get("url")} for p in pages]
            raise RuntimeError(f"GF Browser Qualification tab not found. Chrome pages: {summary}")

        target = candidates[0]
        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            raise RuntimeError("target has no webSocketDebuggerUrl")
        ws = websocket.create_connection(ws_url, timeout=8, origin=f"http://127.0.0.1:{args.port}")
        try:
            expression = r'''(() => {
              const out = {
                title: document.title,
                url: location.href,
                metrics: {
                  devicePixelRatio: window.devicePixelRatio,
                  innerWidth: window.innerWidth,
                  innerHeight: window.innerHeight,
                  outerWidth: window.outerWidth,
                  outerHeight: window.outerHeight,
                  screenWidth: window.screen.width,
                  screenHeight: window.screen.height,
                  screenAvailWidth: window.screen.availWidth,
                  screenAvailHeight: window.screen.availHeight,
                  screenX: window.screenX,
                  screenY: window.screenY,
                  visualViewport: window.visualViewport ? {
                    offsetLeft: window.visualViewport.offsetLeft,
                    offsetTop: window.visualViewport.offsetTop,
                    pageLeft: window.visualViewport.pageLeft,
                    pageTop: window.visualViewport.pageTop,
                    width: window.visualViewport.width,
                    height: window.visualViewport.height,
                    scale: window.visualViewport.scale
                  } : null
                },
                elements: {}
              };
              const ids = ['gf-message','gf-submit','gf-success','gf-scroll-target'];
              for (const id of ids) {
                const el = document.getElementById(id);
                if (!el) {
                  out.elements[id] = null;
                  continue;
                }
                const r = el.getBoundingClientRect();
                out.elements[id] = {
                  tag: el.tagName,
                  text: (el.innerText || el.value || el.getAttribute('placeholder') || '').slice(0, 120),
                  cssSelector: '#' + id,
                  xpath: '//*[@id="' + id + '"]',
                  rectCssPx: {
                    x: r.x, y: r.y, left: r.left, top: r.top,
                    right: r.right, bottom: r.bottom,
                    width: r.width, height: r.height,
                    centerX: r.left + r.width / 2,
                    centerY: r.top + r.height / 2
                  },
                  displayed: !!(r.width || r.height) && getComputedStyle(el).display !== 'none',
                  disabled: !!el.disabled
                };
              }
              return out;
            })()'''
            result = cdp_eval(ws, expression, 1)
        finally:
            ws.close()

        result["adb"] = {"device": args.device, "state": state, "wm_size": wm_size}
        result["method"] = "Chrome DevTools Protocol via adb forward; read-only Runtime.evaluate"
        result["coordinate_policy"] = (
            "rectCssPx is exact DOM viewport geometry. Do not treat it as Android screen coordinates "
            "until browser chrome/inset mapping is verified. Prefer the reported XPath in GenFarmer first."
        )
        shareable = out_dir / "chrome-cdp-dom-probe.shareable.json"
        shareable.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        print("=" * 78)
        print("CHROME CDP DOM / SELECTOR PROBE")
        print("=" * 78)
        print(f"ADB target: {args.device}")
        print(f"Screen: {wm_size}")
        print(f"Page: {result.get('title')} | {result.get('url')}")
        m = result.get("metrics", {})
        print(
            "Browser metrics: "
            f"inner={m.get('innerWidth')}x{m.get('innerHeight')} css px, "
            f"screen={m.get('screenWidth')}x{m.get('screenHeight')} css px, "
            f"DPR={m.get('devicePixelRatio')}, screenXY=({m.get('screenX')},{m.get('screenY')})"
        )
        print("Exact fixture elements:")
        elements = result.get("elements", {})
        for label, element_id in ELEMENTS.items():
            item = elements.get(element_id)
            if not item:
                print(f" - {label}: NOT FOUND")
                continue
            rect = item.get("rectCssPx", {})
            print(
                f" - {label}: xpath={item.get('xpath')} css={item.get('cssSelector')} "
                f"displayed={item.get('displayed')} "
                f"rect=({rect.get('left')},{rect.get('top')})-({rect.get('right')},{rect.get('bottom')}) "
                f"centerCss=({rect.get('centerX')},{rect.get('centerY')})"
            )
        print("Selector policy: use these exact XPaths in GenFarmer first; no guessed coordinates.")
        print("Coordinate policy: only derive screen coordinates after we verify Chrome viewport-to-screen insets.")
        print(f"Shareable result: {shareable.relative_to(ROOT)}")
        print("Read-only: no click, tap, typing, navigation, or GenFarmer mutation was performed.")
        print("=" * 78)
        return 0
    except FileNotFoundError:
        print("ERROR: adb not found in PATH", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            run("adb", "-s", args.device, "forward", "--remove", f"tcp:{args.port}", timeout=10)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
