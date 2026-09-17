#!/usr/bin/env python3
"""FYP-state-aware wrapper for the one-command TikTok client demo.

TikTok can legitimately surface multiple For You card types (ordinary video,
LIVE, photo/image, sponsored/shop/repost variants) and can also spend several
seconds in a readable loading state after relaunch. The strict candidate anchor
remains the primary proof for an ordinary video card, while this wrapper adds a
conservative state machine around it so valid alternate content is advanced
past, loading states are waited out, off-FYP states are restored, and only true
checkpoint failures escalate to a bounded clean app restart.
"""
from __future__ import annotations

import time

import tiktok_client_demo as demo

from genfarmer_automation.fyp_context import FypState, classify_fyp_context
from genfarmer_automation.native_ui import NativeUiError
from genfarmer_automation.warmup_features import find_feed_source_node

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"

_SETTLED_RESTART_COUNT = 0


def _restart_count(supervisor) -> int:
    snapshot = supervisor.snapshot().recovery_budget_used
    return int(snapshot.get("restart_app", 0))


def _read_fyp_state(supervisor, device: str, candidate, preferred_port: int):
    gate, batch = demo._gate(supervisor, device, candidate, preferred_port)
    proof = classify_fyp_context(batch.snapshots[-1], package=TIKTOK_PACKAGE)
    return gate, batch, proof


def _settle_fyp_state(supervisor, device: str, candidate, preferred_port: int):
    """Wait read-only for usable TikTok content, especially after a hard restart."""
    global _SETTLED_RESTART_COUNT

    current_restarts = _restart_count(supervisor)
    post_restart = current_restarts > _SETTLED_RESTART_COUNT
    checks = 15 if post_restart else 3
    interval = 1.0 if post_restart else 0.6
    last = None

    if post_restart:
        print("      POST-RESTART SETTLE: waiting for stable TikTok content")

    for index in range(checks):
        supervisor.ensure_ready(apply=True)
        gate, batch, proof = _read_fyp_state(supervisor, device, candidate, preferred_port)
        last = (gate, batch, proof)
        if gate.passed or proof.state is FypState.CONTENT:
            if post_restart:
                print(f"      POST-RESTART SETTLE: content ready after {index + 1} check(s)")
                _SETTLED_RESTART_COUNT = current_restarts
            return last

        # A readable For You shell with no content is not a crash. Wait without
        # mutating until the bounded settle window expires.
        if proof.state is FypState.LOADING:
            if post_restart and index in {2, 5, 9}:
                print(f"      POST-RESTART SETTLE: still loading ({index + 1}/{checks})")
            if index + 1 < checks:
                time.sleep(interval)
            continue

        # OFF_FYP / UNKNOWN should not consume the full loading window; the
        # caller owns bounded semantic restoration for those states.
        break

    if post_restart:
        _SETTLED_RESTART_COUNT = current_restarts
        print("      POST-RESTART SETTLE: process healthy; semantic restore required")

    if last is None:
        raise RuntimeError("TikTok FYP state could not be observed")
    return last


def _advance_alternate_fyp(supervisor) -> None:
    if supervisor.actions is None:
        raise RuntimeError("FYP variant recovery requires bounded Android actions")
    frame = supervisor.run_read_only(supervisor.observer.capture_raw_frame)
    supervisor.actions.swipe_up_relative(width=frame.width, height=frame.height)
    time.sleep(1.0)
    supervisor.ensure_ready(apply=True)


def resilient_prove_feed(supervisor, device: str, candidate, preferred_port: int):
    """Reach an ordinary-video checkpoint while tolerating valid FYP variants."""
    max_variant_advances = 5
    last_counts = None

    for advance in range(max_variant_advances + 1):
        gate, batch, proof = _settle_fyp_state(supervisor, device, candidate, preferred_port)
        last_counts = gate.counts
        if gate.passed:
            return gate, batch

        if proof.state is FypState.CONTENT:
            if advance >= max_variant_advances:
                raise RuntimeError("alternate FYP content persisted beyond bounded advance budget")
            print(
                "      FYP VARIANT: "
                + ",".join(proof.signals)
                + "; advancing safely without restarting TikTok"
            )
            _advance_alternate_fyp(supervisor)
            continue

        if proof.state is FypState.LOADING:
            raise RuntimeError(
                f"TikTok FYP remained in loading state after bounded settle; counts={last_counts}"
            )

        raise RuntimeError(
            "qualified FYP anchor is absent and a valid FYP content state was not proven; "
            f"state={proof.state.value} counts={last_counts}"
        )

    raise RuntimeError(f"qualified FYP anchor was not restored; counts={last_counts}")


def resilient_restore_fyp(
    supervisor,
    actions,
    device: str,
    candidate,
    preferred_port: int,
    *,
    max_actions: int = 6,
):
    """Restore a strict ordinary-video FYP checkpoint using a bounded state machine."""
    last_counts = None

    for attempt in range(max_actions + 1):
        gate, batch, proof = _settle_fyp_state(supervisor, device, candidate, preferred_port)
        last_counts = gate.counts
        if gate.passed:
            return gate, batch, attempt

        xml = batch.snapshots[-1]
        if proof.state is FypState.CONTENT:
            if attempt >= max_actions:
                break
            print(
                "      FYP VARIANT: "
                + ",".join(proof.signals)
                + "; seeking ordinary feed card"
            )
            _advance_alternate_fyp(supervisor)
            continue

        if proof.state is FypState.LOADING:
            # _settle_fyp_state already gave loading a bounded wait. Do not tap a
            # loading UI. Escalate to checkpoint recovery instead.
            raise RuntimeError(
                f"TikTok FYP remained loading after bounded settle; last counts={last_counts}"
            )

        try:
            for_you = find_feed_source_node(xml, "for-you", package=TIKTOK_PACKAGE)
        except NativeUiError:
            for_you = None

        if attempt >= max_actions:
            break
        if for_you is not None:
            print("      FYP RESTORE: selecting visible For You tab")
            actions.tap(*for_you.center)
            time.sleep(1.25)
        else:
            print("      FYP RESTORE: off-feed state; bounded BACK recovery")
            actions.keyevent(4)
            time.sleep(0.9)

    raise RuntimeError(
        "qualified FYP could not be restored within bounded semantic recovery; "
        f"last counts={last_counts}"
    )


# The original runner resolves these names dynamically when main() executes.
demo._prove_feed = resilient_prove_feed
demo._restore_fyp = resilient_restore_fyp


if __name__ == "__main__":
    raise SystemExit(demo.main())
