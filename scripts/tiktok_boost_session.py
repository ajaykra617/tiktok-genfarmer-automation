#!/usr/bin/env python3
"""One-command authorized TikTok Boost: optional explore then approved publish."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.warmup_session import load_shareable  # noqa: E402


def _write_json(path: Path, value) -> None:
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


def main() -> int:
    ap = argparse.ArgumentParser(description="End-to-end authorized TikTok Boost session")
    ap.add_argument("--device", required=True)
    ap.add_argument("--media", type=Path, required=True)
    ap.add_argument("--caption", default="")
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--explore-type", choices=("keyword", "hashtag", "account", "link"))
    ap.add_argument("--explore-value")
    ap.add_argument("--account-key")
    ap.add_argument("--history", type=Path, default=ROOT / "evidence" / "boost-history.private.json")
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--allow-republish", action="store_true")
    ap.add_argument("--ready", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if bool(args.explore_type) != bool(args.explore_value):
        print("ERROR: --explore-type and --explore-value must be supplied together", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-boost-session-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-boost-session.shareable.json"
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "explore_requested": bool(args.explore_type),
        "publish_requested": bool(args.publish),
        "engagement_actions": 0,
    }

    try:
        if not args.apply:
            result["status"] = "DRY_RUN_READY"
            _write_json(shareable, result)
            print("=" * 78)
            print("TIKTOK BOOST SESSION")
            print("=" * 78)
            print("Status:                     DRY_RUN_READY")
            print(f"Explore:                    {'YES' if args.explore_type else 'NO'}")
            print(f"Final publish permitted:    {'YES' if args.publish else 'NO'}")
            print("Mutation:                   NONE")
            print(f"Shareable result:           {shareable.relative_to(ROOT)}")
            print("=" * 78)
            return 0

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
            explore = _run(explore_cmd, timeout=120.0)
            (private / "explore.log").write_text(explore.stdout or "", encoding="utf-8", errors="replace")
            explore_payload = load_shareable(ROOT, explore.stdout or "")
            if explore.returncode != 0 or explore_payload is None or explore_payload.get("status") != "PASS":
                raise RuntimeError("Boost explore stage did not reach PASS; publish was not attempted")
            result["explore_status"] = "PASS"

        publish_cmd = [
            sys.executable,
            str(ROOT / "scripts" / "tiktok_boost_publish.py"),
            "--media", str(args.media),
            "--caption", args.caption,
            "--device", args.device,
            "--candidates", str(args.candidates),
            "--candidate", str(args.candidate),
            "--history", str(args.history),
            "--preferred-hierarchy-port", str(args.preferred_hierarchy_port),
            "--apply",
        ]
        if args.account_key:
            publish_cmd.extend(["--account-key", args.account_key])
        if args.allow_republish:
            publish_cmd.append("--allow-republish")
        if args.ready:
            publish_cmd.append("--ready")
        if args.publish:
            publish_cmd.append("--publish")

        publish = _run(publish_cmd, timeout=420.0)
        (private / "publish.log").write_text(publish.stdout or "", encoding="utf-8", errors="replace")
        publish_payload = load_shareable(ROOT, publish.stdout or "")
        if publish.returncode != 0 or publish_payload is None:
            raise RuntimeError("Boost publish stage was blocked; inspect private publish log/evidence")
        publish_status = publish_payload.get("status")
        expected = "PASS_PUBLISHED" if args.publish else "READY_TO_PUBLISH"
        if publish_status != expected:
            raise RuntimeError(f"Boost publish stage returned {publish_status!r}, expected {expected!r}")

        result.update(
            {
                "status": expected,
                "publish_status": publish_status,
                "explore_status": result.get("explore_status"),
                "duplicate_guard_pass": publish_payload.get("duplicate_guard_pass"),
                "feed_return_verified": publish_payload.get("feed_return_verified"),
                "media_sha256": publish_payload.get("media_sha256"),
            }
        )
        _write_json(shareable, result)
        print("=" * 78)
        print("TIKTOK BOOST SESSION")
        print("=" * 78)
        print(f"Status:                     {expected}")
        print(f"Explore stage:              {result.get('explore_status') or 'NOT REQUESTED'}")
        print(f"Publish stage:              {publish_status}")
        print("Engagement actions:         NONE")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        _write_json(shareable, result)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
