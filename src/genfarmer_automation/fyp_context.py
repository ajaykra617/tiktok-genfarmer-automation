"""Conservative semantic classification for TikTok For You feed states.

The strict qualified selector is still the primary proof for ordinary video
cards. TikTok can legitimately show other For You states (LIVE, photo/image
posts, sponsored/shop cards, repost cards, etc.) where that selector is absent.
Those states must not be confused with an app crash.

This module never guesses a tap target and never treats a bare For You tab as a
healthy content card. It classifies only from fresh hierarchy evidence so the
caller can choose between waiting, advancing one card, restoring FYP, or failing
closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from .native_ui import NativeUiError, collect_nodes
from .warmup_features import (
    find_comments_node,
    find_creator_profile_entry,
    find_feed_source_node,
)
from . import tiktok_semantics as semantics


class FypState(str, Enum):
    CONTENT = "content"
    LOADING = "loading"
    OFF_FYP = "off_fyp"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FypContextProof:
    passed: bool
    signals: tuple[str, ...]
    state: FypState = FypState.UNKNOWN


def _norm(value: str) -> str:
    return " ".join((value or "").casefold().replace("_", " ").replace("-", " ").split())


def _tokens(value: str) -> tuple[str, ...]:
    """Return conservative word tokens for semantic phrase matching.

    Plain substring matching is unsafe for short markers. For example ``ad`` is
    contained in ``loading`` and previously caused a loading shell to be
    misclassified as a sponsored card. Token/phrase matching avoids that entire
    class of collision while still tolerating punctuation around UI labels.
    """
    return tuple(re.findall(r"[^\W_]+", _norm(value), flags=re.UNICODE))


def _contains_phrase(value: str, phrase: str) -> bool:
    haystack = _tokens(value)
    needle = _tokens(phrase)
    if not haystack or not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(haystack[index:index + width] == needle for index in range(len(haystack) - width + 1))


def _contains_any_phrase(value: str, phrases: tuple[str, ...]) -> bool:
    return any(_contains_phrase(value, phrase) for phrase in phrases)


def classify_fyp_context(xml: str, *, package: str | None = None) -> FypContextProof:
    """Classify a readable hierarchy without relying on one ordinary-video anchor.

    CONTENT requires exact For You tab evidence plus at least one independent
    content affordance. LOADING requires the For You tab plus an explicit loading
    indicator (or only the tab with no content yet). OFF_FYP means the exact For
    You tab is absent. Unknown remains fail-closed.
    """
    try:
        find_feed_source_node(xml, "for-you", package=package)
    except NativeUiError:
        return FypContextProof(False, (), FypState.OFF_FYP)

    signals: list[str] = ["for-you-tab"]
    content_signals: list[str] = []
    loading_signal = False

    try:
        find_comments_node(xml, package=package)
    except NativeUiError:
        pass
    else:
        content_signals.append("comments-control")

    try:
        find_creator_profile_entry(xml, package=package)
    except NativeUiError:
        pass
    else:
        content_signals.append("creator-profile")

    # These phrases are conservative evidence that a legitimate feed card is
    # rendered. They never trigger engagement or direct taps. Avoid very broad
    # single-token markers such as "ad", "photo", or "product": those words can
    # occur inside unrelated/loading UI and are not sufficient proof by themselves.
    phrase_groups: dict[str, tuple[str, ...]] = semantics.FYP_VARIANT_PHRASES
    loading_terms = semantics.LOADING_TERMS

    seen: set[str] = set()
    for node in collect_nodes(xml, package=package):
        text = _norm(f"{node.text} {node.content_desc}")
        if not text:
            continue
        if _contains_any_phrase(text, loading_terms):
            loading_signal = True
        for label, phrases in phrase_groups.items():
            if label not in seen and _contains_any_phrase(text, phrases):
                seen.add(label)
                content_signals.append(label)

    signals.extend(content_signals)

    # Explicit loading evidence wins when the hierarchy has no independent
    # standard feed affordance. This prevents stale/generic text from turning a
    # launch shell into a false healthy-content proof.
    strong_standard_content = any(
        signal in content_signals for signal in ("comments-control", "creator-profile")
    )
    if loading_signal and not strong_standard_content:
        return FypContextProof(False, tuple(signals + ["loading-indicator"]), FypState.LOADING)

    if content_signals:
        return FypContextProof(True, tuple(signals), FypState.CONTENT)
    if loading_signal:
        return FypContextProof(False, tuple(signals + ["loading-indicator"]), FypState.LOADING)

    # A bare selected tab with no independent content affordance is usually a
    # settle/loading state. Treat it as waitable, never as proof of a good card.
    return FypContextProof(False, tuple(signals), FypState.LOADING)


def prove_fyp_context(xml: str, *, package: str | None = None) -> FypContextProof:
    """Compatibility wrapper: prove any legitimate rendered FYP content state."""
    return classify_fyp_context(xml, package=package)
