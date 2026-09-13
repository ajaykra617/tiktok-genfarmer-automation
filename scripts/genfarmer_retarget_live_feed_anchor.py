#!/usr/bin/env python3
"""Retarget the qualified live GenFarmer feed anchor to another ranked selector.

The script never selects a live app by display name. It discovers exactly one
live app whose ElementExists node contains the exact current private selector,
then replaces only that already-observed field with another ranked private
selector and verifies the result after the documented GenFarmer update call.

Dry-run is the default. Exact selector values and app IDs are never printed.
"""
from __future__ import annotations

import argparse
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


def load_xpath(path: Path, index: int) -> tuple[str, str]:
    raw = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not (1 <= index <= len(raw)):
        raise LiveFeedAnchorError("ranked candidate file does not contain the requested candidate")
    item = raw[index - 1]
    if not isinstance(item, Mapping):
        raise LiveFeedAnchorError("ranked candidate entry is not an object")
    xpath = item.get("xpath")
    kind = item.get("kind")
    if not isinstance(xpath, str) or not xpath.strip():
        raise LiveFeedAnchorError("ranked candidate has no XPath string")
    return xpath, str(kind or "<unknown>")


def find_app_by_current_selector(
    client: GenFarmerClient,
    user_id: str | int | None,
    current_xpath: str,
) -> tuple[str, dict[str, Any]]:
    matches: list[tuple[str, dict[str, Any]]] = []
    for page in range(1, 21):
        payload = client.list_apps(user_id=user_id, page=page, limit=100, order="desc", order_by="updatedAt")
        records = extract_app_records(payload)
        if not records:
            break
        for record in records:
            app_id = str(record["id"])
            app = app_object(client.get_app(app_id), app_id)
            locations = sentinel_locations(app, current_xpath)
            if len(locations) == 1:
                matches.append((app_id, app))
            elif len(locations) > 1:
                raise GenFarmerError("one live app contains the current selector multiple times; refusing ambiguous retarget")
        if len(records) < 100:
            break
    if len(matches) != 1:
        raise GenFarmerError(
            f"expected exactly one live app containing the current private feed selector; found {len(matches)}"
        )
    return matches[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Retarget the live qualified TikTok feed anchor between ranked candidates")
    ap.add_argument("candidates", type=Path, help="private ranked-candidates.private.json")
    ap.add_argument("--from-candidate", type=int, default=1, help="currently deployed 1-based candidate index")
    ap.add_argument("--to-candidate", type=int, required=True, help="replacement 1-based candidate index")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.from_candidate < 1 or args.to_candidate < 1:
        print("ERROR: candidate indices must be >= 1", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    try:
        current_xpath, current_kind = load_xpath(args.candidates, args.from_candidate)
        target_xpath, target_kind = load_xpath(args.candidates, args.to_candidate)
        if current_xpath == target_xpath:
            raise LiveFeedAnchorError("source and replacement candidates resolve to the same XPath")

        read_client = GenFarmerClient(base_url, timeout=15.0, allow_mutations=False)
        current_user = discover_user_id(read_client.get_current_user())
        app_id, live_app = find_app_by_current_selector(read_client, current_user, current_xpath)
        patched_script, _ = patch_script_by_sentinel(
            live_app,
            sentinel=current_xpath,
            replacement=target_xpath,
        )

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = ROOT / "evidence" / f"genfarmer-live-feed-anchor-retarget-{stamp}"
        private = out / "private"
        private.mkdir(parents=True, exist_ok=True)
        (private / "before.app.json").write_text(json.dumps(live_app, ensure_ascii=False, indent=2), encoding="utf-8")

        print("=" * 78)
        print("GENFARMER LIVE FEED-ANCHOR RETARGET")
        print("=" * 78)
        print("Target discovery:           EXACT CURRENT PRIVATE SELECTOR")
        print(f"Current ranked candidate:  {args.from_candidate} ({current_kind})")
        print(f"Replacement candidate:     {args.to_candidate} ({target_kind})")
        print("Exact selector values:      PRIVATE / NOT PRINTED")

        if not args.apply:
            print("Mode:                       DRY-RUN")
            print("No GenFarmer state changed. Re-run with --apply after reviewing the target ranks.")
            return 0

        user_id = coerce_user_id(live_app.get("userId", current_user))
        name = live_app.get("name")
        version = live_app.get("version")
        if not isinstance(name, str) or not name:
            raise GenFarmerError("live app has no usable name")
        if not isinstance(version, str) or not version:
            version = "1.0.0"
        description = live_app.get("description")
        if not isinstance(description, str):
            description = ""

        write_client = GenFarmerClient(base_url, timeout=20.0, allow_mutations=True)
        write_client.update_app(
            app_id=app_id,
            user_id=user_id,
            name=name,
            version=version,
            script=patched_script,
            description=description,
        )

        after = app_object(read_client.get_app(app_id), app_id)
        current_remaining = sentinel_locations(after, current_xpath)
        target_locations = sentinel_locations(after, target_xpath)
        passed = len(current_remaining) == 0 and len(target_locations) == 1
        (private / "after.app.json").write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
        shareable = out / "genfarmer-live-feed-anchor-retarget.shareable.json"
        shareable.write_text(
            json.dumps(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "status": "PASS" if passed else "FAIL",
                    "from_candidate": args.from_candidate,
                    "to_candidate": args.to_candidate,
                    "current_kind": current_kind,
                    "target_kind": target_kind,
                    "selector_values_private": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("Mode:                       APPLY")
        print(f"Replacement verification:  {'PASS' if passed else 'FAIL'}")
        print(f"Private evidence:           {private.relative_to(ROOT)}")
        print(f"Shareable result:           {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0 if passed else 1
    except (OSError, json.JSONDecodeError, LiveFeedAnchorError, GenFarmerError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
