#!/usr/bin/env python3
"""Tiny local browser fixture for GenFarmer Chrome qualification.

Serves a deterministic page over the LAN with stable element IDs and no
external dependencies. The page includes a text input, button, success marker,
and a tall scroll region so GenFarmer Touch/TypeText/Press/Swipe/Screenshot
flows can be qualified without relying on third-party websites.
"""
from __future__ import annotations

import argparse
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
  <title>GF Browser Qualification</title>
  <style>
    body { font-family: sans-serif; margin: 0; padding: 20px; background: #fff; color: #111; }
    h1 { font-size: 28px; margin: 0 0 18px; }
    .card { border: 2px solid #222; border-radius: 12px; padding: 18px; max-width: 720px; }
    label { display: block; font-size: 20px; margin-bottom: 8px; }
    input { width: 100%; box-sizing: border-box; min-height: 72px; font-size: 24px; padding: 12px; }
    button { width: 100%; min-height: 80px; margin-top: 16px; font-size: 24px; }
    #gf-success { display: none; margin-top: 18px; padding: 16px; border: 3px solid #111; font-size: 24px; }
    #gf-spacer { height: 1100px; }
    #gf-scroll-target { min-height: 100px; padding: 16px; border: 2px dashed #333; font-size: 22px; }
  </style>
</head>
<body data-gf-ready="true">
  <h1 id="gf-title">GF Browser Qualification</h1>
  <div class="card">
    <label for="gf-message">Qualification message</label>
    <input id="gf-message" name="gf-message" autocomplete="off" placeholder="Type GENFARMER-OK">
    <button id="gf-submit" type="button">Submit qualification</button>
    <div id="gf-success" role="status">SUCCESS: <span id="gf-echo"></span></div>
  </div>
  <div id="gf-spacer"></div>
  <div id="gf-scroll-target">SCROLL TARGET REACHED</div>
  <script>
    window.__GF_READY__ = true;
    document.getElementById('gf-submit').addEventListener('click', function () {
      var value = document.getElementById('gf-message').value;
      document.getElementById('gf-echo').textContent = value;
      document.getElementById('gf-success').style.display = 'block';
      document.body.setAttribute('data-gf-result', value === 'GENFARMER-OK' ? 'pass' : 'submitted');
    });
  </script>
</body>
</html>
'''.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "GFFixture/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print("[fixture] " + (fmt % args))

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            body = json.dumps({"ok": True, "fixture": "gf-browser-qualification"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path not in {"/", "/index.html"}:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(HTML)))
        self.end_headers()
        self.wfile.write(HTML)


def guess_lan_ip() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve the deterministic GenFarmer Chrome qualification page")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--public-host", help="Host/IP to print for the Android device, e.g. 192.168.4.53")
    args = ap.parse_args()

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    host = args.public_host or guess_lan_ip() or "<THIS-PC-LAN-IP>"
    print("=" * 78)
    print("GENFARMER CHROME QUALIFICATION FIXTURE")
    print("=" * 78)
    print(f"Listening: http://{args.bind}:{args.port}/")
    print(f"Android URL: http://{host}:{args.port}/")
    print(f"Health:      http://{host}:{args.port}/healthz")
    print("Expected page title: GF Browser Qualification")
    print("Expected typed value: GENFARMER-OK")
    print("Press Ctrl+C to stop.")
    print("=" * 78)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
