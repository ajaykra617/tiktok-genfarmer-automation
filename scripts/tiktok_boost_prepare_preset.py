#!/usr/bin/env python3
"""Run TikTok Boost Phase A from a saved non-publishing preset.

The preset may choose one passive Explore source from a configured pool using a
recorded deterministic seed.  Presets that request a warm scroll now use the
qualified standalone `tiktok_boost_warm_scroll.py` controller, so no compiled
`.genfarm` export is required.  Preparation still stops at READY_FOR_PUBLISH and
never enters the Create/Upload/Post UI.
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

from genfarmer_automation.boost_preset_runtime import (  # noqa: E402
    build_warm_scroll_command,
    expected_warm_scroll_status,
)
from genfarmer_automation.boost_sources import (  # noqa: E402
    BoostSourceError,
    choose_source,
    load_preset,
    preset_summary,
)
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


def _child_error(output: str, fallback: str) -> str:
    detail = (output or "").strip().splitlines()
    if len(detail) >= 2:
        return detail[-2]
    if detail:
        return detail[-1]
    return fallback


def main() -> int:
    ap = argparse.ArgumentParser(description="Saved-preset runner for TikTok Boost Phase A")
    ap.add_argument("--config", type=Path, default=ROOT / "config" / "tiktok-boost-presets.example.json")
    ap.add_argument("--preset", required=True)
    ap.add_argument("--device", required=True)
    ap.add_argument("--proxy-id", required=True)
    ap.add_argument("--proxy-host")
    ap.add_argument("--proxy-port", type=int)
    ap.add_argument("--account-key")
    ap.add_argument("--media", type=Path, action="append", default=[])
    ap.add_argument("--media-dir", type=Path, action="append", default=[])
    ap.add_argument("--history", type=Path)
    ap.add_argument("--reservations", type=Path)
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--candidates", type=Path)
    ap.add_argument(
        "--warmup-compiled",
        type=Path,
        help="legacy compatibility option; saved-preset warm scroll no longer requires a .genfarm export",
    )
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--ready", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not args.media and not args.media_dir:
        print("ERROR: supply at least one --media or --media-dir", file=sys.stderr)
        return 2
    if bool(args.proxy_host) != bool(args.proxy_port):
        print("ERROR: --proxy-host and --proxy-port must be supplied together", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-boost-preset-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-boost-preset.shareable.json"
    seed = args.seed if args.seed is not None else int(time.time())

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "preset": args.preset,
        "seed": seed,
        "device_private": True,
        "proxy_id_private": True,
        "publishing_deferred": True,
        "engagement_actions": 0,
    }

    try:
        payload = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise BoostSourceError("preset configuration root must be an object")
        preset = load_preset(payload, args.preset)
        source, source_index = choose_source(preset.sources, selection=preset.selection, seed=seed)
        result["preset_summary"] = preset_summary(preset)
        result["selected_source_index"] = source_index
        result["selected_source_type"] = source.source_type if source else None

        # Source values stay private; record them only in private evidence.
        (private / "selection.private.json").write_text(
            json.dumps(
                {
                    "preset": preset.name,
                    "seed": seed,
                    "selection": preset.selection,
                    "source_index": source_index,
                    "source_type": source.source_type if source else None,
                    "source_value": source.value if source else None,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        warm_scroll_status = "NOT_REQUESTED"
        if preset.warm_scroll_videos:
            if args.candidates is None:
                raise BoostSourceError(
                    "preset warm scroll requires --candidates; a compiled .genfarm export is no longer required"
                )
            warm_cmd = build_warm_scroll_command(
                python_executable=sys.executable,
                root=ROOT,
                candidates=args.candidates,
                candidate=args.candidate,
                device=args.device,
                videos=preset.warm_scroll_videos,
                seed=seed,
                preferred_hierarchy_port=args.preferred_hierarchy_port,
                apply=args.apply,
            )
            warm = _run(warm_cmd, timeout=600.0)
            warm_output = warm.stdout or ""
            (private / "warm-scroll.log").write_text(warm_output, encoding="utf-8", errors="replace")
            warm_child = load_shareable(ROOT, warm_output)
            expected_warm = expected_warm_scroll_status(apply=args.apply)
            if warm.returncode != 0 or warm_child is None or warm_child.get("status") != expected_warm:
                raise RuntimeError(
                    "Boost preset warm scroll blocked: "
                    + _child_error(warm_output, "warm-scroll child did not return a result")
                )
            warm_scroll_status = expected_warm

        # Warm scroll is orchestrated above.  The preparation child owns Explore,
        # duplicate guard, atomic reservation and exact Android media staging.
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "tiktok_boost_prepare.py"),
            "--device", args.device,
            "--proxy-id", args.proxy_id,
            "--lease-minutes", str(preset.lease_minutes),
            "--candidate", str(args.candidate),
            "--preferred-hierarchy-port", str(args.preferred_hierarchy_port),
            "--warm-scroll-videos", "0",
        ]
        for path in args.media:
            cmd.extend(["--media", str(path)])
        for path in args.media_dir:
            cmd.extend(["--media-dir", str(path)])
        if args.proxy_host and args.proxy_port:
            cmd.extend(["--proxy-host", args.proxy_host, "--proxy-port", str(args.proxy_port)])
        if args.account_key:
            cmd.extend(["--account-key", args.account_key])
        if args.history:
            cmd.extend(["--history", str(args.history)])
        if args.reservations:
            cmd.extend(["--reservations", str(args.reservations)])
        if source:
            cmd.extend(["--explore-type", source.source_type, "--explore-value", source.value])
        if args.ready:
            cmd.append("--ready")
        if args.apply:
            cmd.append("--apply")

        proc = _run(cmd, timeout=900.0)
        prepare_output = proc.stdout or ""
        (private / "prepare.log").write_text(prepare_output, encoding="utf-8", errors="replace")
        child = load_shareable(ROOT, prepare_output)
        if proc.returncode != 0 or child is None:
            raise RuntimeError(
                "Boost Phase A preset child run blocked: "
                + _child_error(prepare_output, "prepare child did not return a result")
            )

        status = str(child.get("status"))
        expected = "READY_FOR_PUBLISH" if args.apply else "DRY_RUN_READY"
        if status != expected:
            raise RuntimeError(f"Boost Phase A preset returned {status!r}, expected {expected!r}")
        result.update(
            {
                "status": status,
                "child_status": status,
                "warm_scroll_status": warm_scroll_status,
                "explore_status": child.get("explore_status"),
                "duplicate_guard_pass": child.get("duplicate_guard_pass"),
                "media_reserved": child.get("media_reserved"),
                "media_staged": child.get("media_staged"),
                "publish_action_performed": False,
            }
        )
        _write_json(shareable, result)

        print("=" * 78)
        print("TIKTOK BOOST PHASE A PRESET")
        print("=" * 78)
        print(f"Status:                     {status}")
        print(f"Preset:                     {preset.name}")
        print(f"Seed:                       {seed}")
        print(f"Explore source:             {source.source_type if source else 'NOT REQUESTED'}")
        print(f"Warm scroll videos:         {preset.warm_scroll_videos}")
        print(f"Warm scroll status:         {warm_scroll_status}")
        print("Publishing UI:              DEFERRED / NOT ENTERED")
        print("Final Post action:          NONE")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except (OSError, json.JSONDecodeError, BoostSourceError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        _write_json(shareable, result)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
