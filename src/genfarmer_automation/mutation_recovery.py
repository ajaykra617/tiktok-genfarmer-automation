"""Workflow-safe classification for ambiguous ADB mutations.

Transport health alone is not permission to replay a UI mutation. These helpers
only expose whether the transport positively remained healthy while the host
lost certainty about the mutation outcome. Individual workflows decide whether
they have a non-replay recovery checkpoint.
"""
from __future__ import annotations

from .adb_actions import AdbActionError


def healthy_transport_ambiguous_mutation(error: BaseException) -> bool:
    """Return True only for an explicitly ambiguous mutation on healthy ADB."""
    return (
        isinstance(error, AdbActionError)
        and error.mutation_ambiguous is True
        and error.transport_healthy is True
    )
