#!/usr/bin/env python3
"""Add verified GenFarmer node templates to the TikTok warm-up lab app.

This tool intentionally adds nodes *disconnected* from the existing green
route. That lets the operator configure a new node once in GenFarmer, save it,
and then capture the exact serialized settings/edge semantics before Python
starts wiring that node automatically.

Safety properties:
- dry-run by default;
- exact app-name matching;
- clones only exact live templates from ignored local evidence;
- preserves the complete existing app script/flow;
- does not invent action-specific options;
- does not touch existing edges;
- verifies the PUT by re-reading the app when --apply is used.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping
import uuid

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.flow import FlowDocument, find_flow  # noqa: E402
from genfarmer_automation.flow_registry import (  # noqa: E402
    TemplateRegistry,
    TemplateRegistryError,
    semantic_kind,
)
from genfarmer_automation.genfarmer_client import GenFarmerClient, GenFarmerError  # noqa: E402

DEFAULT_APP = "GF Lab - TikTok Warmup Qualification"
DEFAULT_ACTIONS = ("ElementExists", "Swipe")


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
        raise GenFarmerError("could not find selected app object with script in API detail payload")
    candidates.sort(key=lambda item: len(item.keys()), reverse=True)
    return candidates[0]


def latest_template_flow() -> Path:
    patterns = (
        "evidence/genfarmer-lab-template-capture-*/private/flow.raw.json",
        "evidence/genfarmer-lab-schema-matrix-*/private/flow.raw.json",
    )
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(ROOT.glob(pattern))
    paths = [p for p in paths if p.is_file()]
    if not paths:
        raise TemplateRegistryError(
            "no private live-template flow found under evidence; run the existing lab template capture first"
        )
    return max(paths, key=lambda p: p.stat().st_mtime_ns)


def node_action(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, Mapping):
        action = data.get("action")
        if isinstance(action, str) and action:
            return action
    return None


def action_counts(flow: Mapping[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    nodes = flow.get("nodes")
    if not isinstance(nodes, list):
        return counts
    for node in nodes:
        if isinstance(node, Mapping):
            action = node_action(node)
            if action:
                counts[action] += 1
    return counts


def resolve_kind(registry: TemplateRegistry, action: str) -> str:
    matches = [kind for kind in registry.available_kinds() if kind.endswith(f":{action}")]
    if len(matches) != 1:
        raise TemplateRegistryError(
            f"expected exactly one observed template kind for action {action!r}; found {matches}"
        )
    return matches[0]


def place_node(node: dict[str, Any], *, x: float, y: float) -> None:
    position = node.get("position")
    if isinstance(position, dict):
        position["x"] = x
        position["y"] = y


def next_layout_origin(doc: FlowDocument) -> tuple[float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for node in doc.nodes:
        if not isinstance(node, Mapping):
            continue
        pos = node.get("position")
        if not isinstance(pos, Mapping):
            continue
        x = pos.get("x")
        y = pos.get("y")
        if isinstance(x, (int, float)):
            xs.append(float(x))
        if isinstance(y, (int, float)):
            ys.append(float(y))
    return ((max(xs) if xs else 0.0) + 300.0, min(ys) if ys else 0.0)


def coerce_user_id(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise GenFarmerError(f"cannot safely resolve numeric user id from {value!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Add disconnected verified nodes to TikTok warm-up lab app")
    ap.add_argument("--app-name", default=DEFAULT_APP)
    ap.add_argument("--app-id")
    ap.add_argument("--actions", nargs="+", default=list(DEFAULT_ACTIONS))
    ap.add_argument("--template-flow", type=Path, help="private exact flow.raw.json; defaults to latest lab capture")
    ap.add_argument("--allow-duplicates", action="store_true")
    ap.add_argument("--apply", action="store_true", help="perform the documented PUT; otherwise dry-run only")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    read_client = GenFarmerClient(base_url, timeout=15.0, allow_mutations=False)
    try:
        current_user = discover_user_id(read_client.get_current_user())
        app_id, detail = select_app(read_client, current_user, args.app_id, args.app_name)
        app = app_object(detail, app_id)
        flow = find_flow(app)
        if flow is None:
            raise GenFarmerError("selected app has no script.flow")
        doc = FlowDocument.from_flow(flow)
        template_path = args.template_flow or latest_template_flow()
        registry = TemplateRegistry.from_raw_corpus(template_path)

        before_counts = action_counts(doc.to_dict())
        x, y = next_layout_origin(doc)
        added: list[dict[str, str]] = []
        skipped: list[str] = []
        for index, action in enumerate(args.actions):
            if not args.allow_duplicates and before_counts.get(action, 0) > 0:
                skipped.append(action)
                continue
            kind = resolve_kind(registry, action)
            new_id = f"py-{action.lower()}-{uuid.uuid4().hex[:10]}"
            clone = registry.clone(kind, new_id=new_id)
            place_node(clone, x=x, y=y + index * 150.0)
            doc.nodes.append(clone)
            added.append({"action": action, "kind": kind, "id": new_id})

        warnings = doc.validate_basic()
        if warnings:
            raise GenFarmerError("refusing mutation because graph validation warnings exist: " + "; ".join(warnings))

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = ROOT / "evidence" / f"tiktok-warmup-node-add-{stamp}"
        private_dir = out_dir / "private"
        private_dir.mkdir(parents=True, exist_ok=True)
        (private_dir / "before.flow.json").write_text(json.dumps(flow, ensure_ascii=False, indent=2), encoding="utf-8")
        (private_dir / "planned.flow.json").write_text(json.dumps(doc.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        report: dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "apply" if args.apply else "dry-run",
            "app_name": args.app_name,
            "template_source": template_path.parent.parent.name,
            "before_nodes": len(flow.get("nodes", [])),
            "before_edges": len(flow.get("edges", [])),
            "planned_nodes": len(doc.nodes),
            "planned_edges": len(doc.edges),
            "added_actions": [item["action"] for item in added],
            "skipped_existing_actions": skipped,
            "existing_edges_modified": False,
            "policy": "new nodes are exact live clones and remain disconnected until settings/edge semantics are learned",
        }

        if args.apply and added:
            script = deepcopy(dict(app.get("script", {})))
            script["flow"] = doc.to_dict()
            user_id = app.get("userId", current_user)
            write_client = GenFarmerClient(base_url, timeout=20.0, allow_mutations=True)
            write_client.update_app(
                app_id=app_id,
                user_id=coerce_user_id(user_id),
                name=str(app.get("name") or args.app_name),
                version=str(app.get("version") or "1.0.0"),
                description=str(app.get("description") or ""),
                script=script,
            )
            verified_detail = read_client.get_app(app_id)
            verified_flow = find_flow(verified_detail)
            if verified_flow is None:
                raise GenFarmerError("PUT returned but app flow could not be re-read")
            verified_counts = action_counts(verified_flow)
            for item in added:
                action = item["action"]
                if verified_counts[action] < before_counts[action] + 1:
                    raise GenFarmerError(f"post-PUT verification failed for added action {action}")
            if len(verified_flow.get("edges", [])) != len(flow.get("edges", [])):
                raise GenFarmerError("post-PUT verification found unexpected edge-count change")
            (private_dir / "verified.flow.json").write_text(
                json.dumps(verified_flow, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            report["verified"] = True
        else:
            report["verified"] = False

        shareable = out_dir / "tiktok-warmup-node-add.shareable.json"
        shareable.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("=" * 78)
        print("GENFARMER TIKTOK WARM-UP NODE ADD")
        print("=" * 78)
        print(f"App: {args.app_name}")
        print(f"Current flow: nodes={report['before_nodes']} edges={report['before_edges']}")
        print(f"Template source: {template_path.relative_to(ROOT)}")
        print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
        if added:
            print("Planned exact-template nodes:")
            for item in added:
                print(f" - {item['action']} ({item['kind']})")
        if skipped:
            print("Skipped because already present:")
            for action in skipped:
                print(f" - {action}")
        print(f"Planned flow: nodes={report['planned_nodes']} edges={report['planned_edges']}")
        print("Existing edges modified: NO")
        if args.apply:
            print(f"Post-PUT verification: {'PASS' if report['verified'] else 'NO CHANGE'}")
        else:
            print("No GenFarmer state changed. Re-run with --apply after reviewing this plan.")
        print(f"Private evidence: {private_dir.relative_to(ROOT)}")
        print(f"Shareable result: {shareable.relative_to(ROOT)}")
        print("=" * 78)
        return 0

    except (GenFarmerError, TemplateRegistryError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
