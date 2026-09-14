"""Helpers for selecting an exact staged media item from TikTok's normal gallery.

Selection is fail-closed: we derive the target duration from Android MediaStore,
match the exact visible duration label, and require one unique clickable media
tile ancestor. We never guess a gallery coordinate.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import xml.etree.ElementTree as ET


class GalleryPickerError(RuntimeError):
    pass


_BOUNDS_RE = re.compile(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$")


@dataclass(frozen=True)
class GalleryTile:
    label: str
    bounds: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)


def duration_label(duration_ms: int) -> str:
    if duration_ms <= 0:
        raise GalleryPickerError("media duration must be positive")
    total = max(1, int(round(duration_ms / 1000.0)))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _bounds(raw: str) -> tuple[int, int, int, int] | None:
    match = _BOUNDS_RE.match((raw or "").strip())
    if not match:
        return None
    x1, y1, x2, y2 = (int(v) for v in match.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def find_unique_duration_tile(xml: str, *, duration_ms: int, package: str) -> GalleryTile:
    """Return the nearest clickable ancestor for one exact duration label.

    TikTok renders duration text inside the media tile. The duration TextView is
    not itself clickable, so we walk its XML ancestors and select the smallest
    enabled clickable ancestor. If multiple tiles show the same duration we
    refuse to choose one.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise GalleryPickerError("gallery hierarchy XML is invalid") from exc

    wanted = duration_label(duration_ms)
    matches: list[GalleryTile] = []

    def walk(node: ET.Element, ancestors: list[ET.Element]) -> None:
        node_package = node.attrib.get("package", "")
        text = (node.attrib.get("text") or "").strip()
        desc = (node.attrib.get("content-desc") or "").strip()
        if node_package in {"", package} and wanted in {text, desc}:
            candidates: list[tuple[int, tuple[int, int, int, int]]] = []
            for ancestor in reversed(ancestors):
                if ancestor.attrib.get("enabled", "true") == "false":
                    continue
                if ancestor.attrib.get("clickable") != "true":
                    continue
                ancestor_package = ancestor.attrib.get("package", "")
                if ancestor_package not in {"", package}:
                    continue
                b = _bounds(ancestor.attrib.get("bounds", ""))
                if b is None:
                    continue
                x1, y1, x2, y2 = b
                candidates.append(((x2 - x1) * (y2 - y1), b))
            if not candidates:
                raise GalleryPickerError(
                    f"duration {wanted} is visible but has no clickable media-tile ancestor"
                )
            candidates.sort(key=lambda item: item[0])
            matches.append(GalleryTile(wanted, candidates[0][1]))

        for child in list(node):
            walk(child, [*ancestors, node])

    walk(root, [])

    unique: dict[tuple[int, int], GalleryTile] = {item.center: item for item in matches}
    if not unique:
        raise GalleryPickerError(f"staged media duration {wanted} is not visible in TikTok gallery")
    if len(unique) != 1:
        raise GalleryPickerError(
            f"staged media duration {wanted} matches {len(unique)} visible tiles; refusing ambiguous selection"
        )
    return next(iter(unique.values()))
