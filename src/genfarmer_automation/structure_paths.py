"""Small helpers for inspecting and patching already-observed JSON structures.

These helpers are intentionally schema-agnostic. They do not invent fields; they
only locate keys that are already present in a captured GenFarmer payload.
"""
from __future__ import annotations

from typing import Any


PathPart = str | int


def normalized_key(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def find_key_paths(value: Any, target_key: str) -> list[tuple[PathPart, ...]]:
    """Return paths to existing mapping values whose key matches target_key.

    Matching is normalization-only (case/punctuation insensitive). No semantic
    aliases are guessed.
    """
    target = normalized_key(target_key)
    out: list[tuple[PathPart, ...]] = []

    def walk(current: Any, path: tuple[PathPart, ...]) -> None:
        if isinstance(current, dict):
            for key, child in current.items():
                skey = str(key)
                child_path = path + (skey,)
                if normalized_key(skey) == target:
                    out.append(child_path)
                walk(child, child_path)
        elif isinstance(current, list):
            for index, child in enumerate(current):
                walk(child, path + (index,))

    walk(value, ())
    return out


def set_existing_path(value: Any, path: tuple[PathPart, ...], replacement: Any) -> None:
    """Replace an already-existing path; never creates new schema fields."""
    if not path:
        raise ValueError("path must not be empty")
    current = value
    for part in path[:-1]:
        if isinstance(part, int):
            if not isinstance(current, list) or not (0 <= part < len(current)):
                raise ValueError("path does not exist")
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                raise ValueError("path does not exist")
            current = current[part]
    leaf = path[-1]
    if isinstance(leaf, int):
        if not isinstance(current, list) or not (0 <= leaf < len(current)):
            raise ValueError("path does not exist")
        current[leaf] = replacement
    else:
        if not isinstance(current, dict) or leaf not in current:
            raise ValueError("path does not exist")
        current[leaf] = replacement


def structure_paths(value: Any, *, max_depth: int = 8) -> list[str]:
    """Describe mapping/list structure using paths and value types only."""
    rows: list[str] = []

    def walk(current: Any, path: str, depth: int) -> None:
        if depth > max_depth:
            rows.append(f"{path} <max-depth>")
            return
        if isinstance(current, dict):
            rows.append(f"{path} object[{len(current)}]")
            for key in sorted(current, key=lambda item: str(item)):
                child = current[key]
                walk(child, f"{path}.{key}", depth + 1)
        elif isinstance(current, list):
            rows.append(f"{path} list[{len(current)}]")
            for index, child in enumerate(current[:8]):
                walk(child, f"{path}[{index}]", depth + 1)
        else:
            rows.append(f"{path} {type(current).__name__}")

    walk(value, "$", 0)
    return rows
