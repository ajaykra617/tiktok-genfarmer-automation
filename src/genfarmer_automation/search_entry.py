"""Bounded semantic settle helpers for TikTok search entry.

Some devices expose the Search surface before Android accessibility publishes the
editable field. This module keeps the selector strict: it never invents a
coordinate and never substitutes a generic clickable node for an EditText. It
only repeats read-only hierarchy captures for a bounded settle window.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from .native_ui import NativeUiNotFound, UiNode, find_editable_node


@dataclass(frozen=True)
class SearchEntryResult:
    node: UiNode
    xml: str
    attempts: int


def wait_for_search_editable(
    capture: Callable[[], str],
    *,
    package: str | None = None,
    attempts: int = 4,
    settle_delays: tuple[float, ...] = (0.45, 0.75, 1.1),
    sleeper: Callable[[float], None] = time.sleep,
) -> SearchEntryResult:
    """Return the strict Search EditText after bounded accessibility settling.

    The first capture is immediate. Subsequent captures are separated by the
    supplied settle delays. Only NativeUiNotFound is retried; ambiguous
    editable matches or hierarchy/parser failures fail closed immediately.
    """
    if not 1 <= attempts <= 8:
        raise ValueError("attempts must be 1..8")
    if len(settle_delays) < max(0, attempts - 1):
        raise ValueError("settle_delays must cover every retry")
    if any(delay < 0 or delay > 5 for delay in settle_delays[: attempts - 1]):
        raise ValueError("settle delays must be between 0 and 5 seconds")

    last_xml = ""
    for index in range(1, attempts + 1):
        last_xml = capture()
        try:
            node = find_editable_node(
                last_xml,
                package=package,
                hints=("Search", "Rechercher"),
            )
        except NativeUiNotFound:
            if index >= attempts:
                break
            delay = settle_delays[index - 1]
            if delay:
                sleeper(delay)
            continue
        return SearchEntryResult(node=node, xml=last_xml, attempts=index)

    raise NativeUiNotFound(
        f"search surface did not expose an enabled EditText after {attempts} bounded hierarchy checks"
    )
