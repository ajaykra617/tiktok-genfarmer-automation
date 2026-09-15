#!/usr/bin/env python3
"""Qualify passive TikTok Boost Explore source types without publishing.

Each requested source is run through the existing `tiktok_boost_explore.py`
controller. Failures are recorded per source and the matrix continues, so one UI
variant does not hide evidence for the remaining passive source types. A single
bounded retry is allowed only for the known transient hierarchy bootstrap failure
seen during live GF#7 qualification. No likes, follows, replies, DMs,
Create/Upload UI, or Post action are performed.
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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.boost_explore_matrix import (  # noqa: E402
    BoostExploreMatrixError,
    child_passed,
    is_transient_hierarchy_failure,
    matrix_summary,
    normalize_sources,
)
from genfarmer_automation.warmup_session import load_shareable  # noqa: E402


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_child(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=240.0,
            check=False,
        )
        return proc.returncode, proc.stdout or ""
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return 124, str(output) + "\nERROR: Explore child timed out\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Passive TikTok Boost Explore qualification matrix")
    ap.add_argument("--device", required=True)
    ap.add_argument("--keyword")
    ap.add_argument("--hashtag")
    ap.add_argument("--account")
    ap.add_argument("--link")
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    raw_sources = []
    for kind in ("keyword", "hashtag", "account", "link"):
        value = getattr(args, kind)
        if value is not None:
            raw_sources.append((kind, value))

    try:
        sources = normalize_sources(raw_sources)
    except BoostExploreMatrixError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-boost-explore-matrix-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-boost-explore-matrix.shareable.json"

    rows: list[dict[str, Any]] = []
    private_sources = []
    print("=" * 78)
    print("TIKTOK BOOST EXPLORE QUALIFICATION MATRIX")
    print("=" * 78)

    for index, source in enumerate(sources, start=1):
        private_sources.append({"index": index, "type": source.source_type, "value": source.value})
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "tiktok_boost_explore.py"),
            "--type", source.source_type,
            "--value", source.value,
            "--device", args.device,
            "--preferred-hierarchy-port", str(args.preferred_hierarchy_port),
        ]
        if args.apply:
            cmd.append("--apply")

        final_returncode = 124
        final_output = ""
        final_payload: dict[str, Any] | None = None
        retry_count = 0

        for attempt in range(1, 3):
            returncode, output = _run_child(cmd)
            (private / f"source-{index:02d}-{source.source_type}-attempt-{attempt:02d}.log").write_text(
                output, encoding="utf-8", errors="replace"
            )
            payload = load_shareable(ROOT, output)
            if not isinstance(payload, dict):
                payload = None

            final_returncode = returncode
            final_output = output
            final_payload = payload

            expected = "PASS" if args.apply else "DRY_RUN_READY"
            passed = (
                child_passed(returncode, payload)
                if args.apply
                else returncode == 0 and isinstance(payload, dict) and payload.get("status") == expected
            )
            if passed:
                break

            if not args.apply or attempt >= 2 or not is_transient_hierarchy_failure(payload):
                break

            retry_count += 1
            print(
                f"[{index}/{len(sources)}] {source.source_type}: transient hierarchy bootstrap failure; "
                "retrying once"
            )
            time.sleep(1.25)

        # Stable convenience log for operators who want the final child attempt.
        (private / f"source-{index:02d}-{source.source_type}.log").write_text(
            final_output, encoding="utf-8", errors="replace"
        )

        expected = "PASS" if args.apply else "DRY_RUN_READY"
        passed = (
            child_passed(final_returncode, final_payload)
            if args.apply
            else final_returncode == 0
            and isinstance(final_payload, dict)
            and final_payload.get("status") == expected
        )
        status = str(final_payload.get("status")) if isinstance(final_payload, dict) else "MISSING_RESULT"
        row = {
            "index": index,
            "source_type": source.source_type,
            "source_value_private": True,
            "status": status,
            "passed": passed,
            "transient_retry_count": retry_count,
        }
        if isinstance(final_payload, dict):
            row["context_verified"] = final_payload.get("context_verified")
            row["specialized_tab_selected"] = final_payload.get("specialized_tab_selected")
            if not passed and final_payload.get("reason"):
                row["reason"] = final_payload.get("reason")
        rows.append(row)
        print(
            f"[{index}/{len(sources)}] {source.source_type}: "
            f"{'PASS' if passed else 'BLOCKED'} status={status} retries={retry_count}"
        )

    (private / "sources.private.json").write_text(
        json.dumps(private_sources, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = matrix_summary(rows)
    if not args.apply and all(row["passed"] for row in rows):
        summary["status"] = "DRY_RUN_READY"
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "device_private": True,
        **summary,
        "sources": rows,
    }
    _write_json(shareable, result)

    print("-" * 78)
    print(f"Status:                     {result['status']}")
    print(f"Sources passed:             {summary['passed_sources']}/{summary['requested_sources']}")
    print("Engagement actions:         NONE")
    print("Publishing UI:              NOT ENTERED")
    print(f"Private evidence:           {private.relative_to(ROOT)}")
    print(f"Shareable result:           {shareable.relative_to(ROOT)}")
    print("=" * 78)
    return 0 if result["status"] in {"PASS", "DRY_RUN_READY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
