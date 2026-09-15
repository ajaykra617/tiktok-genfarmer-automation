"""Helpers for passive TikTok Boost Explore qualification matrices.

The matrix is deliberately non-publishing and engagement-free. It aggregates
independent Explore child results so keyword/hashtag/account/link qualification
can continue after one source is blocked while still failing the overall matrix
unless every requested source reaches PASS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Any


_ALLOWED_TYPES = {"keyword", "hashtag", "account", "link"}
_TRANSIENT_HIERARCHY_REASON = "no healthy hierarchy source after helper-service recovery"


class BoostExploreMatrixError(ValueError):
    pass


@dataclass(frozen=True)
class ExploreSource:
    source_type: str
    value: str


def normalize_sources(items: Iterable[tuple[str, str]]) -> tuple[ExploreSource, ...]:
    rows: list[ExploreSource] = []
    seen: set[tuple[str, str]] = set()
    for source_type, value in items:
        kind = str(source_type).strip().casefold()
        raw = str(value).strip()
        if kind not in _ALLOWED_TYPES:
            raise BoostExploreMatrixError(f"unsupported explore source type: {source_type!r}")
        if not raw:
            raise BoostExploreMatrixError(f"{kind} source value must not be empty")
        key = (kind, raw.casefold())
        if key in seen:
            continue
        seen.add(key)
        rows.append(ExploreSource(kind, raw))
    if not rows:
        raise BoostExploreMatrixError("at least one Explore source is required")
    return tuple(rows)


def child_passed(returncode: int, payload: Mapping[str, Any] | None) -> bool:
    return returncode == 0 and isinstance(payload, Mapping) and payload.get("status") == "PASS"


def is_transient_hierarchy_failure(payload: Mapping[str, Any] | None) -> bool:
    """Return True only for the known cold/wedged hierarchy bootstrap failure.

    We intentionally do not retry semantic/UI failures. The live GF#7 matrix
    showed the first source failing because every hierarchy provider was briefly
    unavailable, immediately followed by healthy hierarchy captures for later
    sources. One bounded retry is therefore safe and targeted.
    """
    if not isinstance(payload, Mapping):
        return False
    if payload.get("status") != "BLOCKED":
        return False
    reason = payload.get("reason")
    return isinstance(reason, str) and _TRANSIENT_HIERARCHY_REASON in reason


def matrix_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = [dict(row) for row in rows]
    requested = len(values)
    passed = sum(1 for row in values if row.get("passed") is True)
    return {
        "status": "PASS" if requested > 0 and passed == requested else "BLOCKED",
        "requested_sources": requested,
        "passed_sources": passed,
        "blocked_sources": requested - passed,
        "all_requested_sources_passed": requested > 0 and passed == requested,
        "publishing_deferred": True,
        "engagement_actions": 0,
    }
