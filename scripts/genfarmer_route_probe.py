#!/usr/bin/env python3
"""GET-only verification of likely local GenFarmer routes.

This script probes only a curated set of read-only candidate paths discovered
inside the packaged GenFarmer application. It does not send POST/PUT/PATCH/
DELETE requests and does not attempt authenticated mutation endpoints.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CANDIDATES = [
    "/api",
    "/api/devices",
    "/devices",
    "/devices/details",
    "/devices/random",
    "/info",
    "/device",
    "/profile",
    "/group",
    "/instance",
    "/automation",
    "/automation/runs",
    "/tasks",
    "/apps",
    "/apps/total",
    "/v1/resource/device",
]


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


def fetch(url: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "genfarmer-automation-route-probe/0.1",
            "Accept": "application/json,text/plain,text/html,*/*;q=0.5",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(512_000)
            return {
                "status": r.status,
                "content_type": r.headers.get("Content-Type", ""),
                "allow": r.headers.get("Allow"),
                "body": raw.decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read(128_000)
        return {
            "status": exc.code,
            "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
            "allow": exc.headers.get("Allow") if exc.headers else None,
            "body": raw.decode("utf-8", errors="replace"),
        }
    except Exception as exc:
        return {
            "status": None,
            "content_type": "",
            "allow": None,
            "body": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def parse_preview(body: str, content_type: str) -> tuple[Any, str]:
    body = body.strip()
    parsed: Any = None
    if "json" in content_type.lower() or body.startswith(("{", "[")):
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            pass
    if parsed is not None:
        preview = json.dumps(parsed, ensure_ascii=False, indent=2)
    else:
        preview = " ".join(body.split())
    return parsed, preview[:1800]


def shape(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: shape(v) for k, v in list(obj.items())[:40]}
    if isinstance(obj, list):
        if not obj:
            return []
        return [shape(obj[0])]
    return type(obj).__name__


def main() -> int:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="GET-only GenFarmer route verification")
    parser.add_argument("--base-url", default=os.getenv("GENFARMER_BASE_URL"))
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    if not args.base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    base = args.base_url.rstrip("/")
    parsed_base = urllib.parse.urlparse(base)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
        print("ERROR: invalid GENFARMER_BASE_URL", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = ROOT / "evidence" / f"genfarmer-route-probe-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("GENFARMER GET-ONLY ROUTE VERIFICATION")
    print("=" * 72)
    print(f"Base URL: {base}")
    print("Methods: GET only")

    records: list[dict[str, Any]] = []
    interesting = 0

    for path in CANDIDATES:
        url = base + path
        result = fetch(url, args.timeout)
        parsed, preview = parse_preview(result.get("body", ""), result.get("content_type", ""))
        status = result.get("status")
        if status not in {404, None}:
            interesting += 1

        record: dict[str, Any] = {
            "path": path,
            "status": status,
            "content_type": result.get("content_type", ""),
            "allow": result.get("allow"),
            "error": result.get("error"),
            "preview": preview,
        }
        if parsed is not None:
            record["json_shape"] = shape(parsed)
            record["json"] = parsed
        records.append(record)

        status_text = status if status is not None else "ERR"
        print(f"\n[{status_text}] {path}")
        if record.get("allow"):
            print(f"  Allow: {record['allow']}")
        if record.get("error"):
            print(f"  {record['error']}")
        if record.get("content_type"):
            print(f"  content-type: {record['content_type']}")
        if preview:
            for line in preview.splitlines()[:18]:
                print(f"  {line}")

    out = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "safety": "GET-only curated route verification",
        "records": records,
    }
    out_path = evidence_dir / "result.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print(f"Non-404/transport-error responses: {interesting}")
    print(f"Result: {out_path.relative_to(ROOT)}")
    print("No mutation requests were sent.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
