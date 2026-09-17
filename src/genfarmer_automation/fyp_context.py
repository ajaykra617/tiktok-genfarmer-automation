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

from .native_ui import NativeUiError, collect_nodes
from .warmup_features import (
    find_comments_node,
    find_creator_profile_entry,
    find_feed_source_node,
)


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

    # These terms are used only as conservative evidence that some legitimate
    # feed card is rendered. They do not cause clicks or engagement.
    phrase_groups = {
        "live-card": (
            "tap to watch live",
            "watch live",
            "live now",
        ),
        "repost-affordance": (
            "repost to followers",
            "reposted",
        ),
        "photo-card": (
            "photo mode",
            "swipe left",
            "swipe to see more",
            "photo",
            "photos",
        ),
        "sponsored-card": (
            "sponsored",
            "ad",
            "advertisement",
        ),
        "shop-card": (
            "shop now",
            "view product",
            "product",
        ),
    }
    loading_terms = (
        "loading",
        "please wait",
        "retry",
        "no internet connection",
        "network error",
    )

    seen: set[str] = set()
    for node in collect_nodes(xml, package=package):
        text = _norm(f"{node.text} {node.content_desc}")
        if not text:
            continue
        if any(term in text for term in loading_terms):
            loading_signal = True
        for label, terms in phrase_groups.items():
            if label not in seen and any(term in text for term in terms):
                seen.add(label)
                content_signals.append(label)

    signals.extend(content_signals)
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
