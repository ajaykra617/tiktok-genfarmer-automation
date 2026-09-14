#!/usr/bin/env python3
"""Qualify and run one passive TikTok warm-up feature end to end.

Supported features are intentionally passive:
- switch to For You or Following feed;
- open the current creator profile, dwell, and return;
- open comments, dwell, and return;
- explore a keyword or hashtag, dwell, and return to the qualified feed.

Every action starts from the qualified feed selector and, where the action is
supposed to return, proves the same feed selector after returning. Tap targets
come from fresh runtime hierarchy bounds; missing/ambiguous controls fail closed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_actions import AdbActions  # noqa: E402
from genfarmer_automation.adb_observer import AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.feed_anchor_qualification import candidates_from_payload  # noqa: E402
from genfarmer_automation.hierarchy_runtime import (  # noqa: E402
    HierarchyRuntimeError,
    capture_hierarchy_batch,
)
from genfarmer_automation.native_ui import NativeUiError  # noqa: E402
from genfarmer_automation.permission_recovery import recover_tiktok_permission_dialog  # noqa: E402
from genfarmer_automation.selector_gate import assess_selector_gate  # noqa: E402
from genfarmer_automation.tiktok_runtime import TikTokRuntime  # noqa: E402
from genfarmer_automation.warmup_features import (  # noqa: E402
    find_comments_node,
    find_creator_profile_entry,
    find_feed_source_node,
    prove_comments_context,
    prove_profile_context,
)

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _ready(observer: AdbObserver) -> bool:
    obs = observer.observe()
    return obs.adb_state == "device" and obs.tiktok_foreground and obs.interrupt is InterruptKind.NONE


def _ensure_ready(device: str, observer: AdbObserver, *, apply: bool) -> int:
    obs = observer.observe()
    permission_recoveries = 0
    if obs.interrupt is InterruptKind.ANDROID_PERMISSION_DIALOG:
        if not apply:
            raise RuntimeError("TikTok permission dialog is foreground; use --apply for bounded recovery")
        recovered = recover_tiktok_permission_dialog(device, observer=observer)
        if not recovered.success:
            raise RuntimeError(f"permission recovery failed: {recovered.reason}")
        permission_recoveries += int(recovered.handled)
    if not _ready(observer):
        if not apply:
            raise RuntimeError("TikTok foreground/no-interrupt state not proven")
        recovered = TikTokRuntime(device, observer=observer).ensure_foreground()
        if not recovered.success:
            raise RuntimeError(f"foreground recovery failed: {recovered.reason}")
    if not _ready(observer):
        raise RuntimeError("TikTok foreground/no-interrupt state not proven after recovery")
    return permission_recoveries


def _capture(device: str, *, preferred_port: int, count: int = 1):
    return capture_hierarchy_batch(
        device,
        count=count,
        interval=0.12 if count > 1 else 0.0,
        preferred_port=preferred_port,
        helper_timeout=4.0,
        max_ports=12,
    )


def _feed_gate(device: str, candidate, *, preferred_port: int):
    batch = _capture(device, preferred_port=preferred_port, count=2)
    gate = assess_selector_gate(candidate, batch.snapshots, package=TIKTOK_PACKAGE)
    return gate, batch


def _return_to_feed(
    *,
    device: str,
    actions: AdbActions,
    candidate,
    preferred_port: int,
    max_backs: int = 3,
):
    last_counts = None
    for attempt in range(max_backs + 1):
        try:
            gate, batch = _feed_gate(device, candidate, preferred_port=preferred_port)
            last_counts = gate.counts
            if gate.passed:
                return attempt, gate, batch
        except HierarchyRuntimeError:
            pass
        if attempt == max_backs:
            break
        actions.keyevent(4)  # BACK
        time.sleep(1.2)
    raise RuntimeError(f"qualified feed was not restored after bounded BACK recovery; last counts={last_counts}")


def _run_niche_explore(feature: str, value: str, device: str, preferred_port: int) -> subprocess.CompletedProcess[str]:
    source_type = "keyword" if feature == "keyword" else "hashtag"
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "tiktok_boost_explore.py"),
        "--type", source_type,
        "--value", value,
        "--device", device,
        "--preferred-hierarchy-port", str(preferred_port),
        "--apply",
    ]
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=150.0,
        check=False,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Passive TikTok warm-up feature runner")
    ap.add_argument("candidates", type=Path, help="ranked-candidates.private.json")
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--device", required=True)
    ap.add_argument(
        "--feature",
        choices=("for-you", "following", "profile", "comments", "keyword", "hashtag"),
        required=True,
    )
    ap.add_argument("--value", help="required for keyword/hashtag")
    ap.add_argument("--dwell-min", type=float, default=4.0)
    ap.add_argument("--dwell-max", type=float, default=10.0)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.candidate < 1 or args.dwell_min < 0 or args.dwell_max < args.dwell_min:
        print("ERROR: invalid candidate/dwell arguments", file=sys.stderr)
        return 2
    if args.feature in {"keyword", "hashtag"} and not (args.value or "").strip():
        print("ERROR: --value is required for keyword/hashtag", file=sys.stderr)
        return 2

    seed = args.seed if args.seed is not None else int(time.time())
    dwell = round(random.Random(seed).uniform(args.dwell_min, args.dwell_max), 2)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-warmup-feature-{args.feature}-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-warmup-feature.shareable.json"
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "feature": args.feature,
        "candidate_index": args.candidate,
        "dwell_seconds": dwell,
        "passive_only": True,
        "engagement_actions": 0,
    }

    try:
        raw_candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
        candidates = candidates_from_payload(raw_candidates)
        if not 1 <= args.candidate <= len(candidates):
            raise RuntimeError("candidate file does not contain requested candidate")
        candidate = candidates[args.candidate - 1]

        observer = AdbObserver(args.device)
        actions = AdbActions(args.device)
        permission_recoveries = _ensure_ready(args.device, observer, apply=args.apply)
        pre_gate, pre_batch = _feed_gate(args.device, candidate, preferred_port=args.preferred_hierarchy_port)
        if not pre_gate.passed:
            raise RuntimeError(f"qualified feed precondition failed with counts {pre_gate.counts}")
        (private / "feed-before.xml").write_text(pre_batch.snapshots[-1], encoding="utf-8")
        observer.capture_screenshot(private / "before.png")

        xml = pre_batch.snapshots[-1]
        if args.feature in {"for-you", "following"}:
            target = find_feed_source_node(xml, args.feature, package=TIKTOK_PACKAGE)
            target_kind = "feed-source"
        elif args.feature == "profile":
            target = find_creator_profile_entry(xml, package=TIKTOK_PACKAGE)
            target_kind = "creator-avatar"
        elif args.feature == "comments":
            target = find_comments_node(xml, package=TIKTOK_PACKAGE)
            target_kind = "comments-control"
        else:
            target = None
            target_kind = "search"

        result.update(
            {
                "pre_feed_counts": list(pre_gate.counts),
                "pre_feed_provider": pre_batch.provider,
                "target_kind": target_kind,
                "target_resolved": target is not None or args.feature in {"keyword", "hashtag"},
                "permission_recoveries": permission_recoveries,
            }
        )

        if not args.apply:
            result["status"] = "DRY_RUN_READY"
            _write_json(shareable, result)
            print("=" * 78)
            print("TIKTOK WARM-UP FEATURE")
            print("=" * 78)
            print("Mode:                       DRY-RUN")
            print("Status:                     DRY_RUN_READY")
            print(f"Feature:                    {args.feature}")
            print(f"Target resolved:            {'YES' if result['target_resolved'] else 'NO'}")
            print(f"Feed precondition:          PASS {pre_gate.counts}")
            print("Mutation:                   NONE")
            print(f"Shareable result:           {shareable.relative_to(ROOT)}")
            print("=" * 78)
            return 0

        if args.feature in {"for-you", "following"}:
            actions.tap(*target.center)
            time.sleep(max(1.5, min(dwell, 5.0)))
            post_gate, post_batch = _feed_gate(args.device, candidate, preferred_port=args.preferred_hierarchy_port)
            if not post_gate.passed:
                raise RuntimeError(f"feed source tap did not retain a qualified feed; counts={post_gate.counts}")
            observer.capture_screenshot(private / "after-source.png")
            result.update(
                {
                    "status": "PASS",
                    "context_verified": "qualified_feed_after_source_tap",
                    "post_feed_counts": list(post_gate.counts),
                    "post_feed_provider": post_batch.provider,
                }
            )

        elif args.feature in {"profile", "comments"}:
            actions.tap(*target.center)
            time.sleep(1.5)
            context_batch = _capture(args.device, preferred_port=args.preferred_hierarchy_port, count=1)
            context_xml = context_batch.snapshots[0]
            (private / "context.xml").write_text(context_xml, encoding="utf-8")
            observer.capture_screenshot(private / "context.png")
            proof = (
                prove_profile_context(context_xml, package=TIKTOK_PACKAGE)
                if args.feature == "profile"
                else prove_comments_context(context_xml, package=TIKTOK_PACKAGE)
            )
            if not proof.passed:
                raise RuntimeError(f"{args.feature} context was not proven from fresh hierarchy")
            time.sleep(dwell)
            backs, post_gate, post_batch = _return_to_feed(
                device=args.device,
                actions=actions,
                candidate=candidate,
                preferred_port=args.preferred_hierarchy_port,
            )
            if not _ready(observer):
                raise RuntimeError("TikTok foreground/no-interrupt state not proven after returning to feed")
            observer.capture_screenshot(private / "after-return.png")
            result.update(
                {
                    "status": "PASS",
                    "context_verified": proof.kind,
                    "context_indicators": list(proof.matched_terms),
                    "backs_to_feed": backs,
                    "post_feed_counts": list(post_gate.counts),
                    "post_feed_provider": post_batch.provider,
                }
            )

        else:
            proc = _run_niche_explore(args.feature, args.value.strip(), args.device, args.preferred_hierarchy_port)
            (private / "niche-explore.log").write_text(proc.stdout or "", encoding="utf-8", errors="replace")
            if proc.returncode != 0 or "Status:                     PASS" not in (proc.stdout or ""):
                raise RuntimeError("niche exploration did not reach PASS")
            time.sleep(dwell)
            backs, post_gate, post_batch = _return_to_feed(
                device=args.device,
                actions=actions,
                candidate=candidate,
                preferred_port=args.preferred_hierarchy_port,
                max_backs=4,
            )
            if not _ready(observer):
                raise RuntimeError("TikTok foreground/no-interrupt state not proven after niche return")
            observer.capture_screenshot(private / "after-niche-return.png")
            result.update(
                {
                    "status": "PASS",
                    "context_verified": f"{args.feature}_explore_then_feed_return",
                    "backs_to_feed": backs,
                    "post_feed_counts": list(post_gate.counts),
                    "post_feed_provider": post_batch.provider,
                }
            )

        _write_json(shareable, result)
        print("=" * 78)
        print("TIKTOK WARM-UP FEATURE")
        print("=" * 78)
        print("Mode:                       APPLY")
        print("Status:                     PASS")
        print(f"Feature:                    {args.feature}")
        print(f"Context verification:       {result.get('context_verified')}")
        print(f"Feed pre-counts:            {tuple(result['pre_feed_counts'])}")
        if "post_feed_counts" in result:
            print(f"Feed post-counts:           {tuple(result['post_feed_counts'])}")
        print(f"Dwell:                      {dwell:.2f}s")
        print("Engagement actions:         NONE")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except (OSError, json.JSONDecodeError, RuntimeError, ValueError, HierarchyRuntimeError, NativeUiError) as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        _write_json(shareable, result)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
