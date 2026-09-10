"""Read-only helpers for reusing an existing Android UI automation session.

Standalone ``uiautomator dump`` can fail when another automation client already
owns Android's UiAutomation channel.  GenFarmer may already have a UiAutomator2
or Appium-compatible helper running.  These helpers parse existing Appium-style
responses so a diagnostic probe can reuse an *already-existing* session without
creating a new one or disrupting GenFarmer.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping


class UiSourceBridgeError(ValueError):
    pass


def _as_nonempty_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def extract_session_ids(payload: Any) -> tuple[str, ...]:
    """Extract unique session ids from common Appium/WebDriver envelopes."""
    found: list[str] = []

    def add(value: Any) -> None:
        sid = _as_nonempty_str(value)
        if sid is not None and sid not in found:
            found.append(sid)

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key in ("sessionId", "session_id"):
                if key in value:
                    add(value.get(key))
            # GET /sessions commonly returns [{"id": "...", ...}] or a
            # W3C value envelope containing that list.
            if "id" in value and any(k in value for k in ("capabilities", "sessionId", "session_id")):
                add(value.get("id"))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, Mapping) and "id" in child:
                    add(child.get("id"))
                walk(child)

    walk(payload)
    return tuple(found)


def extract_source_xml(payload: Any) -> str | None:
    """Return XML from common WebDriver ``/source`` response shapes."""
    if isinstance(payload, str):
        text = payload.strip()
        return text if text.startswith("<") else None
    if isinstance(payload, Mapping):
        for key in ("value", "source", "xml"):
            if key not in payload:
                continue
            child = payload[key]
            if isinstance(child, str):
                text = child.strip()
                if text.startswith("<"):
                    return text
            nested = extract_source_xml(child)
            if nested is not None:
                return nested
        for child in payload.values():
            nested = extract_source_xml(child)
            if nested is not None:
                return nested
    elif isinstance(payload, list):
        for child in payload:
            nested = extract_source_xml(child)
            if nested is not None:
                return nested
    return None


def appium_base_candidates(port: int) -> tuple[str, ...]:
    if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
        raise UiSourceBridgeError("port must be 1..65535")
    root = f"http://127.0.0.1:{port}"
    return (root, root + "/wd/hub")


def session_source_paths(base: str, session_ids: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    clean_base = base.rstrip("/")
    for raw in session_ids:
        sid = _as_nonempty_str(raw)
        if sid is None:
            continue
        # Session ids are opaque identifiers.  Reject path separators instead
        # of trying to encode an unexpected value into a local diagnostic URL.
        if "/" in sid or "\\" in sid:
            continue
        out.append(f"{clean_base}/session/{sid}/source")
    return tuple(out)
