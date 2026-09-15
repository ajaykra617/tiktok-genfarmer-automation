#!/usr/bin/env python3
"""Prepare an authorized TikTok Boost job without entering the publish UI.

Phase A deliberately stops before Create/Upload/Post. It can perform a short
passive warm-up, an optional passive Explore action, atomically reserve one
approved media hash, stage that exact file into Android MediaStore, and emit an
auditable preparation result. No likes/follows/replies/DMs or final posting are
performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_observer import AdbObserver  # noqa: E402
from genfarmer_automation.audit_log import AuditRecord, append_jsonl  # noqa: E402
from genfarmer_automation.boost_media import AdbMediaStager, load_history  # noqa: E402
from genfarmer_automation.boost_prepare import (  # noqa: E402
    BoostPrepareError,
    PreparationLeaseStore,
    choose_and_reserve_media,
    discover_approved_media,
    pending_media,
)
from genfarmer_automation.warmup_session import load_shareable  # noqa: E402

TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(cmd: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def _adb_text(device: str, *args: str, timeout: float = 15.0) -> str:
    try:
        proc = subprocess.run(
            ["adb", "-s", device, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise BoostPrepareError("adb was not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise BoostPrepareError("ADB preflight timed out") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise BoostPrepareError(detail or f"adb exited {proc.returncode}")
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _tiktok_installed(device: str) -> bool:
    return bool(_adb_text(device, "shell", "pm", "path", TIKTOK_PACKAGE, timeout=15.0))


def _tcp_ready(host: str, port: int, *, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _first_dry_candidate(specs, history, store: PreparationLeaseStore):
    for spec in pending_media(specs, history):
        if not store.is_active(spec.sha256):
            return spec
    raise BoostPrepareError("no pending unreserved approved media is available")


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare TikTok Boost through READY_FOR_PUBLISH without posting")
    ap.add_argument("--device", required=True)
    ap.add_argument("--account-key", help="private local account label; defaults to the device id")
    ap.add_argument("--proxy-id", required=True, help="scheduler/proxy identity label")
    ap.add_argument("--proxy-host", help="optional proxy listener host for TCP readiness check")
    ap.add_argument("--proxy-port", type=int, help="optional proxy listener port for TCP readiness check")
    ap.add_argument("--media", type=Path, action="append", default=[])
    ap.add_argument("--media-dir", type=Path, action="append", default=[])
    ap.add_argument("--history", type=Path, default=ROOT / "evidence" / "boost-history.private.json")
    ap.add_argument(
        "--reservations",
        type=Path,
        default=ROOT / "evidence" / "boost-preparation-leases.private",
    )
    ap.add_argument("--lease-minutes", type=float, default=120.0)
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--candidates", type=Path)
    ap.add_argument("--warm-scroll-videos", type=int, default=0)
    ap.add_argument("--warmup-compiled", type=Path)
    ap.add_argument("--explore-type", choices=("keyword", "hashtag", "account", "link"))
    ap.add_argument("--explore-value")
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--ready", action="store_true", help="assert account/device is authorized for Boost preparation")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not args.media and not args.media_dir:
        print("ERROR: supply at least one --media or --media-dir", file=sys.stderr)
        return 2
    if bool(args.proxy_host) != bool(args.proxy_port):
        print("ERROR: --proxy-host and --proxy-port must be supplied together", file=sys.stderr)
        return 2
    if args.proxy_port is not None and not 1 <= args.proxy_port <= 65535:
        print("ERROR: --proxy-port must be 1..65535", file=sys.stderr)
        return 2
    if not 1 <= args.lease_minutes <= 1440:
        print("ERROR: --lease-minutes must be 1..1440", file=sys.stderr)
        return 2
    if not 0 <= args.warm_scroll_videos <= 20:
        print("ERROR: --warm-scroll-videos must be 0..20", file=sys.stderr)
        return 2
    if bool(args.explore_type) != bool(args.explore_value):
        print("ERROR: --explore-type and --explore-value must be supplied together", file=sys.stderr)
        return 2
    if args.warm_scroll_videos and (args.warmup_compiled is None or args.candidates is None):
        print("ERROR: warm scroll requires --warmup-compiled and --candidates", file=sys.stderr)
        return 2

    account_key = args.account_key or f"device:{args.device}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-boost-prepare-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-boost-prepare.shareable.json"
    audit_path = ROOT / "logs" / "automation.audit.private.jsonl"

    result: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "device_private": True,
        "account_identifier_private": True,
        "proxy_id_private": True,
        "publishing_deferred": True,
        "engagement_actions": 0,
        "warm_scroll_requested": args.warm_scroll_videos,
        "explore_requested": bool(args.explore_type),
    }
    leased_sha: str | None = None
    store = PreparationLeaseStore(args.reservations)

    try:
        specs = discover_approved_media([*args.media, *args.media_dir])
        history = load_history(args.history)
        selected = _first_dry_candidate(specs, history, store)
        result.update(
            {
                "approved_media_count": len(specs),
                "pending_media_count": len(pending_media(specs, history)),
                "selected_media_sha256": selected.sha256,
                "selected_media_kind": selected.media_kind,
                "duplicate_guard_pass": True,
            }
        )

        state = _adb_text(args.device, "get-state", timeout=10.0)
        if state != "device":
            raise BoostPrepareError(f"ADB device is not ready: {state!r}")
        if not _tiktok_installed(args.device):
            raise BoostPrepareError("TikTok package is not installed on the selected device")
        result["device_preflight"] = "PASS"
        result["tiktok_installed"] = True

        proxy_network = "UNVERIFIED"
        if args.proxy_host and args.proxy_port:
            if not _tcp_ready(args.proxy_host, args.proxy_port):
                raise BoostPrepareError("configured proxy listener is not TCP reachable")
            proxy_network = "TCP_PASS"
        result["proxy_network_check"] = proxy_network

        if not args.apply:
            result["status"] = "DRY_RUN_READY"
            _write_json(shareable, result)
            print("=" * 78)
            print("TIKTOK BOOST PHASE A PREPARE")
            print("=" * 78)
            print("Status:                     DRY_RUN_READY")
            print("Device/TikTok preflight:    PASS")
            print("Duplicate guard:            PASS")
            print(f"Proxy network:              {proxy_network}")
            print("Media reservation/staging:  NOT PERFORMED")
            print("Publishing UI:              DEFERRED")
            print(f"Shareable result:           {shareable.relative_to(ROOT)}")
            print("=" * 78)
            return 0

        if not args.ready:
            raise BoostPrepareError("apply mode requires explicit --ready for this authorized account/device")

        prepared = choose_and_reserve_media(
            specs,
            history,
            store,
            device=args.device,
            account_key=account_key,
            ttl_seconds=args.lease_minutes * 60.0,
        )
        leased_sha = prepared.spec.sha256
        selected = prepared.spec
        (private / "reservation.private.json").write_text(
            json.dumps(
                {
                    "lease_path": str(prepared.lease_path),
                    "sha256": selected.sha256,
                    "device": args.device,
                    "account_key": account_key,
                    "proxy_id": args.proxy_id,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        if args.warm_scroll_videos:
            warm_cmd = [
                sys.executable,
                str(ROOT / "scripts" / "tiktok_warmup_session.py"),
                str(args.warmup_compiled),
                str(args.candidates),
                "--candidate", str(args.candidate),
                "--device", args.device,
                "--videos", str(args.warm_scroll_videos),
                "--watch-min", "5",
                "--watch-max", "10",
                "--max-session-minutes", "8",
                "--step-retries", "1",
                "--failure-budget", "2",
                "--preferred-hierarchy-port", str(args.preferred_hierarchy_port),
                "--apply",
            ]
            warm = _run(warm_cmd, timeout=600.0)
            (private / "warm-scroll.log").write_text(warm.stdout or "", encoding="utf-8", errors="replace")
            warm_payload = load_shareable(ROOT, warm.stdout or "")
            if warm.returncode != 0 or warm_payload is None or warm_payload.get("status") != "PASS":
                raise BoostPrepareError("optional warm scroll did not reach PASS")
            result["warm_scroll_status"] = "PASS"
        else:
            result["warm_scroll_status"] = "NOT_REQUESTED"

        if args.explore_type:
            explore_cmd = [
                sys.executable,
                str(ROOT / "scripts" / "tiktok_boost_explore.py"),
                "--type", args.explore_type,
                "--value", args.explore_value,
                "--device", args.device,
                "--preferred-hierarchy-port", str(args.preferred_hierarchy_port),
                "--apply",
            ]
            explore = _run(explore_cmd, timeout=180.0)
            (private / "explore.log").write_text(explore.stdout or "", encoding="utf-8", errors="replace")
            explore_payload = load_shareable(ROOT, explore.stdout or "")
            if explore.returncode != 0 or explore_payload is None or explore_payload.get("status") != "PASS":
                raise BoostPrepareError("Boost Explore did not reach PASS")
            result["explore_status"] = "PASS"
            result["explore_type"] = args.explore_type
        else:
            result["explore_status"] = "NOT_REQUESTED"

        staged = AdbMediaStager(args.device).stage(selected)
        result.update(
            {
                "status": "READY_FOR_PUBLISH",
                "selected_media_sha256": selected.sha256,
                "selected_media_kind": selected.media_kind,
                "media_reserved": True,
                "media_staged": True,
                "staged_content_uri_private": True,
                "publish_action_performed": False,
                "publish_ui_entered": False,
            }
        )
        (private / "staged-media.private.json").write_text(
            json.dumps(
                {
                    "sha256": selected.sha256,
                    "remote_path": selected.remote_path,
                    "content_uri": staged.content_uri,
                    "device": args.device,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        _write_json(shareable, result)
        append_jsonl(
            audit_path,
            AuditRecord.now(
                account=account_key,
                app="tiktok",
                mode="boost_prepare",
                action="ready_for_publish",
                proxy=args.proxy_id,
                result="PASS",
                ai_text="",
            ),
        )

        print("=" * 78)
        print("TIKTOK BOOST PHASE A PREPARE")
        print("=" * 78)
        print("Status:                     READY_FOR_PUBLISH")
        print("Device/TikTok preflight:    PASS")
        print(f"Proxy network:              {proxy_network}")
        print(f"Warm scroll:                {result['warm_scroll_status']}")
        print(f"Explore:                    {result['explore_status']}")
        print("Duplicate guard:            PASS")
        print("Media reservation:          PASS")
        print("Exact media staging:        PASS")
        print("Publishing UI:              DEFERRED / NOT ENTERED")
        print("Final Post action:          NONE")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except (
        OSError,
        ValueError,
        BoostPrepareError,
        subprocess.TimeoutExpired,
    ) as exc:
        if leased_sha is not None:
            store.release(leased_sha, device=args.device)
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        _write_json(shareable, result)
        append_jsonl(
            audit_path,
            AuditRecord.now(
                account=account_key,
                app="tiktok",
                mode="boost_prepare",
                action="prepare",
                proxy=args.proxy_id,
                result="BLOCKED",
                ai_text="",
            ),
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
