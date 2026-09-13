#!/usr/bin/env python3
"""Finalize the imported live feed-anchor app without another manual export.

The operator performs the one-time GenFarmer schema probe by entering the known
sentinel into ElementExists and saving the imported app. This script then:

1. discovers the exact live app by that sentinel rather than by duplicate name;
2. loads a locally ranked private selector candidate;
3. replaces only the already-observed sentinel field;
4. optionally renames the app to a clear qualified name;
5. writes the app back through the documented GenFarmer update endpoint;
6. re-reads and verifies the exact replacement and rename.

Dry-run is the default. Exact selector values and app IDs are not printed.
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

from genfarmer_automation.genfarmer_client import GenFarmerClient, GenFarmerError  # noqa: E402
from genfarmer_automation.live_feed_anchor import (  # noqa: E402
    LiveFeedAnchorError,
    patch_script_by_sentinel,
    sentinel_locations,
)

SENTINEL = "//*[@resource-id='__GF_SCHEMA_PROBE__']"
DEFAULT_NAME = "GF Lab - TikTok Feed Anchor QUALIFIED"


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
            if isinstance(candidate, (str, int)) and not isinstance(candidate, bool):
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
        if not isinstance(app_id, (str, int)) or isinstance(app_id, bool) or not isinstance(name, str):
            continue
        sid = str(app_id)
        if sid in seen:
            continue
        seen.add(sid)
        records.append(obj)
    return records


def app_object(detail: Any, app_id: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for obj in iter_dicts(detail):
        if str(obj.get("id")) != str(app_id):
            continue
        if isinstance(obj.get("script"), Mapping):
            matches.append(obj)
    if not matches:
        raise GenFarmerError("could not resolve live app object with script")
    matches.sort(key=lambda item: len(item.keys()), reverse=True)
    return matches[0]


def coerce_user_id(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise GenFarmerError("could not safely resolve numeric user id")


def printable_path(path: tuple[str | int, ...]) -> str:
    out = "$.data"
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def find_live_sentinel_app(client: GenFarmerClient, user_id: str | int | None) -> tuple[str, dict[str, Any], tuple[str | int, ...]]:
    candidates: list[tuple[str, dict[str, Any], tuple[str | int, ...]]] = []
    for page in range(1, 21):
        payload = client.list_apps(user_id=user_id, page=page, limit=100, order="desc", order_by="updatedAt")
        records = extract_app_records(payload)
        if not records:
            break
        for record in records:
            app_id = str(record["id"])
            detail = client.get_app(app_id)
            app = app_object(detail, app_id)
            locations = sentinel_locations(app, SENTINEL)
            if len(locations) == 1:
                _, path = locations[0]
                candidates.append((app_id, app, path))
            elif len(locations) > 1:
                raise GenFarmerError("one live app contains multiple schema sentinels; refusing ambiguous target")
        if len(records) < 100:
            break

    if len(candidates) != 1:
        raise GenFarmerError(
            f"expected exactly one live app containing the ElementExists schema sentinel; found {len(candidates)}"
        )
    return candidates[0]


def load_candidate(path: Path, index: int) -> tuple[dict[str, Any], str]:
    raw = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not (1 <= index <= len(raw)):
        raise LiveFeedAnchorError("ranked candidate file does not contain the requested candidate")
    selected = raw[index - 1]
    if not isinstance(selected, dict):
        raise LiveFeedAnchorError("ranked candidate entry is not an object")
    xpath = selected.get("xpath")
    if not isinstance(xpath, str) or not xpath.strip():
        raise LiveFeedAnchorError("ranked candidate has no XPath string")
    return selected, xpath


def main() -> int:
    ap = argparse.ArgumentParser(description="Finalize the live imported TikTok feed-anchor app by schema sentinel")
    ap.add_argument("candidates", type=Path, help="private ranked-candidates.private.json")
    ap.add_argument("--candidate", type=int, default=1, help="1-based ranked candidate index")
    ap.add_argument("--name", default=DEFAULT_NAME, help="clear live app name after finalization")
    ap.add_argument("--apply", action="store_true", help="write through the documented GenFarmer update endpoint")
    args = ap.parse_args()

    if args.candidate < 1:
        print("ERROR: --candidate must be >= 1", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    try:
        selected, xpath = load_candidate(args.candidates, args.candidate)
        read_client = GenFarmerClient(base_url, timeout=15.0, allow_mutations=False)
        current_user = discover_user_id(read_client.get_current_user())
        app_id, live_app, sentinel_path = find_live_sentinel_app(read_client, current_user)
        patched_script, patched_path = patch_script_by_sentinel(
            live_app,
            sentinel=SENTINEL,
            replacement=xpath,
        )
        if patched_path != sentinel_path:
            raise GenFarmerError("schema sentinel path changed during patch preparation")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = ROOT / "evidence" / f"genfarmer-live-feed-anchor-finalize-{stamp}"
        private = out / "private"
        private.mkdir(parents=True, exist_ok=True)
        (private / "before.app.json").write_text(
            json.dumps(live_app, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (private / "patched.script.json").write_text(
            json.dumps(patched_script, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report: dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "apply" if args.apply else "dry-run",
            "target_discovered_by_exact_sentinel": True,
            "current_name": str(live_app.get("name") or ""),
            "desired_name": args.name,
            "candidate_index": args.candidate,
            "candidate_kind": selected.get("kind"),
            "sentinel_path": printable_path(sentinel_path),
            "selector_value_private": True,
            "rename_verified": False,
            "selector_verified": False,
        }

        if args.apply:
            writer = GenFarmerClient(base_url, timeout=20.0, allow_mutations=True)
            writer.update_app(
                app_id=app_id,
                user_id=coerce_user_id(live_app.get("userId", current_user)),
                name=args.name,
                version=str(live_app.get("version") or "1.0.0"),
                description=str(live_app.get("description") or ""),
                script=patched_script,
            )

            reread = read_client.get_app(app_id)
            verified_app = app_object(reread, app_id)
            (private / "verified.app.json").write_text(
                json.dumps(verified_app, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            sentinel_after = sentinel_locations(verified_app, SENTINEL)
            replacement_after = sentinel_locations(verified_app, xpath)
            rename_verified = str(verified_app.get("name") or "") == args.name
            selector_verified = len(sentinel_after) == 0 and len(replacement_after) == 1
            report["rename_verified"] = rename_verified
            report["selector_verified"] = selector_verified
            if not rename_verified or not selector_verified:
                raise GenFarmerError("live app update completed but rename/selector verification failed closed")

        shareable = out / "genfarmer-live-feed-anchor-finalize.shareable.json"
        shareable.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("=" * 78)
        print("GENFARMER LIVE FEED-ANCHOR FINALIZER")
        print("=" * 78)
        print("Target discovery:           EXACT ELEMENTEXISTS SENTINEL")
        print(f"Current app name:           {report['current_name']}")
        print(f"Desired app name:           {args.name}")
        print(f"Schema field:               {report['sentinel_path']}")
        print(f"Ranked candidate:           {args.candidate} ({selected.get('kind', '<unknown>')})")
        print("Exact selector value:       PRIVATE / NOT PRINTED")
        print(f"Mode:                       {'APPLY' if args.apply else 'DRY-RUN'}")
        if args.apply:
            print(f"Rename verification:        {'PASS' if report['rename_verified'] else 'FAIL'}")
            print(f"Selector verification:      {'PASS' if report['selector_verified'] else 'FAIL'}")
            print("Manual export required:     NO")
        else:
            print("No GenFarmer state changed. Re-run with --apply after reviewing this target.")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        GenFarmerError,
        LiveFeedAnchorError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
