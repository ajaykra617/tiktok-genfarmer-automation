"""Bounded recovery for Android runtime permission dialogs shown over TikTok.

The warm-up lane does not need contacts access. When Android's permission
controller is the foreground interrupt, we first try to choose the exact deny
control for TikTok from fresh hierarchy evidence. If Android's UIAutomator dump
is temporarily unavailable while the permission controller owns the window, we
use one KEYCODE_BACK dismissal as a safe fallback: it cannot grant the requested
permission and we still require TikTok foreground/no-interrupt state afterward.

We never grant permissions and never tap guessed coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Protocol

from .adb_actions import AdbActions
from .adb_observer import AdbObserver, DeviceObservation, InterruptKind
from .hierarchy_runtime import HierarchyRuntimeError, capture_uiautomator_once
from .native_ui import UiNode, collect_nodes


class PermissionRecoveryError(RuntimeError):
    pass


_DENY_IDS = (
    "permission_deny_button",
    "permission_deny_and_dont_ask_again_button",
    "permission_deny_selected_button",
)
KEYCODE_BACK = 4


class ObserverLike(Protocol):
    def observe(self) -> DeviceObservation: ...


class ActionsLike(Protocol):
    def tap(self, x: int, y: int): ...
    def keyevent(self, keycode: int): ...


@dataclass(frozen=True)
class PermissionRecoveryResult:
    success: bool
    handled: bool
    initial: DeviceObservation
    final: DeviceObservation
    reason: str
    deny_resource_id: str | None = None


def _mentions_tiktok(nodes: list[UiNode]) -> bool:
    for node in nodes:
        joined = f"{node.text} {node.content_desc}".casefold()
        if "tiktok" in joined:
            return True
    return False


def find_tiktok_permission_deny_node(xml: str) -> UiNode:
    nodes = collect_nodes(xml)
    if not _mentions_tiktok(nodes):
        raise PermissionRecoveryError("permission hierarchy does not identify TikTok")

    by_suffix: dict[str, list[UiNode]] = {value: [] for value in _DENY_IDS}
    for node in nodes:
        suffix = node.resource_id.rsplit("/", 1)[-1]
        if suffix in by_suffix and node.enabled:
            by_suffix[suffix].append(node)

    for suffix in _DENY_IDS:
        matches = by_suffix[suffix]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise PermissionRecoveryError(
                f"permission hierarchy contains multiple {suffix} controls"
            )
    raise PermissionRecoveryError("no known Android permission-deny control found")


def _poll_for_tiktok(
    obs: ObserverLike,
    *,
    initial: DeviceObservation,
    handled: bool,
    reason_ok: str,
    deny_resource_id: str | None,
    poll_seconds: float,
    max_polls: int,
) -> PermissionRecoveryResult:
    final = initial
    for index in range(max_polls):
        final = obs.observe()
        if (
            final.interrupt is InterruptKind.NONE
            and final.adb_state == "device"
            and final.tiktok_foreground
        ):
            return PermissionRecoveryResult(
                True,
                handled,
                initial,
                final,
                reason_ok,
                deny_resource_id=deny_resource_id,
            )
        if final.interrupt not in {
            InterruptKind.NONE,
            InterruptKind.ANDROID_PERMISSION_DIALOG,
        }:
            return PermissionRecoveryResult(
                False,
                handled,
                initial,
                final,
                f"different interrupt appeared during permission recovery: {final.interrupt.value}",
                deny_resource_id=deny_resource_id,
            )
        if index + 1 < max_polls and poll_seconds:
            time.sleep(poll_seconds)

    return PermissionRecoveryResult(
        False,
        handled,
        initial,
        final,
        "permission dialog recovery did not return to a healthy TikTok foreground state",
        deny_resource_id=deny_resource_id,
    )


def recover_tiktok_permission_dialog(
    device: str,
    *,
    observer: ObserverLike | None = None,
    actions: ActionsLike | None = None,
    settle_seconds: float = 0.35,
    poll_seconds: float = 0.25,
    max_polls: int = 8,
) -> PermissionRecoveryResult:
    if settle_seconds < 0 or poll_seconds < 0 or max_polls < 1:
        raise ValueError("invalid permission-recovery timing arguments")

    obs = observer or AdbObserver(device)
    act = actions or AdbActions(device)
    initial = obs.observe()
    if initial.interrupt is not InterruptKind.ANDROID_PERMISSION_DIALOG:
        return PermissionRecoveryResult(
            True,
            False,
            initial,
            initial,
            "no Android permission dialog is foreground",
        )

    try:
        xml = capture_uiautomator_once(device, timeout=10.0)
    except HierarchyRuntimeError:
        # Android can temporarily block/kill UIAutomator while the permission
        # controller owns the top window. One BACK key is safe here: unlike an
        # Allow button it cannot grant the requested permission. We still fail
        # closed unless TikTok healthy foreground state is proven afterward.
        act.keyevent(KEYCODE_BACK)
        if settle_seconds:
            time.sleep(settle_seconds)
        return _poll_for_tiktok(
            obs,
            initial=initial,
            handled=True,
            reason_ok="TikTok permission dialog dismissed with safe BACK fallback and TikTok foreground restored",
            deny_resource_id=None,
            poll_seconds=poll_seconds,
            max_polls=max_polls,
        )

    try:
        target = find_tiktok_permission_deny_node(xml)
    except PermissionRecoveryError as exc:
        return PermissionRecoveryResult(False, False, initial, initial, str(exc))

    x, y = target.center
    act.tap(x, y)
    if settle_seconds:
        time.sleep(settle_seconds)

    return _poll_for_tiktok(
        obs,
        initial=initial,
        handled=True,
        reason_ok="TikTok permission dialog denied and TikTok foreground restored",
        deny_resource_id=target.resource_id,
        poll_seconds=poll_seconds,
        max_polls=max_polls,
    )
