"""Fail-closed schema resolution for configured GenFarmer ElementExists nodes.

Empty palette templates may omit their selector field entirely. A one-time
schema-probe export can serialize a known sentinel XPath. Once that exact scalar
exists in captured data, it is safe to replace that existing path without
inventing undocumented fields.
"""
from __future__ import annotations

from typing import Any

from .structure_paths import find_key_paths, find_scalar_value_paths


class ElementExistsSchemaError(ValueError):
    pass


def printable_path(path: tuple[str | int, ...]) -> str:
    out = "$"
    for part in path:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}"
    return out


def resolve_xpath_path(
    data: dict[str, Any],
    sentinel: str,
) -> tuple[tuple[str | int, ...], str]:
    """Resolve exactly one already-observed selector path.

    Priority:
    1. one exact normalized ``xpath`` key already serialized by GenFarmer;
    2. one scalar field whose value exactly equals the known schema sentinel.
    """
    xpath_paths = find_key_paths(data, "xpath")
    if len(xpath_paths) == 1:
        return xpath_paths[0], "verified XPath key"
    if len(xpath_paths) > 1:
        visible = ", ".join(printable_path(path) for path in xpath_paths)
        raise ElementExistsSchemaError(
            "multiple XPath keys were captured; refusing ambiguous patch: " + visible
        )

    sentinel_paths = find_scalar_value_paths(data, sentinel)
    if len(sentinel_paths) == 1:
        return sentinel_paths[0], "exact schema-probe sentinel"
    if len(sentinel_paths) > 1:
        visible = ", ".join(printable_path(path) for path in sentinel_paths)
        raise ElementExistsSchemaError(
            "schema-probe sentinel appears in multiple fields; refusing ambiguous patch: " + visible
        )
    raise ElementExistsSchemaError(
        "captured ElementExists data contains neither one XPath key nor the exact schema-probe sentinel"
    )
