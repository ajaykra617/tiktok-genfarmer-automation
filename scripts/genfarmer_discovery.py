#!/usr/bin/env python3
"""Read-only discovery probe for a locally configured GenFarmer service.

The probe intentionally limits itself to root, health, version, and common API
metadata/documentation paths. It never sends POST/PUT/PATCH/DELETE requests.
Results are sanitized and written under evidence/ for local inspection.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

SAFE_PATHS = [
    "/",
    "/health",
    "/api/health",
    "/version",
    "/api/version",
    "/docs",
    "/redoc",
    "/swagger",
    "/swagger/",
    "/swagger/index.html",
    "/openapi.json",
    "/swagger.json",
    "/api-docs",
    "/api/docs",
]

SENSITIVE_KEY_RE = re.compile(
    r"(?i)(password|passwd|secret|token|authorization|api[_-]?key|cookie|credential)"
)
URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@")


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


def sanitize_text(value: str) -> str:
    value = URL_CREDENTIAL_RE.sub(r"\1<redacted>:<redacted>@", value)
    # Redact obvious JSON-ish credential fields while retaining structure.
    value = re.sub(
        r'(?i)(["\']?(?:password|passwd|secret|token|authorization|api[_-]?key|cookie|credential)["\']?\s*[:=]\s*)["\']?[^,}\]\s<]+',
        r"\1<redacted>",
        value,
    )
    return value


def sanitize_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if SENSITIVE_KEY_RE.search(str(key)):
                out[str(key)] = "<redacted>"
            else:
                out[str(key)] = sanitize_obj(value)
        return out
    if isinstance(obj, list):
        return [sanitize_obj(x) for x in obj]
    if isinstance(obj, str):
        return sanitize_text(obj)
    return obj


def fetch(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "genfarmer-automation-discovery/0.1",
            "Accept": "application/json,text/html,text/plain,*/*;q=0.5",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(256_000)
            content_type = response.headers.get("Content-Type", "")
            text = raw.decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status": response.status,
                "final_url": response.geturl(),
                "content_type": content_type,
                "headers": {
                    "server": response.headers.get("Server"),
                    "allow": response.headers.get("Allow"),
                },
                "body": text,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read(64_000)
        text = raw.decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": exc.code,
            "final_url": exc.geturl(),
            "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
            "headers": {
                "server": exc.headers.get("Server") if exc.headers else None,
                "allow": exc.headers.get("Allow") if exc.headers else None,
            },
            "body": text,
            "error": f"HTTP {exc.code}",
        }
    except Exception as exc:  # network errors are useful discovery evidence
        return {
            "ok": False,
            "status": None,
            "final_url": url,
            "content_type": "",
            "headers": {},
            "body": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def summarize_body(body: str, content_type: str) -> tuple[Any, str]:
    body = sanitize_text(body)
    parsed: Any = None
    if "json" in content_type.lower() or body.lstrip().startswith(("{", "[")):
        try:
            parsed = sanitize_obj(json.loads(body))
        except json.JSONDecodeError:
            parsed = None

    if parsed is not None:
        preview = json.dumps(parsed, ensure_ascii=False, indent=2)
    else:
        cleaned = re.sub(r"\s+", " ", html.unescape(body)).strip()
        preview = cleaned
    return parsed, preview[:1200]


def discover_links(body: str) -> list[str]:
    candidates = set()
    for match in re.findall(r'''(?:href|src)=["']([^"']+)["']''', body, flags=re.I):
        lower = match.lower()
        if any(word in lower for word in ("api", "swagger", "openapi", "docs", "redoc")):
            candidates.add(sanitize_text(match))
    return sorted(candidates)[:50]


def main() -> int:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Read-only GenFarmer API discovery")
    parser.add_argument(
        "--base-url",
        default=os.getenv("GENFARMER_BASE_URL"),
        help="GenFarmer base URL; otherwise read GENFARMER_BASE_URL from .env",
    )
    parser.add_argument("--timeout", type=float, default=4.0)
    args = parser.parse_args()

    if not args.base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env or pass --base-url", file=sys.stderr)
        return 2

    parsed_base = urllib.parse.urlparse(args.base_url)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
        print("ERROR: GENFARMER_BASE_URL must be an http(s) URL", file=sys.stderr)
        return 2

    base = args.base_url.rstrip("/")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = ROOT / "evidence" / f"genfarmer-discovery-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 68)
    print("GENFARMER READ-ONLY API DISCOVERY")
    print("=" * 68)
    print(f"Base URL: {base}")
    print("Methods: GET only")
    print(f"Evidence: {evidence_dir.relative_to(ROOT)}")

    results: list[dict[str, Any]] = []

    for path in SAFE_PATHS:
        url = urllib.parse.urljoin(base + "/", path.lstrip("/"))
        result = fetch(url, args.timeout)
        parsed, preview = summarize_body(result.get("body", ""), result.get("content_type", ""))
        links = discover_links(result.get("body", "")) if "html" in result.get("content_type", "").lower() else []

        record = {
            "path": path,
            "status": result.get("status"),
            "ok": result.get("ok"),
            "final_url": sanitize_text(result.get("final_url", url)),
            "content_type": result.get("content_type", ""),
            "headers": sanitize_obj(result.get("headers", {})),
            "error": sanitize_text(result.get("error", "")),
            "preview": preview,
            "links": links,
        }
        if isinstance(parsed, (dict, list)):
            record["json"] = parsed
        results.append(record)

        status = record["status"] if record["status"] is not None else "ERR"
        print(f"\n[{status}] {path}")
        if record["error"]:
            print(f"  {record['error']}")
        if record["content_type"]:
            print(f"  content-type: {record['content_type']}")
        if preview:
            print("  preview:")
            for line in preview[:600].splitlines()[:12]:
                print(f"    {line}")
        if links:
            print("  interesting links:")
            for link in links[:10]:
                print(f"    {link}")

    output = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": sanitize_text(base),
        "safety": "GET-only probe of root/health/version/documentation metadata paths",
        "results": results,
    }
    out_path = evidence_dir / "result.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    successful = [r for r in results if r["status"] and int(r["status"]) < 400]
    print("\n" + "=" * 68)
    print(f"Discovery complete: {len(successful)} responding metadata path(s)")
    print(f"Result: {out_path.relative_to(ROOT)}")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
