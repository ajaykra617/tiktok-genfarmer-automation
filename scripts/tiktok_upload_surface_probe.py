#!/usr/bin/env python3
"""Capture a read-only sanitized semantic snapshot of the current upload surface."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.adb_observer import AdbObserver  # noqa: E402
from genfarmer_automation.hierarchy_runtime import capture_hierarchy_batch  # noqa: E402
from genfarmer_automation.upload_surface import sanitized_upload_rows  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only semantic probe for TikTok/Android upload picker")
    ap.add_argument("--device", required=True)
    ap.add_argument("--preferred-hierarchy-port", type=int, default=8912)
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.device)
    out = ROOT / "evidence" / f"tiktok-upload-surface-{safe_device}-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    shareable = out / "tiktok-upload-surface.shareable.json"

    try:
        observer = AdbObserver(args.device)
        obs = observer.observe()
        batch = capture_hierarchy_batch(
            args.device,
            count=1,
            interval=0.0,
            preferred_port=args.preferred_hierarchy_port,
            helper_timeout=4.0,
            max_ports=12,
        )
        xml = batch.snapshots[0]
        (private / "surface.xml").write_text(xml, encoding="utf-8")
        observer.capture_screenshot(private / "surface.png")
        rows = sanitized_upload_rows(xml)
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "device": args.device,
            "foreground_package": obs.foreground_package,
            "foreground_activity": obs.foreground_activity,
            "hierarchy_provider": batch.provider,
            "safe_rows": [
                {
                    "package": row.package,
                    "class": row.class_name,
                    "resource_id": row.resource_id,
                    "text": row.text,
                    "content_desc": row.content_desc,
                    "bounds": list(row.bounds),
                    "clickable": row.clickable,
                }
                for row in rows
            ],
        }
        shareable.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        print("=" * 78)
        print("TIKTOK UPLOAD SURFACE PROBE")
        print("=" * 78)
        print(f"Foreground:                  {obs.foreground_package}/{obs.foreground_activity}")
        print(f"Hierarchy provider:          {batch.provider}")
        print(f"Safe semantic rows:          {len(rows)}")
        for index, row in enumerate(rows[:40], start=1):
            print(
                f"{index:02d}. pkg={row.package or '-'} class={row.class_name.rsplit('.', 1)[-1] or '-'} "
                f"clickable={'YES' if row.clickable else 'NO'} bounds={row.bounds} "
                f"text={row.text!r} desc={row.content_desc!r} rid={row.resource_id!r}"
            )
        if len(rows) > 40:
            print(f"... {len(rows) - 40} additional safe rows saved to shareable result")
        print(f"Private evidence:            {private.relative_to(ROOT)}")
        print(f"Shareable result:            {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
