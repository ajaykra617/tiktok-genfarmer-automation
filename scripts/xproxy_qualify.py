#!/usr/bin/env python3
"""Qualify one HTTP proxy endpoint before device automation uses it.

The probe is intentionally vendor-neutral. It validates proxy URL syntax, TCP
reachability, real HTTP(S) egress through the proxy, and a parseable external IP.
The external IP is written only to ignored private evidence; the shareable result
records whether verification passed without exposing the address.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.proxy_readiness import (  # noqa: E402
    ProxyReadinessError,
    parse_http_proxy,
    probe_http_proxy,
    tcp_reachable,
)


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Qualify one XProxy/HTTP proxy egress lane")
    ap.add_argument("--proxy-id", required=True, help="private local proxy label")
    ap.add_argument("--proxy-url", required=True, help="HTTP proxy URL, for example http://host:4001")
    ap.add_argument("--check-url", required=True, help="external endpoint that returns a public IP")
    ap.add_argument("--timeout", type=float, default=8.0)
    args = ap.parse_args()

    if args.timeout <= 0:
        print("ERROR: --timeout must be positive", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_proxy = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.proxy_id)
    out = ROOT / "evidence" / f"xproxy-qualify-{safe_proxy}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "xproxy-qualify.shareable.json"

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "proxy_id_private": True,
        "proxy_url_private": True,
        "check_url": args.check_url,
        "tcp_reachable": False,
        "egress_verified": False,
        "external_ip_detected": False,
    }

    try:
        endpoint = parse_http_proxy(args.proxy_url)
        tcp_ok = tcp_reachable(endpoint, timeout=min(args.timeout, 3.0))
        result["tcp_reachable"] = tcp_ok
        if not tcp_ok:
            raise ProxyReadinessError("proxy TCP endpoint is unreachable")

        readiness = probe_http_proxy(args.proxy_url, check_url=args.check_url, timeout=args.timeout)
        if not readiness.ready or not readiness.external_ip:
            raise ProxyReadinessError("proxy did not reach fully qualified egress state")

        _write_json(
            private / "proxy-readiness.private.json",
            {
                "proxy_id": args.proxy_id,
                "proxy_url": args.proxy_url,
                "tcp_reachable": readiness.tcp_reachable,
                "egress_verified": readiness.egress_verified,
                "external_ip": readiness.external_ip,
            },
        )
        result.update(
            {
                "status": "PASS",
                "tcp_reachable": True,
                "egress_verified": True,
                "external_ip_detected": True,
            }
        )
        _write_json(shareable, result)

        print("=" * 78)
        print("XPROXY EGRESS QUALIFICATION")
        print("=" * 78)
        print("Status:                     PASS")
        print("TCP endpoint:               PASS")
        print("HTTP(S) egress:             PASS")
        print("External IP detected:       YES (stored in private evidence)")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0
    except (OSError, ValueError, ProxyReadinessError) as exc:
        result.update({"status": "BLOCKED", "reason": str(exc)})
        _write_json(shareable, result)
        print("=" * 78, file=sys.stderr)
        print("XPROXY EGRESS QUALIFICATION", file=sys.stderr)
        print("=" * 78, file=sys.stderr)
        print("Status:                     BLOCKED", file=sys.stderr)
        print(f"TCP endpoint:               {'PASS' if result['tcp_reachable'] else 'FAIL'}", file=sys.stderr)
        print("HTTP(S) egress:             FAIL", file=sys.stderr)
        print("External IP detected:       NO", file=sys.stderr)
        print(f"Reason:                     {exc}", file=sys.stderr)
        print(f"Shareable result:           {shareable.relative_to(ROOT)}", file=sys.stderr)
        print("=" * 78, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
