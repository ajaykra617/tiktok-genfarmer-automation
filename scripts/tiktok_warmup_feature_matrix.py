#!/usr/bin/env python3
"""Run the remaining passive TikTok warm-up feature qualifications in one command."""
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

from genfarmer_automation.warmup_matrix import build_matrix  # noqa: E402
from genfarmer_automation.warmup_session import load_shareable  # noqa: E402


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Qualify passive TikTok warm-up feature matrix")
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--candidate", type=int, default=8)
    ap.add_argument("--device", required=True)
    ap.add_argument("--keyword")
    ap.add_argument("--hashtag")
    ap.add_argument("--dwell-min", type=float, default=3.0)
    ap.add_argument("--dwell-max", type=float, default=6.0)
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-warmup-feature-matrix-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-warmup-feature-matrix.shareable.json"

    rows = build_matrix(keyword=args.keyword, hashtag=args.hashtag)
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "features": [row.feature for row in rows],
        "passive_only": True,
        "engagement_actions": 0,
        "results": [],
    }

    try:
        for index, row in enumerate(rows, start=1):
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "tiktok_warmup_feature.py"),
                str(args.candidates),
                "--candidate", str(args.candidate),
                "--device", args.device,
                "--feature", row.feature,
                "--dwell-min", str(args.dwell_min),
                "--dwell-max", str(args.dwell_max),
                "--preferred-hierarchy-port", str(args.preferred_hierarchy_port),
                "--seed", str(1000 + index),
            ]
            if row.value is not None:
                cmd.extend(["--value", row.value])
            if args.apply:
                cmd.append("--apply")

            print(f"[{index}/{len(rows)}] {row.feature}")
            proc = subprocess.run(
                cmd,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=210.0,
                check=False,
            )
            output = proc.stdout or ""
            (private / f"{index:02d}-{row.feature}.log").write_text(output, encoding="utf-8", errors="replace")
            payload = load_shareable(ROOT, output)
            expected = "PASS" if args.apply else "DRY_RUN_READY"
            passed = proc.returncode == 0 and payload is not None and payload.get("status") == expected
            result["results"].append(
                {
                    "feature": row.feature,
                    "status": payload.get("status") if payload else "NO_RESULT",
                    "passed": passed,
                }
            )
            if not passed:
                result["status"] = "BLOCKED"
                result["blocked_feature"] = row.feature
                _write_json(shareable, result)
                print(output.rstrip())
                print(f"ERROR: feature matrix blocked at {row.feature}", file=sys.stderr)
                print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
                return 1
            print(f"  PASS {row.feature}")

        result["status"] = "PASS" if args.apply else "DRY_RUN_READY"
        _write_json(shareable, result)
        print("=" * 78)
        print("TIKTOK WARM-UP FEATURE MATRIX")
        print("=" * 78)
        print(f"Status:                     {result['status']}")
        print(f"Features passed:            {len(rows)}/{len(rows)}")
        print("Engagement actions:         NONE")
        print(f"Private logs:               {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except subprocess.TimeoutExpired as exc:
        result["status"] = "BLOCKED"
        result["reason"] = f"feature subprocess timed out: {exc}"
        _write_json(shareable, result)
        print(f"ERROR: {result['reason']}", file=sys.stderr)
        print(f"Shareable result: {shareable.relative_to(ROOT)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
