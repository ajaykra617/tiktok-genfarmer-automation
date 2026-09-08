#!/usr/bin/env python3
"""Discover the latest persisted GenFarmer run/task binding for a compiled app.

Read-only. The compiled .genfarm preserved app identity is used as the target.
Exact run/task/device identifiers are written only to ignored private evidence;
console/shareable output reports only whether the required pieces were found.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.genfarm_file import GenFarmDocument, GenFarmFileError  # noqa: E402
from genfarmer_automation.genfarmer_client import GenFarmerClient, GenFarmerError  # noqa: E402
from genfarmer_automation.run_binding import extract_run_bindings, newest_for_app  # noqa: E402


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def discover_user_id(value: Any) -> str | int | None:
    if isinstance(value, Mapping):
        for key in ("id", "userId", "user_id"):
            candidate = value.get(key)
            if isinstance(candidate, (str, int)):
                return candidate
        for key in ("user", "data", "result"):
            found = discover_user_id(value.get(key))
            if found is not None:
                return found
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only discovery of a recent GenFarmer run binding")
    ap.add_argument("compiled", type=Path, help="compiled .genfarm whose preserved app identity should be matched")
    ap.add_argument("--pages", type=int, default=5, help="recent run pages to inspect (1..20)")
    args = ap.parse_args()
    if not (1 <= args.pages <= 20):
        print("ERROR: --pages must be 1..20", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence" / f"genfarmer-run-binding-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)

    try:
        doc = GenFarmDocument.load(args.compiled)
        payload = doc.to_dict()
        raw_app_id = payload.get("id")
        if not isinstance(raw_app_id, (str, int)) or not str(raw_app_id):
            raise GenFarmerError("compiled export has no preserved app id; use a build derived from the live app export")
        app_id = str(raw_app_id)

        client = GenFarmerClient(base_url, timeout=15.0, allow_mutations=False)
        user_id = discover_user_id(client.get_current_user())
        pages: list[Any] = []
        bindings = []
        for page in range(1, args.pages + 1):
            value = client.list_runs(user_id=user_id, page=page, limit=100)
            pages.append(value)
            bindings.extend(extract_run_bindings(value))
        (private / "runs.raw.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")

        matches = [item for item in bindings if item.app_id == app_id]
        selected = newest_for_app(bindings, app_id)
        if selected is not None:
            (private / "binding.private.json").write_text(
                json.dumps(selected.private_dict(), indent=2), encoding="utf-8"
            )

        shareable = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "compiled_file": args.compiled.name,
            "target_app_identity_present": True,
            "run_records_scanned": len(bindings),
            "matching_runs": len(matches),
            "latest_binding_found": selected is not None,
            "task_id_present": bool(selected and selected.task_id),
            "device_refs_found": len(selected.device_ids) if selected else 0,
            "status_present": bool(selected and selected.status is not None),
            "created_at_present": bool(selected and selected.created_at),
            "read_only": True,
        }
        shareable_path = out / "genfarmer-run-binding.shareable.json"
        shareable_path.write_text(json.dumps(shareable, indent=2), encoding="utf-8")

        print("=" * 78)
        print("GENFARMER TIKTOK RUN BINDING PROBE")
        print("=" * 78)
        print(f"Compiled:             {args.compiled.name}")
        print(f"Run records scanned:  {len(bindings)}")
        print(f"Matching app runs:    {len(matches)}")
        print(f"Latest binding found: {'YES' if selected else 'NO'}")
        if selected:
            print(f"Task binding present: {'YES' if selected.task_id else 'NO'}")
            print(f"Device refs found:    {len(selected.device_ids)}")
            print(f"Status present:       {'YES' if selected.status is not None else 'NO'}")
            print("Private binding:      " + str((private / "binding.private.json").relative_to(ROOT)))
        else:
            print("Next: run the target app once in GenFarmer, then rerun this read-only probe.")
        print(f"Private raw evidence: {private.relative_to(ROOT)}")
        print(f"Shareable result:     {shareable_path.relative_to(ROOT)}")
        print("Read-only: no GenFarmer/device state was changed.")
        print("=" * 78)
        return 0 if selected else 1
    except (GenFarmFileError, GenFarmerError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
