#!/usr/bin/env python3
"""Stage and publish one explicitly approved media item through TikTok.

Safety/correctness properties:
- the local file is hash-addressed before it reaches the device;
- successful hashes are blocked from re-use by default;
- the exact staged MediaStore URI is sent to TikTok, avoiding gallery ambiguity;
- UI taps are derived from fresh hierarchy bounds, never fixed guessed pixels;
- the final Post/Publish control requires exact semantic equality;
- actual publishing requires both --apply and --publish;
- success is recorded only after the previously-qualified feed selector returns.

This workflow is for authorized account-local publishing. It contains no likes,
follows, replies, DMs, or coordinated engagement behavior.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_actions import AdbActions, AdbActionError  # noqa: E402
from genfarmer_automation.adb_observer import AdbObserver, InterruptKind  # noqa: E402
from genfarmer_automation.boost_media import (  # noqa: E402
    AdbMediaStager,
    BoostMediaError,
    already_published,
    load_history,
    media_spec,
    record_history,
)
from genfarmer_automation.feed_anchor_qualification import candidates_from_payload  # noqa: E402
from genfarmer_automation.hierarchy_runtime import HierarchyRuntimeError, capture_hierarchy_batch  # noqa: E402
from genfarmer_automation.native_ui import (  # noqa: E402
    NativeUiError,
    NativeUiNotFound,
    contains_semantic_term,
    find_editable_node,
    find_exact_semantic_node,
)
from genfarmer_automation.selector_gate import assess_selector_gate  # noqa: E402

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"
CAPTION_HINTS = (
    "Describe your post",
    "Add description",
    "Write a caption",
    "Caption",
    "Description",
)
NEXT_TERMS = ("Next", "Continue")
POST_TERMS = ("Post", "Publish", "Post now")


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _capture_xml(device: str, preferred_port: int) -> tuple[str, str]:
    batch = capture_hierarchy_batch(
        device,
        count=1,
        interval=0.0,
        preferred_port=preferred_port,
        helper_timeout=4.0,
        max_ports=12,
    )
    return batch.snapshots[0], batch.provider


def _tap(actions: AdbActions, node) -> None:
    x, y = node.center
    actions.tap(x, y)


def _tiktok_ready(observer: AdbObserver) -> bool:
    obs = observer.observe()
    return (
        obs.adb_state == "device"
        and obs.tiktok_foreground
        and obs.interrupt is InterruptKind.NONE
    )


def _verify_feed_return(device: str, candidate, preferred_port: int) -> tuple[bool, str | None, tuple[int, ...] | None]:
    try:
        batch = capture_hierarchy_batch(
            device,
            count=2,
            interval=0.15,
            preferred_port=preferred_port,
            helper_timeout=4.0,
            max_ports=12,
        )
    except HierarchyRuntimeError:
        return False, None, None
    gate = assess_selector_gate(candidate, batch.snapshots, package=TIKTOK_PACKAGE)
    return gate.passed, batch.provider, gate.counts


def main() -> int:
    ap = argparse.ArgumentParser(description="Authorized TikTok Boost media publisher")
    ap.add_argument("--media", type=Path, required=True, help="explicitly approved local media file")
    ap.add_argument("--caption", default="", help="optional conservative ASCII caption")
    ap.add_argument("--device", required=True)
    ap.add_argument("--candidates", type=Path, required=True, help="private ranked feed-anchor candidates")
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--account-key", help="private local account label; defaults to the device id")
    ap.add_argument("--history", type=Path, default=ROOT / "evidence" / "boost-history.private.json")
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--ui-steps", type=int, default=8)
    ap.add_argument("--publish-timeout", type=float, default=75.0)
    ap.add_argument("--allow-republish", action="store_true")
    ap.add_argument("--ready", action="store_true", help="assert this authorized account/device is ready for Boost")
    ap.add_argument("--publish", action="store_true", help="permit the final exact Post/Publish tap")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.candidate < 1 or not 1 <= args.ui_steps <= 20 or not 10 <= args.publish_timeout <= 300:
        print("ERROR: invalid bounds for candidate/ui-steps/publish-timeout", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-boost-publish-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-boost-publish.shareable.json"
    account_key = args.account_key or f"device:{args.device}"

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "publish_permitted": bool(args.publish),
        "account_identifier_private": True,
        "caption_private": True,
        "engagement_actions": 0,
        "candidate_index": args.candidate,
    }

    try:
        spec = media_spec(args.media)
        history = load_history(args.history)
        if already_published(history, spec.sha256) and not args.allow_republish:
            raise BoostMediaError("this exact media hash is already recorded as published")

        raw_candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
        candidates = candidates_from_payload(raw_candidates)
        if not 1 <= args.candidate <= len(candidates):
            raise RuntimeError("ranked candidate file does not contain requested candidate")
        candidate = candidates[args.candidate - 1]

        caption_hash = hashlib.sha256(args.caption.encode("utf-8")).hexdigest() if args.caption else None
        result.update(
            {
                "media_kind": spec.media_kind,
                "media_sha256": spec.sha256,
                "media_size": spec.local_path.stat().st_size,
                "caption_sha256": caption_hash,
                "duplicate_guard_pass": True,
            }
        )

        if not args.apply:
            result["status"] = "DRY_RUN_READY"
            result["reason"] = "approved file validated, hash duplicate guard passed, no device mutation performed"
            _write_json(shareable, result)
            print("=" * 78)
            print("TIKTOK BOOST PUBLISH")
            print("=" * 78)
            print("Mode:                       DRY-RUN")
            print("Status:                     DRY_RUN_READY")
            print(f"Media kind:                 {spec.media_kind}")
            print("Duplicate guard:            PASS")
            print("Device mutation:            NONE")
            print(f"Shareable result:           {shareable.relative_to(ROOT)}")
            print("=" * 78)
            return 0

        if not args.ready:
            raise RuntimeError("Boost write path requires explicit --ready for this authorized account/device")

        stager = AdbMediaStager(args.device)
        staged = stager.stage(spec)
        result["media_staged"] = True
        result["staged_content_uri_private"] = True
        (private / "staged-media.private.json").write_text(
            json.dumps(
                {
                    "account_key": account_key,
                    "local_path": str(spec.local_path),
                    "remote_path": spec.remote_path,
                    "content_uri": staged.content_uri,
                    "sha256": spec.sha256,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        stager.launch_tiktok_share(staged, package=TIKTOK_PACKAGE)
        time.sleep(4.0)

        observer = AdbObserver(args.device)
        actions = AdbActions(args.device)
        caption_entered = not bool(args.caption)
        final_ready = False
        providers: list[str] = []

        for step in range(1, args.ui_steps + 1):
            obs = observer.observe()
            if obs.interrupt is not InterruptKind.NONE:
                raise RuntimeError(f"Android/TikTok interrupt blocks publish flow: {obs.interrupt.value}")
            if not obs.tiktok_foreground:
                raise RuntimeError("TikTok is not foreground after targeted media share")

            observer.capture_screenshot(private / f"ui-{step:02d}.png")
            xml, provider = _capture_xml(args.device, args.preferred_hierarchy_port)
            providers.append(provider)
            (private / f"ui-{step:02d}.xml").write_text(xml, encoding="utf-8")

            if not caption_entered:
                try:
                    editable = find_editable_node(xml, package=TIKTOK_PACKAGE, hints=CAPTION_HINTS)
                except NativeUiError:
                    editable = None
                if editable is not None and (
                    contains_semantic_term(xml, CAPTION_HINTS, package=TIKTOK_PACKAGE)
                    or contains_semantic_term(xml, POST_TERMS, package=TIKTOK_PACKAGE)
                ):
                    _tap(actions, editable)
                    actions.input_text(args.caption)
                    actions.keyevent(4)  # BACK: dismiss IME without navigating app state.
                    caption_entered = True
                    time.sleep(1.0)
                    continue

            try:
                post = find_exact_semantic_node(xml, POST_TERMS, package=TIKTOK_PACKAGE)
            except NativeUiNotFound:
                post = None
            if post is not None:
                if not caption_entered:
                    raise RuntimeError("final publish control appeared before caption field was safely resolved")
                final_ready = True
                observer.capture_screenshot(private / "ready-to-publish.png")
                if not args.publish:
                    result.update(
                        {
                            "status": "READY_TO_PUBLISH",
                            "caption_entered": caption_entered,
                            "final_control_exact_match": True,
                            "hierarchy_providers": sorted(set(providers)),
                        }
                    )
                    _write_json(shareable, result)
                    print("=" * 78)
                    print("TIKTOK BOOST PUBLISH")
                    print("=" * 78)
                    print("Status:                     READY_TO_PUBLISH")
                    print("Exact final Post control:   YES")
                    print("Final publish tap:          NOT PERMITTED (add --publish)")
                    print(f"Private evidence:           {private.relative_to(ROOT)}")
                    print(f"Shareable result:           {shareable.relative_to(ROOT)}")
                    print("=" * 78)
                    return 0

                record_history(
                    args.history,
                    history,
                    sha256=spec.sha256,
                    entry={
                        "status": "submitting",
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "account_key": account_key,
                        "device": args.device,
                        "caption_sha256": caption_hash,
                    },
                )
                _tap(actions, post)
                result["final_publish_tap_sent"] = True
                break

            try:
                nxt = find_exact_semantic_node(xml, NEXT_TERMS, package=TIKTOK_PACKAGE)
            except NativeUiNotFound:
                nxt = None
            if nxt is not None:
                _tap(actions, nxt)
                time.sleep(2.0)
                continue

            raise RuntimeError("publish state machine found neither a safe caption field nor exact Next/Post control")

        if not final_ready:
            raise RuntimeError("publish flow exhausted its bounded UI-step budget before final Post control")
        if not args.publish:
            raise RuntimeError("internal publish state reached without final permission")

        deadline = time.monotonic() + args.publish_timeout
        verified = False
        verify_provider = None
        verify_counts = None
        while time.monotonic() < deadline:
            time.sleep(2.0)
            if not _tiktok_ready(observer):
                continue
            passed, provider, counts = _verify_feed_return(
                args.device, candidate, args.preferred_hierarchy_port
            )
            if passed:
                verified = True
                verify_provider = provider
                verify_counts = counts
                break

        if not verified:
            record_history(
                args.history,
                history,
                sha256=spec.sha256,
                entry={
                    "status": "submitted_unverified",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "account_key": account_key,
                    "device": args.device,
                    "caption_sha256": caption_hash,
                },
            )
            raise RuntimeError("final Post tap was sent but qualified feed-return success was not proven before timeout")

        observer.capture_screenshot(private / "published-feed-return.png")
        record_history(
            args.history,
            history,
            sha256=spec.sha256,
            entry={
                "status": "published",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "account_key": account_key,
                "device": args.device,
                "caption_sha256": caption_hash,
            },
        )
        result.update(
            {
                "status": "PASS_PUBLISHED",
                "caption_entered": caption_entered,
                "final_control_exact_match": True,
                "feed_return_verified": True,
                "feed_selector_counts": list(verify_counts or ()),
                "verification_provider": verify_provider,
                "hierarchy_providers": sorted(set(providers)),
                "history_recorded": True,
            }
        )
        _write_json(shareable, result)

        print("=" * 78)
        print("TIKTOK BOOST PUBLISH")
        print("=" * 78)
        print("Status:                     PASS_PUBLISHED")
        print("Approved media hash:        RECORDED / VALUE IN REPORT")
        print("Exact final Post control:   YES")
        print("Qualified feed return:      PASS")
        print(f"Feed selector counts:       {verify_counts}")
        print("Duplicate history:          RECORDED")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except (
        OSError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
        BoostMediaError,
        AdbActionError,
        HierarchyRuntimeError,
        NativeUiError,
    ) as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        _write_json(shareable, result)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
