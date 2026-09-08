#!/usr/bin/env python3
"""Apply a compiled .genfarm script to one existing GenFarmer app.

Dry-run by default. The target app is selected by exact name (or --app-id), the
compiled flow is validated locally, the current live script is preserved to
private evidence, and --apply performs the documented PUT then re-reads the app
to verify node/edge counts and exact flow hash.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.flow import FlowDocument, find_flow  # noqa: E402
from genfarmer_automation.genfarm_file import GenFarmDocument, GenFarmFileError  # noqa: E402
from genfarmer_automation.genfarmer_client import GenFarmerClient, GenFarmerError  # noqa: E402

DEFAULT_APP = "GF Lab - TikTok Warmup Qualification"


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


def iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


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


def extract_app_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obj in iter_dicts(value):
        app_id = obj.get("id")
        name = obj.get("name")
        if not isinstance(app_id, (str, int)) or not isinstance(name, str):
            continue
        sid = str(app_id)
        if sid in seen:
            continue
        seen.add(sid)
        records.append(obj)
    return records


def select_app(client: GenFarmerClient, user_id: str | int | None, app_id: str | None, app_name: str) -> tuple[str, Any]:
    if app_id:
        return app_id, client.get_app(app_id)
    matches: dict[str, dict[str, Any]] = {}
    for page in range(1, 21):
        payload = client.list_apps(user_id=user_id, page=page, limit=100)
        records = extract_app_records(payload)
        for record in records:
            if record.get("name") == app_name:
                matches[str(record["id"])] = record
        if not records or len(records) < 100:
            break
    if not matches:
        raise GenFarmerError(f"app not found by exact name {app_name!r}")
    if len(matches) != 1:
        raise GenFarmerError(f"found {len(matches)} apps named {app_name!r}; pass --app-id")
    app_id = next(iter(matches))
    return app_id, client.get_app(app_id)


def app_object(detail: Any, app_id: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for obj in iter_dicts(detail):
        if str(obj.get("id")) != str(app_id):
            continue
        if isinstance(obj.get("script"), Mapping):
            candidates.append(obj)
    if not candidates:
        raise GenFarmerError("could not find selected app object with script")
    candidates.sort(key=lambda item: len(item.keys()), reverse=True)
    return candidates[0]


def coerce_user_id(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise GenFarmerError(f"cannot safely resolve numeric user id from {value!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply a compiled .genfarm script to an existing GenFarmer app")
    ap.add_argument("compiled", type=Path)
    ap.add_argument("--app-name", default=DEFAULT_APP)
    ap.add_argument("--app-id")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    try:
        compiled = GenFarmDocument.load(args.compiled)
        compiled_flow = compiled.flow
        warnings = compiled_flow.validate_basic()
        if warnings:
            raise GenFarmerError("compiled graph has validation warnings: " + "; ".join(warnings))

        read_client = GenFarmerClient(base_url, timeout=15.0, allow_mutations=False)
        current_user = discover_user_id(read_client.get_current_user())
        app_id, detail = select_app(read_client, current_user, args.app_id, args.app_name)
        live_app = app_object(detail, app_id)
        live_flow_raw = find_flow(live_app)
        if live_flow_raw is None:
            raise GenFarmerError("target app has no script.flow")
        live_flow = FlowDocument.from_flow(live_flow_raw)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = ROOT / "evidence" / f"genfarm-apply-{stamp}"
        private_dir = out_dir / "private"
        private_dir.mkdir(parents=True, exist_ok=True)
        (private_dir / "before.flow.json").write_text(json.dumps(live_flow.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        (private_dir / "compiled.flow.json").write_text(json.dumps(compiled_flow.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        report: dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "apply" if args.apply else "dry-run",
            "app_name": args.app_name,
            "before_nodes": len(live_flow.nodes),
            "before_edges": len(live_flow.edges),
            "compiled_nodes": len(compiled_flow.nodes),
            "compiled_edges": len(compiled_flow.edges),
            "flow_changed": live_flow.sha256() != compiled_flow.sha256(),
            "verified": False,
        }

        if args.apply:
            script = deepcopy(dict(live_app.get("script", {})))
            script["flow"] = compiled_flow.to_dict()
            writer = GenFarmerClient(base_url, timeout=20.0, allow_mutations=True)
            writer.update_app(
                app_id=app_id,
                user_id=coerce_user_id(live_app.get("userId", current_user)),
                name=str(live_app.get("name") or args.app_name),
                version=str(live_app.get("version") or "1.0.0"),
                description=str(live_app.get("description") or ""),
                script=script,
            )
            reread = read_client.get_app(app_id)
            verified_raw = find_flow(reread)
            if verified_raw is None:
                raise GenFarmerError("PUT completed but flow could not be re-read")
            verified = FlowDocument.from_flow(verified_raw)
            if verified.sha256() != compiled_flow.sha256():
                raise GenFarmerError("post-PUT flow hash does not match compiled flow")
            (private_dir / "verified.flow.json").write_text(json.dumps(verified.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            report["verified"] = True

        shareable = out_dir / "genfarm-apply.shareable.json"
        shareable.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("=" * 78)
        print("GENFARM COMPILED FLOW APPLY")
        print("=" * 78)
        print(f"Target app: {args.app_name}")
        print(f"Compiled:   {args.compiled}")
        print(f"Current:    nodes={report['before_nodes']} edges={report['before_edges']}")
        print(f"Compiled:   nodes={report['compiled_nodes']} edges={report['compiled_edges']}")
        print(f"Flow changed: {'YES' if report['flow_changed'] else 'NO'}")
        print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
        if args.apply:
            print(f"Post-PUT verification: {'PASS' if report['verified'] else 'FAIL'}")
        else:
            print("No GenFarmer state changed. Re-run with --apply after reviewing this plan.")
        print(f"Private evidence: {private_dir.relative_to(ROOT)}")
        print(f"Shareable result: {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0
    except (GenFarmFileError, GenFarmerError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
