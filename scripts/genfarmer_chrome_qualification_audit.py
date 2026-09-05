#!/usr/bin/env python3
"""GET-only audit for the dedicated GenFarmer Chrome qualification flow.

The script reads ``GF Lab - Chrome Qualification`` and reports whether the
minimal browser-qualification actions and routing are present. Exact flow is
stored only under ignored private evidence; the shareable report contains only
semantic action/family counts and action-to-action edge pairs.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.flow import FlowDocument, find_flow  # noqa: E402
from genfarmer_automation.genfarmer_client import GenFarmerClient, GenFarmerError  # noqa: E402

SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/+-]{1,120}$")

# Phase A intentionally avoids depending on action-specific UI settings beyond
# StartApp/Adb. The ADB node can open the fixture URL and include a short shell
# delay before the screenshot. Pause is learned/qualified in Phase B.
PHASE_A_REQUIRED = (
    "Start",
    "StartApp",
    "Adb",
    "Screenshot",
    "StopApp",
    "Stop",
)

PHASE_B_REQUIRED = (
    "Pause",
    "Touch",
    "TypeText",
    "Press",
    "ElementExists",
    "Swipe",
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
            if isinstance(candidate, (str, int)):
                return candidate
        for key in ("user", "data", "result"):
            found = discover_user_id(value.get(key))
            if found is not None:
                return found
    return None


def extract_app_records(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
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
        out.append(obj)
    return out


def select_app(client: GenFarmerClient, user_id: str | int | None, app_id: str | None, app_name: str) -> Any:
    if app_id:
        return client.get_app(app_id)
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
        raise GenFarmerError(f"qualification app not found by exact name {app_name!r}")
    if len(matches) != 1:
        raise GenFarmerError(f"found {len(matches)} apps named {app_name!r}; pass --app-id")
    return client.get_app(next(iter(matches)))


def node_action(node: Mapping[str, Any]) -> str:
    data = node.get("data")
    if isinstance(data, Mapping):
        action = data.get("action")
        if isinstance(action, str) and SAFE_TOKEN_RE.fullmatch(action):
            return action
    family = node.get("type")
    if isinstance(family, str) and SAFE_TOKEN_RE.fullmatch(family):
        return f"<{family}>"
    return "<unknown>"


def main() -> int:
    ap = argparse.ArgumentParser(description="GET-only audit of GF Lab - Chrome Qualification")
    ap.add_argument("--app-id")
    ap.add_argument("--app-name", default="GF Lab - Chrome Qualification")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    client = GenFarmerClient(base_url, timeout=12.0, allow_mutations=False)
    try:
        user_id = discover_user_id(client.get_current_user())
        detail = select_app(client, user_id, args.app_id, args.app_name)
        flow = find_flow(detail)
        if flow is None:
            raise GenFarmerError("selected qualification app has no script.flow")
        doc = FlowDocument.from_flow(flow)
    except (GenFarmerError, Exception) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    id_to_action: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for node in doc.nodes:
        if not isinstance(node, Mapping):
            continue
        node_id = node.get("id")
        if not isinstance(node_id, (str, int)):
            continue
        action = node_action(node)
        id_to_action[str(node_id)] = action
        counts[action] += 1

    edge_pairs: Counter[tuple[str, str]] = Counter()
    for edge in doc.edges:
        if not isinstance(edge, Mapping):
            continue
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, (str, int)) or not isinstance(target, (str, int)):
            continue
        edge_pairs[(id_to_action.get(str(source), "<unknown>"), id_to_action.get(str(target), "<unknown>"))] += 1

    observed = set(counts)
    phase_a_missing = [x for x in PHASE_A_REQUIRED if x not in observed]
    phase_b_missing = [x for x in PHASE_B_REQUIRED if x not in observed]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-chrome-qualification-audit-{stamp}"
    private_dir = out_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "flow.raw.json").write_text(json.dumps(flow, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "catalog_format": 1,
        "privacy": "shareable semantic audit only; exact flow kept under ignored private evidence",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "nodes": len(doc.nodes),
        "edges": len(doc.edges),
        "action_counts": dict(sorted(counts.items())),
        "phase_a_required": list(PHASE_A_REQUIRED),
        "phase_a_missing": phase_a_missing,
        "phase_a_ready": not phase_a_missing and len(doc.edges) >= max(1, len(PHASE_A_REQUIRED) - 1),
        "phase_b_required": list(PHASE_B_REQUIRED),
        "phase_b_missing": phase_b_missing,
        "edge_pairs": [
            {"source_action": s, "target_action": t, "count": c}
            for (s, t), c in sorted(edge_pairs.items())
        ],
        "warnings": doc.validate_basic(),
    }
    shareable = out_dir / "chrome-qualification-audit.shareable.json"
    shareable.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER CHROME QUALIFICATION AUDIT")
    print("=" * 78)
    print(f"Flow: nodes={len(doc.nodes)} edges={len(doc.edges)}")
    print("Observed actions:")
    for action, count in sorted(counts.items()):
        print(f" - {action}: {count}")
    print(f"Phase A ready: {'YES' if report['phase_a_ready'] else 'NO'}")
    if phase_a_missing:
        print("Phase A missing:")
        for action in phase_a_missing:
            print(f" - {action}")
    print(f"Phase B missing: {len(phase_b_missing)}")
    if edge_pairs:
        print("Observed action routing:")
        for (source, target), count in sorted(edge_pairs.items()):
            print(f" - {source} -> {target}: {count}")
    print(f"Private exact flow: {private_dir.relative_to(ROOT) / 'flow.raw.json'}")
    print(f"Shareable result:  {shareable.relative_to(ROOT)}")
    print("GET only; no GenFarmer state was modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
