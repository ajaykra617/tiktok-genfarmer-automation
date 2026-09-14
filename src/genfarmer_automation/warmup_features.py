"""Semantic helpers for passive TikTok warm-up features.

These helpers deliberately target only passive browsing controls: feed-source
selection, comments, creator profile entry, and context verification. They do
not implement likes, follows, replies, DMs, or any other engagement action.

All tap targets are derived from fresh UI hierarchy bounds. Ambiguous or
missing controls fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .native_ui import (
    NativeUiAmbiguous,
    NativeUiNotFound,
    UiNode,
    collect_nodes,
    find_exact_semantic_node,
    find_semantic_node,
)


class WarmupFeature(str, Enum):
    FOR_YOU = "for-you"
    FOLLOWING = "following"
    PROFILE = "profile"
    COMMENTS = "comments"


@dataclass(frozen=True)
class ContextProof:
    kind: str
    matched_terms: tuple[str, ...]
    passed: bool


def _norm(value: str) -> str:
    return " ".join((value or "").casefold().replace("_", " ").replace("-", " ").split())


def _contains_any(value: str, terms: Iterable[str]) -> bool:
    normalized = _norm(value)
    return any(_norm(term) in normalized for term in terms if _norm(term))


def find_feed_source_node(xml: str, source: str, *, package: str | None = None) -> UiNode:
    normalized = source.strip().casefold().replace("_", "-")
    if normalized in {"foryou", "for-you", "for you", "fyp"}:
        terms = ("For You", "For you", "Pour toi")
    elif normalized in {"following", "follow"}:
        terms = ("Following", "Abonnements")
    else:
        raise ValueError(f"unsupported feed source: {source}")
    return find_exact_semantic_node(xml, terms, package=package)


def following_empty_state(xml: str, *, package: str | None = None) -> ContextProof:
    """Recognize TikTok's legitimate empty Following-feed prerequisite state.

    A newly prepared account may have no followed creators. In that case TikTok
    shows a recommendation/empty-state screen instead of feed items. That is not
    an automation failure and must not trigger an automated Follow action.
    """
    matched: list[str] = []
    for node in collect_nodes(xml, package=package):
        joined = f"{node.text} {node.content_desc}"
        if _contains_any(joined, ("Trending creators", "Créateurs tendance")):
            if "trending-creators" not in matched:
                matched.append("trending-creators")
        if _contains_any(
            joined,
            (
                "Follow an account to see their latest videos here",
                "Follow an account to see their latest videos here.",
                "Suivez un compte",
            ),
        ):
            if "follow-prerequisite" not in matched:
                matched.append("follow-prerequisite")
    return ContextProof("following-empty", tuple(matched), "follow-prerequisite" in matched)


def find_comments_node(xml: str, *, package: str | None = None) -> UiNode:
    """Find the passive comments-entry control on the current feed item."""
    candidates: list[UiNode] = []
    for node in collect_nodes(xml, package=package):
        if not node.enabled or not node.clickable:
            continue
        haystack = f"{node.text} {node.content_desc} {node.resource_id.rsplit('/', 1)[-1]}"
        if _contains_any(haystack, ("comments", "comment", "commentaires")):
            candidates.append(node)
    if not candidates:
        raise NativeUiNotFound("no clickable comments control found in current hierarchy")

    # Prefer semantically explicit controls, then smaller controls. This avoids
    # selecting a large comment-panel container if one is already present.
    ranked = sorted(
        candidates,
        key=lambda node: (
            int(_contains_any(node.content_desc, ("comments", "comment", "commentaires"))),
            int(_contains_any(node.text, ("comments", "comment", "commentaires"))),
            -node.area,
        ),
        reverse=True,
    )
    top = ranked[0]
    top_key = (
        int(_contains_any(top.content_desc, ("comments", "comment", "commentaires"))),
        int(_contains_any(top.text, ("comments", "comment", "commentaires"))),
        -top.area,
    )
    tied = [
        node for node in ranked
        if (
            int(_contains_any(node.content_desc, ("comments", "comment", "commentaires"))),
            int(_contains_any(node.text, ("comments", "comment", "commentaires"))),
            -node.area,
        ) == top_key
    ]
    if len({node.center for node in tied}) > 1:
        raise NativeUiAmbiguous("multiple comments controls tied for best runtime match")
    return top


def find_creator_profile_entry(xml: str, *, package: str | None = None) -> UiNode:
    """Find the current creator avatar/profile entry without using the bottom nav.

    We intentionally require avatar/profile-photo style evidence and do not use a
    bare `Profile` label, because TikTok's bottom navigation contains the user's
    own Profile tab and is not the desired creator entry point.
    """
    candidates: list[tuple[int, int, UiNode]] = []
    for node in collect_nodes(xml, package=package):
        if not node.enabled or not node.clickable:
            continue
        rid = _norm(node.resource_id.rsplit("/", 1)[-1])
        desc = _norm(node.content_desc)
        text = _norm(node.text)
        score = 0
        if "avatar" in desc:
            score = max(score, 130)
        if "avatar" in rid:
            score = max(score, 115)
        if "profile photo" in desc or "profile picture" in desc:
            score = max(score, 120)
        if "photo de profil" in desc:
            score = max(score, 120)
        if "avatar" in text:
            score = max(score, 105)
        if score:
            candidates.append((score, -node.area, node))
    if not candidates:
        raise NativeUiNotFound("no current-creator avatar/profile-photo control found")
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    top_score, top_area, top = candidates[0]
    tied = [item for item in candidates if item[0] == top_score and item[1] == top_area]
    if len({item[2].center for item in tied}) > 1:
        raise NativeUiAmbiguous("multiple creator profile-entry controls tied for best match")
    return top


def prove_comments_context(xml: str, *, package: str | None = None) -> ContextProof:
    matched: list[str] = []
    checks = (
        ("comments", ("Comments", "Comment", "Commentaires")),
        ("add-comment", ("Add comment", "Add comment...", "Ajouter un commentaire")),
    )
    for label, terms in checks:
        try:
            find_semantic_node(xml, terms, package=package)
        except (NativeUiNotFound, NativeUiAmbiguous):
            continue
        matched.append(label)
    return ContextProof("comments", tuple(matched), bool(matched))


def prove_profile_context(xml: str, *, package: str | None = None) -> ContextProof:
    matched: list[str] = []
    checks = (
        ("followers", ("Followers", "Abonnés")),
        ("following", ("Following", "Abonnements")),
        ("likes", ("Likes", "J'aime")),
        ("videos", ("Videos", "Vidéos")),
    )
    for label, terms in checks:
        try:
            find_semantic_node(xml, terms, package=package)
        except (NativeUiNotFound, NativeUiAmbiguous):
            continue
        matched.append(label)
    # Creator profiles consistently expose more than one of these counters/tabs;
    # requiring two avoids treating a stray word on feed as a profile proof.
    return ContextProof("profile", tuple(matched), len(set(matched)) >= 2)
