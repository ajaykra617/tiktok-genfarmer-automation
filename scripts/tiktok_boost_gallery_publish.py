#!/usr/bin/env python3
"""Publish approved media through TikTok's normal Create -> Upload gallery path.

This is the qualification path for TikTok builds that reject external ACTION_SEND
media ingestion. It expects TikTok's Upload gallery to be open. The approved file
is staged and resolved in MediaStore, then the exact visible media tile is chosen
by its MediaStore-derived duration. Ambiguous same-duration tiles fail closed.

The picker intentionally stays on TikTok's default All tab. Earlier code tried to
switch to the Videos tab first, but current TikTok builds can expose duplicate
accessibility nodes for that label. Since media selection is already constrained
by the exact staged video duration, changing tabs adds no safety and can introduce
false ambiguity.

Actual final publishing still requires both --apply and --publish.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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
from genfarmer_automation.gallery_picker import GalleryPickerError, find_unique_duration_tile  # noqa: E402
from genfarmer_automation.hierarchy_runtime import HierarchyRuntimeError, capture_hierarchy_batch  # noqa: E402
from genfarmer_automation.native_ui import (  # noqa: E402
    NativeUiError,
    NativeUiNotFound,
    collect_nodes,
    contains_semantic_term,
    find_editable_node,
    find_exact_semantic_node,
)
from genfarmer_automation.selector_gate import assess_selector_gate  # noqa: E402

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"
CAPTION_HINTS = ("Describe your post", "Add description", "Write a caption", "Caption", "Description")
NEXT_TERMS = ("Next", "Continue")
POST_TERMS = ("Post", "Publish", "Post now")


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _capture(device: str, preferred_port: int) -> tuple[str, str]:
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


def _adb_text(device: str, *args: str, timeout: float = 20.0) -> str:
    try:
        proc = subprocess.run(
            ["adb", "-s", device, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise BoostMediaError("adb was not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise BoostMediaError("ADB media metadata query timed out") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise BoostMediaError(detail or f"adb exited {proc.returncode}")
    return proc.stdout.decode("utf-8", errors="replace")


def _duration_ms(device: str, content_uri: str) -> int:
    text = _adb_text(
        device,
        "shell",
        "content",
        "query",
        "--uri",
        content_uri,
        "--projection",
        "duration:_display_name:_size:mime_type",
        timeout=20.0,
    )
    matches = re.findall(r"(?:^|[\s,])duration=(\d+)(?:[\s,]|$)", text)
    values = sorted({int(value) for value in matches if int(value) > 0})
    if len(values) != 1:
        raise BoostMediaError("MediaStore did not expose one positive duration for staged video")
    return values[0]


def _is_gallery(xml: str) -> bool:
    return any(node.resource_id.endswith("/viewpager_choose_media") for node in collect_nodes(xml, package=TIKTOK_PACKAGE))


def _verify_feed_return(device: str, candidate, preferred_port: int):
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
    ap = argparse.ArgumentParser(description="Authorized TikTok normal-gallery Boost publisher")
    ap.add_argument("--media", type=Path, required=True)
    ap.add_argument("--caption", default="")
    ap.add_argument("--device", required=True)
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--account-key")
    ap.add_argument("--history", type=Path, default=ROOT / "evidence" / "boost-history.private.json")
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--ui-steps", type=int, default=10)
    ap.add_argument("--publish-timeout", type=float, default=75.0)
    ap.add_argument("--allow-republish", action="store_true")
    ap.add_argument("--ready", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-boost-gallery-publish-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-boost-gallery-publish.shareable.json"
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "publish_permitted": bool(args.publish),
        "candidate_index": args.candidate,
        "engagement_actions": 0,
        "gallery_filter": "all",
    }

    try:
        spec = media_spec(args.media)
        if spec.media_kind != "video":
            raise BoostMediaError("gallery qualification currently requires one approved video")
        history = load_history(args.history)
        if already_published(history, spec.sha256) and not args.allow_republish:
            raise BoostMediaError("this exact media hash is already recorded as published")
        candidates = candidates_from_payload(json.loads(args.candidates.read_text(encoding="utf-8")))
        if not 1 <= args.candidate <= len(candidates):
            raise RuntimeError("ranked candidate file does not contain requested candidate")
        candidate = candidates[args.candidate - 1]
        caption_hash = hashlib.sha256(args.caption.encode("utf-8")).hexdigest() if args.caption else None

        stager = AdbMediaStager(args.device)
        staged = stager.stage(spec)
        duration_ms = _duration_ms(args.device, staged.content_uri)
        result.update({
            "media_sha256": spec.sha256,
            "media_size": spec.local_path.stat().st_size,
            "duplicate_guard_pass": True,
            "media_duration_ms": duration_ms,
            "staged_content_uri_private": True,
        })

        observer = AdbObserver(args.device)
        obs = observer.observe()
        if obs.interrupt is not InterruptKind.NONE or not obs.tiktok_foreground:
            raise RuntimeError(
                f"TikTok upload gallery must be foreground; foreground={obs.foreground_package}/{obs.foreground_activity}, interrupt={obs.interrupt.value}"
            )
        xml, provider = _capture(args.device, args.preferred_hierarchy_port)
        (private / "gallery-before.xml").write_text(xml, encoding="utf-8")
        observer.capture_screenshot(private / "gallery-before.png")
        if not _is_gallery(xml):
            raise RuntimeError("TikTok normal Upload gallery surface is not currently open")

        if not args.apply:
            tile = find_unique_duration_tile(xml, duration_ms=duration_ms, package=TIKTOK_PACKAGE)
            result.update({"status": "DRY_RUN_READY", "gallery_provider": provider, "unique_media_tile": True})
            _write_json(shareable, result)
            print("=" * 78)
            print("TIKTOK BOOST NORMAL-GALLERY PUBLISH")
            print("=" * 78)
            print("Status:                     DRY_RUN_READY")
            print("Gallery surface:            PASS")
            print("Unique staged media tile:   PASS")
            print(f"Target duration:            {tile.label}")
            print("Device mutation:            NONE")
            print(f"Shareable result:           {shareable.relative_to(ROOT)}")
            print("=" * 78)
            return 0

        if not args.ready:
            raise RuntimeError("Boost write path requires explicit --ready")
        actions = AdbActions(args.device)

        # Stay on TikTok's default All tab. Exact duration matching already
        # constrains selection to the staged video and avoids duplicate Videos
        # accessibility labels observed on this build.
        tile = find_unique_duration_tile(xml, duration_ms=duration_ms, package=TIKTOK_PACKAGE)
        actions.tap(*tile.center)
        time.sleep(1.0)
        selected_xml, selected_provider = _capture(args.device, args.preferred_hierarchy_port)
        (private / "gallery-selected.xml").write_text(selected_xml, encoding="utf-8")
        observer.capture_screenshot(private / "gallery-selected.png")

        nxt = find_exact_semantic_node(selected_xml, NEXT_TERMS, package=TIKTOK_PACKAGE)
        _tap(actions, nxt)
        time.sleep(3.0)

        caption_entered = not bool(args.caption)
        final_ready = False
        providers = [provider, selected_provider]
        for step in range(1, args.ui_steps + 1):
            obs = observer.observe()
            if obs.interrupt is not InterruptKind.NONE:
                raise RuntimeError(f"Android/TikTok interrupt blocks publish flow: {obs.interrupt.value}")
            if not obs.tiktok_foreground:
                raise RuntimeError("TikTok left foreground after normal-gallery media selection")
            observer.capture_screenshot(private / f"ui-{step:02d}.png")
            xml, step_provider = _capture(args.device, args.preferred_hierarchy_port)
            providers.append(step_provider)
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
                    actions.keyevent(4)
                    caption_entered = True
                    time.sleep(1.0)
                    continue

            try:
                post = find_exact_semantic_node(xml, POST_TERMS, package=TIKTOK_PACKAGE)
            except NativeUiNotFound:
                post = None
            if post is not None:
                if not caption_entered:
                    raise RuntimeError("final Post control appeared before caption was safely entered")
                final_ready = True
                observer.capture_screenshot(private / "ready-to-publish.png")
                if not args.publish:
                    result.update({
                        "status": "READY_TO_PUBLISH",
                        "final_control_exact_match": True,
                        "caption_entered": caption_entered,
                        "hierarchy_providers": sorted(set(providers)),
                    })
                    _write_json(shareable, result)
                    print("=" * 78)
                    print("TIKTOK BOOST NORMAL-GALLERY PUBLISH")
                    print("=" * 78)
                    print("Status:                     READY_TO_PUBLISH")
                    print("Staged media selection:     PASS")
                    print("Exact final Post control:   YES")
                    print("Final publish tap:          NOT PERMITTED (add --publish)")
                    print(f"Private evidence:           {private.relative_to(ROOT)}")
                    print(f"Shareable result:           {shareable.relative_to(ROOT)}")
                    print("=" * 78)
                    return 0

                account_key = args.account_key or f"device:{args.device}"
                record_history(args.history, history, sha256=spec.sha256, entry={
                    "status": "submitting",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "account_key": account_key,
                    "device": args.device,
                    "caption_sha256": caption_hash,
                })
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
            raise RuntimeError("post-selection state has neither safe caption field nor exact Next/Post control")

        if not final_ready:
            raise RuntimeError("publish flow exhausted UI-step budget before final Post control")

        deadline = time.monotonic() + args.publish_timeout
        verified = False
        verify_provider = None
        verify_counts = None
        while time.monotonic() < deadline:
            time.sleep(2.0)
            obs = observer.observe()
            if not obs.tiktok_foreground or obs.interrupt is not InterruptKind.NONE:
                continue
            passed, verify_provider, verify_counts = _verify_feed_return(args.device, candidate, args.preferred_hierarchy_port)
            if passed:
                verified = True
                break
        account_key = args.account_key or f"device:{args.device}"
        if not verified:
            record_history(args.history, history, sha256=spec.sha256, entry={
                "status": "submitted_unverified",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "account_key": account_key,
                "device": args.device,
                "caption_sha256": caption_hash,
            })
            raise RuntimeError("final Post tap sent but qualified feed return was not proven before timeout")

        record_history(args.history, history, sha256=spec.sha256, entry={
            "status": "published",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "account_key": account_key,
            "device": args.device,
            "caption_sha256": caption_hash,
        })
        result.update({
            "status": "PASS_PUBLISHED",
            "feed_return_verified": True,
            "feed_selector_counts": list(verify_counts or ()),
            "verification_provider": verify_provider,
            "history_recorded": True,
        })
        _write_json(shareable, result)
        print("=" * 78)
        print("TIKTOK BOOST NORMAL-GALLERY PUBLISH")
        print("=" * 78)
        print("Status:                     PASS_PUBLISHED")
        print("Staged media selection:     PASS")
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
        GalleryPickerError,
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