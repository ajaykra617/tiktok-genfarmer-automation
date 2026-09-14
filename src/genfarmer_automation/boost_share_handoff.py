"""Bounded Android share-sheet handoff helpers for TikTok Boost.

The media publisher prefers a package-targeted ACTION_SEND. Some Android builds
still surface a system Resolver/Chooser before entering TikTok. These helpers
recognize only known system share surfaces and require an exact TikTok semantic
target from fresh hierarchy evidence; unknown foreground apps fail closed.
"""
from __future__ import annotations

from .native_ui import UiNode, find_exact_semantic_node

_SYSTEM_SHARE_PACKAGES = {
    "android",
    "com.android.intentresolver",
    "com.google.android.intentresolver",
}
_SHARE_ACTIVITY_MARKERS = (
    "resolveractivity",
    "chooseractivity",
    "intentresolver",
)


def is_system_share_surface(package: str | None, activity: str | None) -> bool:
    pkg = (package or "").strip().casefold()
    act = (activity or "").strip().casefold()
    if pkg in _SYSTEM_SHARE_PACKAGES:
        return True
    return any(marker in act for marker in _SHARE_ACTIVITY_MARKERS)


def find_tiktok_share_target(xml: str) -> UiNode:
    """Resolve exactly one visible TikTok target on a system share surface."""
    return find_exact_semantic_node(xml, ("TikTok",), package=None)
