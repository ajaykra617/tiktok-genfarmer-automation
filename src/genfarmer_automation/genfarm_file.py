"""Lossless helpers for GenFarmer ``.genfarm`` export files.

A ``.genfarm`` export is JSON containing the app metadata plus ``script.flow``.
This module keeps every unknown field intact so exported apps can be inspected,
cloned and edited with Python without re-creating GenFarmer's schema by hand.

The safe rule is the same as for live API flows: clone observed structures and
patch only fields we have verified.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping

from .flow import FlowDocument, FlowError, find_flow


class GenFarmFileError(ValueError):
    """Raised when a .genfarm export cannot be parsed safely."""


class GenFarmDocument:
    """Lossless wrapper around one exported GenFarmer app."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload = deepcopy(dict(payload))
        flow = find_flow(self._payload)
        if flow is None:
            raise GenFarmFileError("export has no script.flow with nodes/edges")

    @classmethod
    def load(cls, path: str | Path) -> "GenFarmDocument":
        export_path = Path(path)
        try:
            value = json.loads(export_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GenFarmFileError(f"cannot read .genfarm JSON: {exc}") from exc
        if not isinstance(value, Mapping):
            raise GenFarmFileError(".genfarm root must be a JSON object")
        return cls(value)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._payload)

    @property
    def script(self) -> dict[str, Any]:
        script = self._payload.get("script")
        if not isinstance(script, dict):
            raise GenFarmFileError("export has no script object")
        return script

    @property
    def flow(self) -> FlowDocument:
        try:
            return FlowDocument.from_app_payload(self._payload)
        except FlowError as exc:
            raise GenFarmFileError(str(exc)) from exc

    def replace_flow(self, flow: FlowDocument | Mapping[str, Any]) -> None:
        value = flow.to_dict() if isinstance(flow, FlowDocument) else deepcopy(dict(flow))
        if not isinstance(value.get("nodes"), list) or not isinstance(value.get("edges"), list):
            raise GenFarmFileError("replacement flow must contain nodes and edges lists")
        self.script["flow"] = value

    def patch_metadata(self, patch: Mapping[str, Any]) -> None:
        """Patch top-level metadata while preserving all unspecified fields."""
        for key, value in patch.items():
            self._payload[str(key)] = deepcopy(value)

    def clear_identity_for_copy(self) -> None:
        """Remove identity/timestamp fields when preparing a copy for import.

        Import behavior is GenFarmer-version-specific, so callers should use this
        only when they intentionally want a new app rather than updating the
        original export.
        """
        for key in ("id", "userId", "createdAt", "updatedAt", "expiredAt"):
            self._payload.pop(key, None)
        script = self._payload.get("script")
        if isinstance(script, dict):
            script.pop("id", None)

    def save(self, path: str | Path, *, compact: bool = False) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if compact:
            text = json.dumps(self._payload, ensure_ascii=False, separators=(",", ":"))
        else:
            text = json.dumps(self._payload, ensure_ascii=False, indent=2)
        output.write_text(text, encoding="utf-8")
