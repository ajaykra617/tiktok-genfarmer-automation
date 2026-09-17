"""Semantic proof for valid TikTok For You feed variants.

The qualified selector anchor used by the automation is intentionally strict and
works well for ordinary video cards. TikTok can also surface legitimate FYP
variants such as LIVE cards where that selector is absent. Treating every such
absence as an app crash causes false process restarts.

This module provides a second, conservative semantic proof. It requires the
exact For You tab plus at least one independent feed-content affordance. A bare
For You tab is not enough because it can be visible while content is still
loading.
"""
from __future__ import annotations

from dataclasses import dataclass

from .native_ui import NativeUiError, collect_nodes
from .warmup_features import (
    find_comments_node,
    find_creator_profile_entry,
    find_feed_source_node,
)


@dataclass(frozen=True)
class FypContextProof:
    passed: bool
    signals: tuple[str, ...]


def _norm(value: str) -> str:
    return " ".join((value or "").casefold().replace("_", " ").replace("-", " ").split())


def prove_fyp_context(xml: str, *, package: str | None = None) -> FypContextProof:
    """Prove a real FYP content context without relying on one video selector.

    The proof is deliberately conservative:
    - exact For You tab must be present;
    - at least one independent content signal must also be present.

    Standard video cards normally expose comments and/or creator-avatar controls.
    LIVE cards observed on the qualified device expose explicit LIVE-view or
    repost affordances instead. Unknown/blank/loading states remain unproven.
    """
    try:
        find_feed_source_node(xml, "for-you", package=package)
    except NativeUiError:
        return FypContextProof(False, ())

    signals: list[str] = ["for-you-tab"]

    try:
        find_comments_node(xml, package=package)
    except NativeUiError:
        pass
    else:
        signals.append("comments-control")

    try:
        find_creator_profile_entry(xml, package=package)
    except NativeUiError:
        pass
    else:
        signals.append("creator-profile")

    saw_live_view = False
    saw_repost = False
    for node in collect_nodes(xml, package=package):
        text = _norm(f"{node.text} {node.content_desc}")
        if "tap to watch live" in text or "watch live" in text:
            saw_live_view = True
        if "repost to followers" in text:
            saw_repost = True

    if saw_live_view:
        signals.append("live-card")
    if saw_repost:
        signals.append("repost-affordance")

    return FypContextProof(len(signals) >= 2, tuple(signals))
