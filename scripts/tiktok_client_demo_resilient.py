#!/usr/bin/env python3
"""FYP-variant-aware wrapper for the one-command TikTok client demo.

TikTok may surface legitimate For You variants such as LIVE cards that do not
contain the strict selector used to qualify ordinary video cards. This wrapper
keeps the original demo orchestration and recovery budgets, but replaces the FYP
proof/restoration hooks so valid alternate FYP content is advanced past instead
of being misclassified as an app stall.

A clean TikTok restart proves only that the package is alive/foreground. The
feed may still be booting for several seconds. Immediately demanding the strict
ordinary-video selector after relaunch caused false failures, so this wrapper
also gives a newly restarted process a bounded read-only settle window before
performing navigation or declaring the checkpoint unhealthy.
"""
from __future__ import annotations

import time

import tiktok_client_demo as demo

from genfarmer_automation.fyp_context import prove_fyp_context
from genfarmer_automation.native_ui import NativeUiError
from genfarmer_automation.warmup_features import find_feed_source_node

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"

# Single-process demo runner: remember which hard-restart generation has already
# received the longer post-launch settle window. This avoids adding long waits to
# every normal profile/search return later in the session.
_SETTLED_RESTART_COUNT = 0


def _restart_count(supervisor) -> int:
    snapshot = supervisor.snapshot().recovery_budget_used
    return int(snapshot.get("restart_app", 0))


def _read_fyp_state(supervisor, device: str, candidate, preferred_port: int):
    gate, batch = demo._gate(supervisor, device, candidate, preferred_port)
    proof = prove_fyp_context(batch.snapshots[-1], package=TIKTOK_PACKAGE)
    return gate, batch, proof


def _settle_fyp_state(supervisor, device: str, candidate, preferred_port: int):
    """Wait read-only for FYP content after a fresh hard restart.

    Foreground process readiness is not the same as content readiness. After a
    restart TikTok can spend several seconds with a readable but incomplete UI.
    We therefore poll without taps/swipes first. Normal transitions get only a
    short two-read settle; a new hard-restart generation gets up to ~12 seconds.
    """
    global _SETTLED_RESTART_COUNT

    current_restarts = _restart_count(supervisor)
    post_restart = current_restarts > _SETTLED_RESTART_COUNT
    checks = 12 if post_restart else 2
    interval = 1.0 if post_restart else 0.7
    last = None

    if post_restart:
        print("      POST-RESTART SETTLE: waiting for TikTok feed content")

    for index in range(checks):
        supervisor.ensure_ready(apply=True)
        gate, batch, proof = _read_fyp_state(
            supervisor, device, candidate, preferred_port
        )
        last = (gate, batch, proof)
        if gate.passed or proof.passed:
            if post_restart:
                print(
                    f"      POST-RESTART SETTLE: feed ready after {index + 1} check(s)"
                )
                _SETTLED_RESTART_COUNT = current_restarts
            return last
        if index + 1 < checks:
            time.sleep(interval)

    if post_restart:
        # Mark the generation as settled even when no feed proof appeared. The
        # caller can now use bounded semantic BACK/For You recovery rather than
        # repeatedly waiting the full launch window.
        _SETTLED_RESTART_COUNT = current_restarts
        print("      POST-RESTART SETTLE: foreground healthy but feed not proven yet")

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
    """Return to a strict ordinary-video anchor, skipping valid FYP variants."""
    max_variant_advances = 3
    last_counts = None

    for advance in range(max_variant_advances + 1):
        gate, batch, proof = _settle_fyp_state(
            supervisor, device, candidate, preferred_port
        )
        last_counts = gate.counts
        if gate.passed:
            return gate, batch

        if not proof.passed:
            raise RuntimeError(
                "qualified FYP anchor is absent and FYP context is not "
                f"semantically proven after settle; counts={last_counts}"
            )

        if advance >= max_variant_advances:
            raise RuntimeError(
                "valid alternate FYP content persisted beyond the bounded advance budget"
            )

        print(
            "      FYP VARIANT: "
            + ",".join(proof.signals)
            + "; advancing without restarting TikTok"
        )
        _advance_alternate_fyp(supervisor)

    raise RuntimeError(f"qualified FYP anchor was not restored; counts={last_counts}")


def resilient_restore_fyp(
    supervisor,
    actions,
    device: str,
    candidate,
    preferred_port: int,
    *,
    max_actions: int = 5,
):
    """Restore a strict FYP checkpoint without false restarts on launch/LIVE."""
    last_counts = None

    for attempt in range(max_actions + 1):
        gate, batch, proof = _settle_fyp_state(
            supervisor, device, candidate, preferred_port
        )
        last_counts = gate.counts
        if gate.passed:
            return gate, batch, attempt

        xml = batch.snapshots[-1]
        if proof.passed:
            if attempt >= max_actions:
                break
            print(
                "      FYP VARIANT: "
                + ",".join(proof.signals)
                + "; seeking ordinary feed card"
            )
            _advance_alternate_fyp(supervisor)
            continue

        try:
            for_you = find_feed_source_node(xml, "for-you", package=TIKTOK_PACKAGE)
        except NativeUiError:
            for_you = None

        if attempt >= max_actions:
            break
        if for_you is not None:
            print("      FYP RESTORE: For You tab visible; selecting after settle")
            actions.tap(*for_you.center)
            time.sleep(1.25)
        else:
            print("      FYP RESTORE: feed tab unavailable; bounded BACK recovery")
            actions.keyevent(4)
            time.sleep(0.9)

    raise RuntimeError(
        "qualified FYP could not be restored within bounded semantic recovery; "
        f"last counts={last_counts}"
    )


# The original runner resolves these names dynamically when its main() executes.
demo._prove_feed = resilient_prove_feed
demo._restore_fyp = resilient_restore_fyp


if __name__ == "__main__":
    raise SystemExit(demo.main())
