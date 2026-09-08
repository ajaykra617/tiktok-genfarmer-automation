#!/usr/bin/env python3
"""Compare a compiled .genfarm flow with the live GenFarmer app after a PUT.

This is read-only. It distinguishes harmless editor/server normalization from
runtime-significant changes by comparing a semantic projection of nodes and
edges while still reporting whether the full lossless flow hash is exact.

Private exact flows are written only under ignored evidence/. Console/shareable
output contains action counts, routing, and differing JSON paths, never scalar
option values.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
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


def select_app(
    client: GenFarmerClient,
    user_id: str | int | None,
    compiled_payload: Mapping[str, Any],
    app_id: str | None,
    app_name: str,
) -> tuple[str, str, Any]:
    if app_id:
        return app_id, "explicit --app-id", client.get_app(app_id)

    compiled_id = compiled_payload.get("id")
    if isinstance(compiled_id, (str, int)) and str(compiled_id):
        sid = str(compiled_id)
        try:
            return sid, "compiled export identity", client.get_app(sid)
        except Exception:
            pass

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
    sid = next(iter(matches))
    return sid, "unique exact name", client.get_app(sid)


def action_of(node: Mapping[str, Any]) -> str:
    data = node.get("data")
    if isinstance(data, Mapping):
        action = data.get("action")
        if isinstance(action, str) and action:
            return action
    family = node.get("type")
    return f"<{family}>" if isinstance(family, str) else "<unknown>"


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def semantic_node(node: Mapping[str, Any]) -> dict[str, Any]:
    data = node.get("data")
    data_map = data if isinstance(data, Mapping) else {}
    return {
        "id": str(node.get("id")),
        "type": node.get("type"),
        "action": data_map.get("action"),
        "options": data_map.get("options") if isinstance(data_map.get("options"), Mapping) else data_map.get("options"),
        "successNode": data_map.get("successNode"),
        "failNode": data_map.get("failNode"),
        "startLoopNode": data_map.get("startLoopNode"),
    }


def semantic_edge(edge: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": str(edge.get("source")),
        "target": str(edge.get("target")),
        "sourceHandle": edge.get("sourceHandle"),
        "targetHandle": edge.get("targetHandle"),
    }


def semantic_flow(doc: FlowDocument) -> dict[str, Any]:
    nodes = [semantic_node(node) for node in doc.nodes if isinstance(node, Mapping)]
    nodes.sort(key=lambda item: item["id"])
    edges = [semantic_edge(edge) for edge in doc.edges if isinstance(edge, Mapping)]
    edges.sort(key=lambda item: (item["source"], item["target"], str(item["sourceHandle"]), str(item["targetHandle"])))
    return {"nodes": nodes, "edges": edges}


def diff_paths(a: Any, b: Any, path: str = "$", limit: int = 80) -> list[str]:
    out: list[str] = []

    def walk(x: Any, y: Any, p: str) -> None:
        if len(out) >= limit:
            return
        if type(x) is not type(y):
            out.append(f"{p} [type]")
            return
        if isinstance(x, Mapping):
            keys = sorted(set(map(str, x.keys())) | set(map(str, y.keys())))
            for key in keys:
                if len(out) >= limit:
                    break
                if key not in x or key not in y:
                    out.append(f"{p}.{key} [missing]")
                else:
                    walk(x[key], y[key], f"{p}.{key}")
            return
        if isinstance(x, list):
            if len(x) != len(y):
                out.append(f"{p} [length]")
            for i, (xi, yi) in enumerate(zip(x, y)):
                if len(out) >= limit:
                    break
                walk(xi, yi, f"{p}[{i}]")
            return
        if x != y:
            out.append(p)

    walk(a, b, path)
    return out


def action_counts(doc: FlowDocument) -> Counter[str]:
    counts: Counter[str] = Counter()
    for node in doc.nodes:
        if isinstance(node, Mapping):
            counts[action_of(node)] += 1
    return counts


def route_pairs(doc: FlowDocument) -> list[str]:
    id_to_action = {
        str(node.get("id")): action_of(node)
        for node in doc.nodes
        if isinstance(node, Mapping) and isinstance(node.get("id"), (str, int))
    }
    pairs: list[str] = []
    for edge in doc.edges:
        if not isinstance(edge, Mapping):
            continue
        s = str(edge.get("source"))
        t = str(edge.get("target"))
        pairs.append(f"{id_to_action.get(s, '<unknown>')} -> {id_to_action.get(t, '<unknown>')}")
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only semantic verification of a compiled flow against live GenFarmer")
    ap.add_argument("compiled", type=Path)
    ap.add_argument("--app-name", default=DEFAULT_APP)
    ap.add_argument("--app-id")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    try:
        compiled_doc = GenFarmDocument.load(args.compiled)
        compiled_payload = compiled_doc.to_dict()
        compiled_flow = compiled_doc.flow
        read_client = GenFarmerClient(base_url, timeout=15.0, allow_mutations=False)
        current_user = discover_user_id(read_client.get_current_user())
        app_id, selection, live_detail = select_app(
            read_client, current_user, compiled_payload, args.app_id, args.app_name
        )
        live_raw = find_flow(live_detail)
        if live_raw is None:
            raise GenFarmerError("target app has no script.flow")
        live_flow = FlowDocument.from_flow(live_raw)

        compiled_sem = semantic_flow(compiled_flow)
        live_sem = semantic_flow(live_flow)
        exact_equal = compiled_flow.sha256() == live_flow.sha256()
        semantic_equal = canonical_hash(compiled_sem) == canonical_hash(live_sem)
        sem_diffs = diff_paths(compiled_sem, live_sem)
        full_diffs = [] if exact_equal else diff_paths(compiled_flow.to_dict(), live_flow.to_dict(), limit=40)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = ROOT / "evidence" / f"genfarm-live-verify-{stamp}"
        private_dir = out_dir / "private"
        private_dir.mkdir(parents=True, exist_ok=True)
        (private_dir / "compiled.flow.json").write_text(
            json.dumps(compiled_flow.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (private_dir / "live.flow.json").write_text(
            json.dumps(live_flow.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "app_name": args.app_name,
            "selection": selection,
            "compiled_nodes": len(compiled_flow.nodes),
            "compiled_edges": len(compiled_flow.edges),
            "live_nodes": len(live_flow.nodes),
            "live_edges": len(live_flow.edges),
            "exact_flow_equal": exact_equal,
            "semantic_runtime_equal": semantic_equal,
            "compiled_actions": dict(sorted(action_counts(compiled_flow).items())),
            "live_actions": dict(sorted(action_counts(live_flow).items())),
            "compiled_route": route_pairs(compiled_flow),
            "live_route": route_pairs(live_flow),
            "semantic_diff_paths": sem_diffs,
            "full_diff_paths_sample": full_diffs,
        }
        shareable = out_dir / "genfarm-live-verify.shareable.json"
        shareable.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("=" * 78)
        print("GENFARM LIVE FLOW VERIFICATION")
        print("=" * 78)
        print(f"Target app: {args.app_name}")
        print(f"Selection:  {selection}")
        print(f"Compiled:   nodes={len(compiled_flow.nodes)} edges={len(compiled_flow.edges)}")
        print(f"Live:       nodes={len(live_flow.nodes)} edges={len(live_flow.edges)}")
        print(f"Exact lossless flow match: {'YES' if exact_equal else 'NO'}")
        print(f"Runtime-semantic match:    {'YES' if semantic_equal else 'NO'}")
        if semantic_equal and not exact_equal:
            print("Interpretation: GenFarmer normalized editor/non-runtime fields; runtime graph/options/routing still match.")
        if not semantic_equal:
            print("Runtime-significant differing paths (values intentionally hidden):")
            for path in sem_diffs[:40]:
                print(f" - {path}")
        elif full_diffs:
            print("Sample non-runtime differing paths (values intentionally hidden):")
            for path in full_diffs[:20]:
                print(f" - {path}")
        print("Live routing:")
        for pair in route_pairs(live_flow):
            print(f" - {pair}")
        print(f"Private evidence: {private_dir.relative_to(ROOT)}")
        print(f"Shareable result: {shareable.relative_to(ROOT)}")
        print("Read-only: no GenFarmer state was changed.")
        print("=" * 78)
        return 0 if semantic_equal else 3

    except (GenFarmFileError, GenFarmerError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
