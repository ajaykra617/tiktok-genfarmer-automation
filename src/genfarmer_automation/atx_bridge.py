"""Helpers for reading Android UI hierarchy through an existing atx-agent.

GenFarmer's packaged implementation contains UiAutomator2/openatx terms including
``atx-agent`` and ``dumpWindowHierarchy``.  This module deliberately keeps the
bridge read-only from the application-under-test perspective: it only interprets
HTTP responses from an already-running helper and never installs packages,
creates a WebDriver session, taps, swipes, or changes app state.
"""
from __future__ import annotations

from typing import Any

from .ui_source_bridge import extract_source_xml


class AtxBridgeError(ValueError):
    pass


def atx_base_url(local_port: int) -> str:
    if not isinstance(local_port, int) or isinstance(local_port, bool) or not (1 <= local_port <= 65535):
        raise AtxBridgeError("local_port must be 1..65535")
    return f"http://127.0.0.1:{local_port}"


def extract_atx_version(payload: Any) -> str | None:
    if isinstance(payload, str):
        value = payload.strip()
        return value or None
    if isinstance(payload, dict):
        for key in ("version", "value", "result"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip() and not value.lstrip().startswith("<"):
                return value.strip()
    return None


def extract_atx_hierarchy_xml(payload: Any) -> str | None:
    """Extract hierarchy XML from raw or JSON-RPC-style atx-agent responses."""
    return extract_source_xml(payload)
