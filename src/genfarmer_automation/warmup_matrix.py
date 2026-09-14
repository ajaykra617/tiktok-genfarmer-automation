"""Planning helpers for the passive TikTok warm-up qualification matrix."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatrixFeature:
    feature: str
    value: str | None = None


def build_matrix(*, keyword: str | None = None, hashtag: str | None = None) -> tuple[MatrixFeature, ...]:
    """Return the deterministic feature qualification order.

    Feed-source switching is qualified first and returned to For You before
    context excursions. Niche exploration is included only when explicitly
    supplied by the operator.
    """
    rows: list[MatrixFeature] = [
        MatrixFeature("following"),
        MatrixFeature("for-you"),
        MatrixFeature("comments"),
        MatrixFeature("profile"),
    ]
    if keyword and keyword.strip():
        rows.append(MatrixFeature("keyword", keyword.strip()))
    if hashtag and hashtag.strip():
        rows.append(MatrixFeature("hashtag", hashtag.strip().lstrip("#")))
    return tuple(rows)
