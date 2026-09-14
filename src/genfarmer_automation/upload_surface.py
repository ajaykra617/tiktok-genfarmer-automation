"""Sanitized semantic inspection helpers for TikTok/Android media upload surfaces.

The probe intentionally exposes only UI terms relevant to upload navigation or
media-type/duration hints. Arbitrary media titles, account names, captions, and
other user text stay private in the captured XML evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .native_ui import UiNode, collect_nodes

_SAFE_TERMS = (
    "create", "upload", "post", "publish", "next", "continue", "video", "videos",
    "photo", "photos", "image", "images", "album", "albums", "recent", "recents",
    "all", "select", "done", "camera", "gallery", "media", "genfarmerboost",
)
_DURATION_RE = re.compile(r"(?<!\d)(?:\d{1,2}:)?\d{1,2}:\d{2}(?!\d)")


@dataclass(frozen=True)
class UploadSurfaceRow:
    package: str
    class_name: str
    resource_id: str
    text: str
    content_desc: str
    bounds: tuple[int, int, int, int]
    clickable: bool


def _norm(value: str) -> str:
    return " ".join((value or "").casefold().replace("_", " ").replace("-", " ").split())


def _safe_value(value: str, *, safe_terms: Iterable[str]) -> bool:
    norm = _norm(value)
    if not norm:
        return False
    wanted = tuple(_norm(term) for term in safe_terms)
    if any(term and (norm == term or term in norm) for term in wanted):
        return True
    return bool(_DURATION_RE.search(value))


def sanitized_upload_rows(xml: str, *, safe_terms: Iterable[str] = _SAFE_TERMS) -> list[UploadSurfaceRow]:
    rows: list[UploadSurfaceRow] = []
    for node in collect_nodes(xml):
        safe_text = node.text if _safe_value(node.text, safe_terms=safe_terms) else ""
        safe_desc = node.content_desc if _safe_value(node.content_desc, safe_terms=safe_terms) else ""
        rid_suffix = node.resource_id.rsplit("/", 1)[-1] if node.resource_id else ""
        safe_rid = node.resource_id if _safe_value(rid_suffix, safe_terms=safe_terms) else ""
        if not (safe_text or safe_desc or safe_rid):
            continue
        rows.append(
            UploadSurfaceRow(
                package=node.package,
                class_name=node.class_name,
                resource_id=safe_rid,
                text=safe_text,
                content_desc=safe_desc,
                bounds=node.bounds,
                clickable=node.clickable,
            )
        )
    return rows
