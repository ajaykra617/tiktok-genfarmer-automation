#!/usr/bin/env python3
"""One-command TikTok Warm-up + Boost Preparation client demo.

This is intentionally a presentation runner, not a hidden shortcut. It uses
qualified semantic gates and bounded runtime recovery, performs only passive
Warm-up behavior, then runs the saved Boost Phase A standard preset through the
READY_FOR_PUBLISH boundary. It never likes, follows, replies, sends DMs, or
performs the final Post action.

TikTok can occasionally wedge, crash, or stop producing a healthy accessibility
hierarchy even when the workflow itself is correct. Every replayable demo stage
therefore starts from a known checkpoint and may perform one clean app-process
restart before replaying that passive stage. The whole demo also has a global
hard-restart budget. Unknown semantic failures still fail closed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_actions import AdbActions  # noqa: E402
from genfarmer_automation.adb_observer import AdbObserver  # noqa: E402
from genfarmer_automation.app_resilience import (  # noqa: E402
    StageRecoveryEvent,
    run_checkpointed_stage,
)
from genfarmer_automation.client_demo_plan import build_client_demo_plan  # noqa: E402
from genfarmer_automation.feed_anchor_qualification import candidates_from_payload  # noqa: E402
from genfarmer_automation.hierarchy_runtime import capture_hierarchy_batch  # noqa: E402
from genfarmer_automation.native_ui import NativeUiError  # noqa: E402
from genfarmer_automation.runtime_recovery import RecoveryBudget, RecoveryLimits  # noqa: E402
from genfarmer_automation.runtime_supervisor import TikTokRuntimeSupervisor  # noqa: E402
from genfarmer_automation.selector_gate import assess_selector_gate  # noqa: E402
from genfarmer_automation.warmup_features import (  # noqa: E402
    find_comments_node,
    find_creator_profile_entry,
    find_feed_source_node,
    prove_comments_context,
    prove_profile_context,
)
from genfarmer_automation.warmup_session import load_shareable  # noqa: E402

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _capture(supervisor: TikTokRuntimeSupervisor, device: str, preferred_port: int, *, count: int = 1):
    return supervisor.run_read_only(
        lambda: capture_hierarchy_batch(
            device,
            count=count,
            interval=0.12 if count > 1 else 0.0,
            preferred_port=preferred_port,
            helper_timeout=4.0,
            max_ports=12,
        )
    )


def _gate(supervisor, device: str, candidate, preferred_port: int):
    batch = _capture(supervisor, device, preferred_port, count=2)
    gate = assess_selector_gate(candidate, batch.snapshots, package=TIKTOK_PACKAGE)
    return gate, batch


def _prove_feed(supervisor, device: str, candidate, preferred_port: int):
    gate, batch = _gate(supervisor, device, candidate, preferred_port)
    if gate.passed:
        return gate, batch
    # A readable hierarchy with a missing selector may simply be a UI settle
    # race. One delayed read is allowed; stage-level hard recovery is separate.
    time.sleep(0.8)
    gate, batch = _gate(supervisor, device, candidate, preferred_port)
    if not gate.passed:
        raise RuntimeError(f"qualified FYP anchor is absent; counts={gate.counts}")
    return gate, batch


def _restore_fyp(supervisor, actions: AdbActions, device: str, candidate, preferred_port: int, *, max_actions: int = 4):
    """Restore and prove FYP without tapping it when already qualified."""
    for attempt in range(max_actions + 1):
        supervisor.ensure_ready(apply=True)
        gate, batch = _gate(supervisor, device, candidate, preferred_port)
        if gate.passed:
            return gate, batch, attempt
        xml = batch.snapshots[-1]

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

    raise RuntimeError("qualified FYP could not be restored within bounded semantic recovery")


def _watch(supervisor, seconds: float) -> None:
    remaining = float(seconds)
    while remaining > 0:
        supervisor.ensure_ready(apply=True)
        chunk = min(1.0, remaining)
        time.sleep(chunk)
        remaining -= chunk


def _warm_scroll(
    *,
    supervisor,
    observer,
    actions,
    device,
    candidate,
    preferred_port,
    watch_seconds,
    restart_stage,
    on_recovery,
):
    rows = []
    for index, seconds in enumerate(watch_seconds, start=1):
        label = f"warm-scroll-video-{index}"

        def operation():
            pre_gate, _, restores = _restore_fyp(
                supervisor, actions, device, candidate, preferred_port
            )
            print(f"  [{index}/{len(watch_seconds)}] FYP PASS; watch {seconds:.2f}s")
            _watch(supervisor, seconds)
            frame = supervisor.run_read_only(observer.capture_raw_frame)
            actions.swipe_up_relative(width=frame.width, height=frame.height)
            time.sleep(1.0)
            supervisor.ensure_ready(apply=True)
            post_gate, _ = _prove_feed(supervisor, device, candidate, preferred_port)
            print(f"      swipe PASS pre={pre_gate.counts} post={post_gate.counts}")
            return {"video": index, "watch_seconds": seconds, "restores": restores}

        row = run_checkpointed_stage(
            label,
            operation,
            restart=restart_stage,
            max_restarts=1,
            on_recovery=on_recovery,
        )
        rows.append(row)
    return rows


def _resolve_target(supervisor, observer, actions, device, candidate, preferred_port, finder, *, max_feed_advances: int = 2):
    """Find one passive control, advancing only to another qualified feed item."""
    for attempt in range(max_feed_advances + 1):
        _, batch, _ = _restore_fyp(supervisor, actions, device, candidate, preferred_port)
        xml = batch.snapshots[-1]
        try:
            return finder(xml, package=TIKTOK_PACKAGE)
        except NativeUiError:
            if attempt >= max_feed_advances:
                raise
            frame = supervisor.run_read_only(observer.capture_raw_frame)
            actions.swipe_up_relative(width=frame.width, height=frame.height)
            time.sleep(1.0)
    raise RuntimeError("passive feed target could not be resolved")


def _profile_feature(*, supervisor, observer, actions, device, candidate, preferred_port, dwell):
    target = _resolve_target(
        supervisor, observer, actions, device, candidate, preferred_port, find_creator_profile_entry
    )
    actions.tap(*target.center)
    time.sleep(1.5)
    supervisor.ensure_ready(apply=True)
    batch = _capture(supervisor, device, preferred_port)
    proof = prove_profile_context(batch.snapshots[-1], package=TIKTOK_PACKAGE)
    if not proof.passed:
        raise RuntimeError("creator profile context was not semantically proven")
    _watch(supervisor, dwell)
    actions.keyevent(4)
    time.sleep(1.0)
    _restore_fyp(supervisor, actions, device, candidate, preferred_port)
    return {"status": "PASS", "proof": list(proof.matched_terms)}


def _comments_feature(*, supervisor, observer, actions, device, candidate, preferred_port, dwell):
    target = _resolve_target(
        supervisor, observer, actions, device, candidate, preferred_port, find_comments_node
    )
    actions.tap(*target.center)
    time.sleep(1.2)
    supervisor.ensure_ready(apply=True)
    batch = _capture(supervisor, device, preferred_port)
    proof = prove_comments_context(batch.snapshots[-1], package=TIKTOK_PACKAGE)
    if not proof.passed:
        raise RuntimeError("comments context was not semantically proven")
    _watch(supervisor, dwell)
    actions.keyevent(4)
    time.sleep(1.0)
    _restore_fyp(supervisor, actions, device, candidate, preferred_port)
    return {"status": "PASS", "proof": list(proof.matched_terms)}


def _niche_feature(*, kind: str, value: str, device: str, preferred_port: int, private: Path, supervisor, actions, candidate, dwell):
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "tiktok_boost_explore.py"),
        "--type", kind,
        "--value", value,
        "--device", device,
        "--preferred-hierarchy-port", str(preferred_port),
        "--apply",
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180.0,
        check=False,
    )
    output = proc.stdout or ""
    (private / f"warmup-{kind}.log").write_text(output, encoding="utf-8", errors="replace")
    payload = load_shareable(ROOT, output)
    if proc.returncode != 0 or not isinstance(payload, dict) or payload.get("status") != "PASS":
        reason = payload.get("reason") if isinstance(payload, dict) else None
        raise RuntimeError(f"{kind} exploration failed: {reason or 'child did not reach PASS'}")
    _watch(supervisor, dwell)
    _restore_fyp(supervisor, actions, device, candidate, preferred_port)
    return {"status": "PASS", "context_verified": payload.get("context_verified")}


def _run_boost(*, device: str, proxy_id: str, media: Path, seed: int, preferred_port: int, private: Path):
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "tiktok_boost_prepare_preset.py"),
        "--preset", "phase_a_standard",
        "--device", device,
        "--proxy-id", proxy_id,
        "--media", str(media),
        "--seed", str(seed),
        "--preferred-hierarchy-port", str(preferred_port),
        "--ready",
        "--apply",
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=900.0,
        check=False,
    )
    output = proc.stdout or ""
    (private / "boost.log").write_text(output, encoding="utf-8", errors="replace")
    payload = load_shareable(ROOT, output)
    if proc.returncode != 0 or not isinstance(payload, dict) or payload.get("status") != "READY_FOR_PUBLISH":
        reason = payload.get("reason") if isinstance(payload, dict) else None
        raise RuntimeError(f"Boost preparation failed: {reason or 'child did not reach READY_FOR_PUBLISH'}")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="One-command live TikTok Warm-up + Boost client demo")
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--device", required=True)
    ap.add_argument("--proxy-id", required=True)
    ap.add_argument("--media", type=Path, required=True)
    ap.add_argument("--keyword", default="technology")
    ap.add_argument("--hashtag", default="technology")
    ap.add_argument("--videos", type=int, default=3)
    ap.add_argument("--watch-min", type=float, default=4.0)
    ap.add_argument("--watch-max", type=float, default=7.0)
    ap.add_argument("--dwell", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-app-restarts", type=int, default=3)
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    try:
        plan = build_client_demo_plan(
            seed=args.seed,
            videos=args.videos,
            watch_min_seconds=args.watch_min,
            watch_max_seconds=args.watch_max,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.dwell < 0 or args.dwell > 30:
        print("ERROR: --dwell must be between 0 and 30 seconds", file=sys.stderr)
        return 2
    if not 0 <= args.max_app_restarts <= 5:
        print("ERROR: --max-app-restarts must be between 0 and 5", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-client-demo-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-client-demo.shareable.json"
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "seed": args.seed,
        "candidate_index": args.candidate,
        "warmup_feature_order": list(plan.feature_order),
        "warmup_watch_seconds": list(plan.watch_seconds),
        "passive_only": True,
        "engagement_actions": 0,
        "publishing_ui_entered": False,
        "final_post_action": False,
        "following_selected": False,
        "following_note": "not selected in this demo preset because the qualification account has no followed creators",
        "max_app_restarts": args.max_app_restarts,
    }

    if not args.apply:
        result["status"] = "DRY_RUN_READY"
        _write_json(shareable, result)
        print("TIKTOK CLIENT DEMO")
        print("Status:                     DRY_RUN_READY")
        print(f"Warm-up order:              {' -> '.join(plan.feature_order)}")
        print(f"Warm-scroll videos:         {len(plan.watch_seconds)}")
        print(f"Hard app restart budget:    {args.max_app_restarts}")
        print("Boost preset:               phase_a_standard")
        print("Final Post action:          NONE")
        return 0

    recovery_events: list[dict[str, object]] = []

    try:
        raw = json.loads(args.candidates.read_text(encoding="utf-8"))
        candidates = candidates_from_payload(raw)
        if not 1 <= args.candidate <= len(candidates):
            raise RuntimeError("candidate file does not contain requested candidate")
        candidate = candidates[args.candidate - 1]
        if not args.media.is_file():
            raise RuntimeError("demo media file does not exist")

        observer = AdbObserver(args.device)
        actions = AdbActions(args.device)
        budget = RecoveryBudget(
            RecoveryLimits(
                app_restarts=args.max_app_restarts,
                hierarchy_retries=6,
                adb_retries=3,
                foreground_restores=4,
                permission_recoveries=2,
            )
        )
        supervisor = TikTokRuntimeSupervisor(
            args.device,
            observer=observer,
            actions=actions,
            budget=budget,
        )

        def restart_stage(reason: str) -> None:
            print("      RECOVERY: TikTok appears stalled; clean process restart")
            supervisor.hard_restart(reason=reason, settle_seconds=2.0)
            time.sleep(1.0)

        def on_recovery(event: StageRecoveryEvent) -> None:
            recovery_events.append(
                {
                    "stage": event.label,
                    "restart_number": event.restart_number,
                    "reason": event.reason,
                }
            )
            print(f"      RECOVERY COMPLETE: replaying {event.label} from checkpoint")

        print("=" * 78)
        print("TIKTOK CLIENT DEMO - WARM-UP + BOOST PREPARATION")
        print("=" * 78)
        print("[1/3] Runtime + FYP preflight")
        supervisor.ensure_ready(apply=True)
        gate, _, restores = run_checkpointed_stage(
            "runtime-fyp-preflight",
            lambda: _restore_fyp(
                supervisor, actions, args.device, candidate, args.preferred_hierarchy_port
            ),
            restart=restart_stage,
            max_restarts=1,
            on_recovery=on_recovery,
        )
        print(f"      PASS FYP={gate.counts} restore_actions={restores}")

        print("[2/3] WARM-UP MODE")
        warm_rows = _warm_scroll(
            supervisor=supervisor,
            observer=observer,
            actions=actions,
            device=args.device,
            candidate=candidate,
            preferred_port=args.preferred_hierarchy_port,
            watch_seconds=plan.watch_seconds,
            restart_stage=restart_stage,
            on_recovery=on_recovery,
        )
        feature_results = {}
        for index, feature in enumerate(plan.feature_order, start=1):
            print(f"  feature {index}/{len(plan.feature_order)}: {feature}")

            if feature == "profile":
                operation = lambda: _profile_feature(
                    supervisor=supervisor,
                    observer=observer,
                    actions=actions,
                    device=args.device,
                    candidate=candidate,
                    preferred_port=args.preferred_hierarchy_port,
                    dwell=args.dwell,
                )
            elif feature == "comments":
                operation = lambda: _comments_feature(
                    supervisor=supervisor,
                    observer=observer,
                    actions=actions,
                    device=args.device,
                    candidate=candidate,
                    preferred_port=args.preferred_hierarchy_port,
                    dwell=args.dwell,
                )
            elif feature == "keyword":
                operation = lambda: _niche_feature(
                    kind="keyword",
                    value=args.keyword,
                    device=args.device,
                    preferred_port=args.preferred_hierarchy_port,
                    private=private,
                    supervisor=supervisor,
                    actions=actions,
                    candidate=candidate,
                    dwell=args.dwell,
                )
            else:
                operation = lambda: _niche_feature(
                    kind="hashtag",
                    value=args.hashtag,
                    device=args.device,
                    preferred_port=args.preferred_hierarchy_port,
                    private=private,
                    supervisor=supervisor,
                    actions=actions,
                    candidate=candidate,
                    dwell=args.dwell,
                )

            payload = run_checkpointed_stage(
                f"warmup-{feature}",
                operation,
                restart=restart_stage,
                max_restarts=1,
                on_recovery=on_recovery,
            )
            feature_results[feature] = payload
            print("      PASS")

        result["warmup_status"] = "PASS"
        result["warmup_scroll"] = warm_rows
        result["warmup_features"] = feature_results
        result["runtime_recovery_counts"] = supervisor.snapshot().recovery_budget_used
        result["app_restart_events"] = recovery_events
        print("      WARM-UP STATUS: PASS")

        print("[3/3] BOOST MODE")
        boost = run_checkpointed_stage(
            "boost-preparation",
            lambda: _run_boost(
                device=args.device,
                proxy_id=args.proxy_id,
                media=args.media,
                seed=args.seed,
                preferred_port=args.preferred_hierarchy_port,
                private=private,
            ),
            restart=restart_stage,
            max_restarts=1,
            on_recovery=on_recovery,
        )
        result.update(
            {
                "status": "READY_FOR_PUBLISH",
                "boost_status": "READY_FOR_PUBLISH",
                "boost_explore_status": boost.get("explore_status"),
                "boost_duplicate_guard_pass": boost.get("duplicate_guard_pass"),
                "boost_media_reserved": boost.get("media_reserved"),
                "boost_media_staged": boost.get("media_staged"),
                "runtime_recovery_counts": supervisor.snapshot().recovery_budget_used,
                "app_restart_events": recovery_events,
            }
        )
        _write_json(shareable, result)

        restart_count = supervisor.snapshot().recovery_budget_used.get("restart_app", 0)
        print("-" * 78)
        print("CLIENT DEMO RESULT")
        print("Warm-up mode:               PASS")
        print(f"Warm-scroll videos:         {len(plan.watch_seconds)}/{len(plan.watch_seconds)}")
        print(f"Passive features:           {len(feature_results)}/{len(plan.feature_order)} PASS")
        print("Boost mode:                 READY_FOR_PUBLISH")
        print(f"Hard app restarts:          {restart_count}/{args.max_app_restarts}")
        print("Engagement actions:         NONE")
        print("Publishing UI:              NOT ENTERED")
        print("Final Post action:          NONE")
        print(f"Runtime recoveries:         {supervisor.snapshot().recovery_budget_used or 'NONE'}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except (OSError, json.JSONDecodeError, RuntimeError, subprocess.TimeoutExpired, NativeUiError) as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        result["app_restart_events"] = recovery_events
        if "supervisor" in locals():
            result["runtime_recovery_counts"] = supervisor.snapshot().recovery_budget_used
        _write_json(shareable, result)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
