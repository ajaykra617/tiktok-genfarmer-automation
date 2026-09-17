#!/usr/bin/env python3
"""FYP-variant-aware wrapper for the one-command TikTok client demo.

TikTok may surface legitimate For You variants such as LIVE cards that do not
contain the strict selector used to qualify ordinary video cards. This wrapper
keeps the original demo orchestration and recovery budgets, but replaces the FYP
proof/restoration hooks so valid alternate FYP content is advanced past instead
of being misclassified as an app stall.
"""
from __future__ import annotations

import time

import tiktok_client_demo as demo

from genfarmer_automation.fyp_context import prove_fyp_context
from genfarmer_automation.native_ui import NativeUiError
from genfarmer_automation.warmup_features import find_feed_source_node

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


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
        gate, batch = demo._gate(supervisor, device, candidate, preferred_port)
        last_counts = gate.counts
        if gate.passed:
            return gate, batch

        # One read-only settle retry before making any decision.
        time.sleep(0.7)
        gate, batch = demo._gate(supervisor, device, candidate, preferred_port)
        last_counts = gate.counts
        if gate.passed:
            return gate, batch

        proof = prove_fyp_context(batch.snapshots[-1], package=TIKTOK_PACKAGE)
        if not proof.passed:
            raise RuntimeError(
                f"qualified FYP anchor is absent and FYP context is not semantically proven; counts={last_counts}"
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
    """Restore a strict FYP checkpoint without false restarts on LIVE cards."""
    last_counts = None

    for attempt in range(max_actions + 1):
        supervisor.ensure_ready(apply=True)
        gate, batch = demo._gate(supervisor, device, candidate, preferred_port)
        last_counts = gate.counts
        if gate.passed:
            return gate, batch, attempt

        xml = batch.snapshots[-1]
        proof = prove_fyp_context(xml, package=TIKTOK_PACKAGE)
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
            actions.tap(*for_you.center)
            time.sleep(1.25)
        else:
            actions.keyevent(4)
            time.sleep(0.9)

    raise RuntimeError(
        f"qualified FYP could not be restored within bounded semantic recovery; last counts={last_counts}"
    )


# The original runner resolves these names dynamically when its main() executes.
demo._prove_feed = resilient_prove_feed
demo._restore_fyp = resilient_restore_fyp


if __name__ == "__main__":
    raise SystemExit(demo.main())
