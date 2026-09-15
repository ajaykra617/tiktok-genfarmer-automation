"""Source-pool and preset planning for non-publishing TikTok Boost Phase A.

This module only chooses passive Explore inputs and preparation settings. It does
not enter TikTok's Create/Upload/Post UI and performs no engagement actions.
Random source selection is seeded and recorded so a preparation run can be
reproduced from evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import random
import re
from typing import Any, Mapping, Sequence


class BoostSourceError(ValueError):
    pass


_SOURCE_TYPES = {"keyword", "hashtag", "account", "link"}
_SELECTION_MODES = {"first", "random"}


@dataclass(frozen=True)
class ExploreSource:
    source_type: str
    value: str


@dataclass(frozen=True)
class BoostPreparePreset:
    name: str
    warm_scroll_videos: int
    lease_minutes: float
    selection: str
    sources: tuple[ExploreSource, ...]


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BoostSourceError(f"{field} must be a non-empty string")
    return value.strip()


def normalize_source(source_type: str, value: str) -> ExploreSource:
    kind = _required_text(source_type, "source.type").casefold()
    if kind not in _SOURCE_TYPES:
        raise BoostSourceError(f"unsupported source type: {kind}")
    raw = _required_text(value, "source.value")
    normalized = raw
    if kind == "hashtag":
        normalized = raw.lstrip("#").strip()
    elif kind == "account":
        normalized = raw.lstrip("@").strip()
    elif kind == "link":
        if not re.match(r"^https?://", raw, re.IGNORECASE):
            raise BoostSourceError("link source must be an http(s) URL")
    if not normalized:
        raise BoostSourceError("source value became empty after normalization")
    return ExploreSource(kind, normalized)


def load_source_pool(raw_sources: Any) -> tuple[ExploreSource, ...]:
    if raw_sources in (None, []):
        return ()
    if not isinstance(raw_sources, Sequence) or isinstance(raw_sources, (str, bytes)):
        raise BoostSourceError("explore.sources must be an array")
    result: list[ExploreSource] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_sources, 1):
        if not isinstance(raw, Mapping):
            raise BoostSourceError(f"explore source {index} must be an object")
        source = normalize_source(raw.get("type"), raw.get("value"))
        key = (source.source_type, source.value.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return tuple(result)


def choose_source(
    sources: Sequence[ExploreSource],
    *,
    selection: str,
    seed: int,
) -> tuple[ExploreSource | None, int | None]:
    mode = _required_text(selection, "explore.selection").casefold()
    if mode not in _SELECTION_MODES:
        raise BoostSourceError(f"unsupported explore selection mode: {mode}")
    if not sources:
        return None, None
    if mode == "first":
        return sources[0], 0
    index = random.Random(int(seed)).randrange(len(sources))
    return sources[index], index


def load_preset(payload: Mapping[str, Any], name: str) -> BoostPreparePreset:
    presets = payload.get("presets")
    if not isinstance(presets, Mapping):
        raise BoostSourceError("preset configuration must contain an object named 'presets'")
    preset_name = _required_text(name, "preset")
    raw = presets.get(preset_name)
    if not isinstance(raw, Mapping):
        raise BoostSourceError(f"Boost preset not found: {preset_name}")

    try:
        warm_scroll_videos = int(raw.get("warm_scroll_videos", 0))
        lease_minutes = float(raw.get("lease_minutes", 120.0))
    except (TypeError, ValueError) as exc:
        raise BoostSourceError("warm_scroll_videos/lease_minutes must be numeric") from exc
    if not 0 <= warm_scroll_videos <= 20:
        raise BoostSourceError("warm_scroll_videos must be 0..20")
    if not 1 <= lease_minutes <= 1440:
        raise BoostSourceError("lease_minutes must be 1..1440")

    explore = raw.get("explore", {})
    if explore is None:
        explore = {}
    if not isinstance(explore, Mapping):
        raise BoostSourceError("preset explore must be an object")
    selection = str(explore.get("selection", "first")).strip().casefold() or "first"
    if selection not in _SELECTION_MODES:
        raise BoostSourceError(f"unsupported explore selection mode: {selection}")
    sources = load_source_pool(explore.get("sources", []))

    return BoostPreparePreset(
        name=preset_name,
        warm_scroll_videos=warm_scroll_videos,
        lease_minutes=lease_minutes,
        selection=selection,
        sources=sources,
    )


def preset_summary(preset: BoostPreparePreset) -> dict[str, Any]:
    return {
        "name": preset.name,
        "warm_scroll_videos": preset.warm_scroll_videos,
        "lease_minutes": preset.lease_minutes,
        "explore_selection": preset.selection,
        "explore_sources": len(preset.sources),
        "source_types": sorted({source.source_type for source in preset.sources}),
        "publishing_deferred": True,
    }
