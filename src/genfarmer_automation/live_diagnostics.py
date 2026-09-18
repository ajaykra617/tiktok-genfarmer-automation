"""Read-only diagnostics for LIVE-related TikTok hierarchy states.

These helpers do not decide whether a node is safe to tap. They only collect
bounded evidence so a trace can show whether a failing feed transition involved
a LIVE card, LIVE badge, survey, or other live-related accessibility node.
"""
from __future__ import annotations

import re
from typing import Any

from .native_ui import collect_nodes


def _norm(value: str) -> str:
    return " ".join((value or "").casefold().replace("_", " ").replace("-", " ").split())


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[^\W_]+", _norm(value), flags=re.UNICODE))


def collect_live_hints(
    xml: str,
    *,
    package: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Collect diagnostic nodes that contain conservative LIVE/direct markers."""
    out: list[dict[str, Any]] = []
    for node in collect_nodes(xml, package=package):
        joined = f"{node.text} {node.content_desc} {node.resource_id.rsplit('/', 1)[-1]}"
        tokens = set(_tokens(joined))
        normalized = _norm(joined)
        has_live = "live" in tokens
        has_direct = "direct" in tokens or "en direct" in normalized
        has_stream = "livestream" in tokens or "live stream" in normalized
        if not (has_live or has_direct or has_stream):
            continue
        out.append(
            {
                "text": node.text,
                "content_desc": node.content_desc,
                "resource_id": node.resource_id,
                "class_name": node.class_name,
                "bounds": node.bounds,
                "clickable": node.clickable,
                "enabled": node.enabled,
            }
        )
        if len(out) >= limit:
            break
    return out


def live_hint_summary(xml: str, *, package: str | None = None) -> dict[str, Any]:
    hints = collect_live_hints(xml, package=package)
    return {
        "detected": bool(hints),
        "count": len(hints),
        "nodes": hints,
    }
