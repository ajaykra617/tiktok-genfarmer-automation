"""Versioned semantic registry for GenFarmer 2.6.1 script.flow actions.

This module records only actions and field shapes that were observed in a real
GenFarmer-generated flow. It does not contain client selectors, labels, IDs,
commands, or raw proprietary flow payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ActionSpec:
    semantic_kind: str
    family: str
    action: str
    option_types: Mapping[str, str]
    source_position: str | None = None
    target_position: str | None = None
    observed_timeout_type: str | None = None
    confidence: str = "observed-structure"
    notes: str = ""


GENFARMER_VERSION = "2.6.1"

VERIFIED_ACTIONS: dict[str, ActionSpec] = {
    "custom-context-menu:ContextMenu": ActionSpec(
        semantic_kind="custom-context-menu:ContextMenu",
        family="custom-context-menu",
        action="ContextMenu",
        option_types={"casePaths": "object"},
        notes="Observed context/case routing container. Case-path semantics still require differential learning.",
    ),
    "custom:Adb": ActionSpec(
        semantic_kind="custom:Adb",
        family="custom",
        action="Adb",
        option_types={
            "breakpoint": "bool",
            "command": "str",
            "disabled": "bool",
            "nodeLog": "str",
            "nodeSleep": "str",
            "nodeTimeout": "str",
            "outputVariable": "null",
            "timeoutAdbReconnect": "str",
            "timeoutNextNode": "str",
        },
        source_position="right",
        target_position="left",
        notes="Command/outputVariable fields observed. Do not author arbitrary commands until behavior and safety are proven.",
    ),
    "custom:DeepSeek": ActionSpec(
        semantic_kind="custom:DeepSeek",
        family="custom",
        action="DeepSeek",
        option_types={
            "breakpoint": "bool",
            "disabled": "bool",
            "nodeLog": "str",
            "nodeSleep": "str",
            "nodeTimeout": "str",
            "timeoutAdbReconnect": "str",
            "timeoutNextNode": "str",
        },
        source_position="right",
        target_position="left",
        notes="Observed action token only; request/response option semantics still unknown.",
    ),
    "custom:Pause": ActionSpec(
        semantic_kind="custom:Pause",
        family="custom",
        action="Pause",
        option_types={
            "breakpoint": "bool",
            "disabled": "bool",
            "nodeLog": "str",
            "nodeSleep": "str",
            "nodeTimeout": "str",
            "timeout": "str",
            "timeoutAdbReconnect": "str",
            "timeoutFrom": "str",
            "timeoutNextNode": "str",
            "timeoutTo": "str",
            "timeoutType": "str",
        },
        source_position="right",
        target_position="left",
        observed_timeout_type="fixed",
        notes="Fixed timeout mode observed. Random/range semantics still require one-field differential tests.",
    ),
    "custom:Screenshot": ActionSpec(
        semantic_kind="custom:Screenshot",
        family="custom",
        action="Screenshot",
        option_types={
            "breakpoint": "bool",
            "disabled": "bool",
            "nodeLog": "str",
            "nodeSleep": "str",
            "nodeTimeout": "str",
            "timeoutAdbReconnect": "str",
            "timeoutNextNode": "str",
        },
        source_position="right",
        target_position="left",
        notes="Screenshot action observed; storage/output behavior still to prove.",
    ),
    "helper:Variables": ActionSpec(
        semantic_kind="helper:Variables",
        family="helper",
        action="Variables",
        option_types={},
        notes="Helper node observed with empty options object.",
    ),
    "input:Start": ActionSpec(
        semantic_kind="input:Start",
        family="input",
        action="Start",
        option_types={},
        source_position="right",
        target_position="left",
        confidence="observed-structure-and-edge",
        notes="Start node observed as graph entry. Its outgoing edge uses a generated start handle into target successNode.",
    ),
}

OBSERVED_EDGE_PATTERNS = (
    {
        "type": "custom",
        "animated": True,
        "updatable": True,
        "source_handle": "<generated-start-handle>",
        "target_handle": "successNode",
        "meaning": "Start node outbound edge",
    },
    {
        "type": "custom",
        "animated": True,
        "updatable": True,
        "source_handle": "successNode",
        "target_handle": "successNode",
        "meaning": "Normal success-chain edge",
    },
)


def get_action_spec(semantic_kind: str) -> ActionSpec:
    try:
        return VERIFIED_ACTIONS[semantic_kind]
    except KeyError as exc:
        raise KeyError(
            f"GenFarmer {GENFARMER_VERSION} action not verified: {semantic_kind}"
        ) from exc


def is_verified_action(family: str, action: str) -> bool:
    return f"{family}:{action}" in VERIFIED_ACTIONS
