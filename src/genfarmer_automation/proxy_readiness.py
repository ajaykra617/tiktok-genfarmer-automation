"""Fail-closed readiness checks for configured HTTP proxy endpoints.

This module deliberately does not rotate proxies or call vendor-specific APIs.
It verifies the reusable conditions we need before a proxy-required automation
wave starts: endpoint syntax, TCP reachability, and optionally real HTTP(S)
egress with a parseable external IP.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import socket
from urllib.parse import urlparse
import urllib.error
import urllib.request


class ProxyReadinessError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProxyEndpoint:
    url: str
    host: str
    port: int


@dataclass(frozen=True)
class ProxyReadiness:
    tcp_reachable: bool
    external_ip: str | None
    egress_verified: bool

    @property
    def ready(self) -> bool:
        return self.tcp_reachable and self.egress_verified


def parse_http_proxy(url: str) -> ProxyEndpoint:
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme.casefold() != "http":
        raise ProxyReadinessError("HTTP proxy URL must use http://")
    if not parsed.hostname or parsed.port is None:
        raise ProxyReadinessError("HTTP proxy URL must include host and port")
    if not 1 <= int(parsed.port) <= 65535:
        raise ProxyReadinessError("HTTP proxy port must be 1..65535")
    return ProxyEndpoint(url=raw, host=parsed.hostname, port=int(parsed.port))


def tcp_reachable(endpoint: ProxyEndpoint, *, timeout: float = 3.0) -> bool:
    if timeout <= 0:
        raise ProxyReadinessError("proxy TCP timeout must be positive")
    try:
        with socket.create_connection((endpoint.host, endpoint.port), timeout=timeout):
            return True
    except OSError:
        return False


def extract_external_ip(body: str) -> str:
    raw = (body or "").strip()
    candidates: list[str] = []
    if raw:
        candidates.append(raw)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        for key in ("ip", "query", "origin", "address"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                candidates.insert(0, value.strip())
    for candidate in candidates:
        # Some endpoints return comma-separated proxy chains in `origin`.
        for part in candidate.split(","):
            value = part.strip()
            try:
                return str(ipaddress.ip_address(value))
            except ValueError:
                continue
    raise ProxyReadinessError("external IP endpoint did not return a parseable IP address")


def probe_http_proxy(
    proxy_url: str,
    *,
    check_url: str | None = None,
    timeout: float = 8.0,
) -> ProxyReadiness:
    endpoint = parse_http_proxy(proxy_url)
    reachable = tcp_reachable(endpoint, timeout=min(timeout, 3.0))
    if not reachable:
        return ProxyReadiness(tcp_reachable=False, external_ip=None, egress_verified=False)
    if not check_url:
        return ProxyReadiness(tcp_reachable=True, external_ip=None, egress_verified=False)

    proxies = {"http": endpoint.url, "https": endpoint.url}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
    request = urllib.request.Request(check_url, headers={"User-Agent": "genfarmer-proxy-readiness/1"})
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProxyReadinessError(f"HTTP proxy egress check failed: {exc}") from exc
    ip = extract_external_ip(body)
    return ProxyReadiness(tcp_reachable=True, external_ip=ip, egress_verified=True)
