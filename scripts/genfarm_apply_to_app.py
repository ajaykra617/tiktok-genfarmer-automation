#!/usr/bin/env python3
"""Apply a compiled .genfarm script to one existing GenFarmer app.

Dry-run by default. Target selection prefers explicit --app-id, then the
compiled export's preserved id, then a unique exact name. Before mutation the
live flow is backed up under ignored evidence. After PUT the app is re-read.

Verification has two levels:
1. exact lossless flow hash;
2. runtime-semantic equality of node ids/types/actions/options/routing and edge
   endpoints/handles.

GenFarmer may normalize editor-only/cache fields on save, so exact hash mismatch
is not considered failure when the runtime-semantic projection is identical.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
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
    app_id: str | None,
    app_name: str,
    *,
    preferred_id: str | None = None,
) -> tuple[str, Any, str]:
    if app_id:
        return app_id, client.get_app(app_id), "explicit --app-id"

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
    if preferred_id and preferred_id in matches:
        return preferred_id, client.get_app(preferred_id), "compiled export identity"
    if len(matches) != 1:
        raise GenFarmerError(
            f"found {len(matches)} apps named {app_name!r}, and the compiled export identity did not uniquely match one; pass --app-id"
        )
    selected = next(iter(matches))
    return selected, client.get_app(selected), "unique exact name"


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


def compiled_identity(doc: GenFarmDocument) -> str | None:
    value = doc.to_dict().get("id")
    if isinstance(value, (str, int)) and str(value):
        return str(value)
    return None


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def semantic_node(node: Mapping[str, Any]) -> dict[str, Any]:
    data = node.get("data")
    data_map = data if isinstance(data, Mapping) else {}
    return {
        "id": str(node.get("id")),
        "type": node.get("type"),
        "action": data_map.get("action"),
        "options": data_map.get("options"),
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
    nodes = [semantic_node(n) for n in doc.nodes if isinstance(n, Mapping)]
    nodes.sort(key=lambda item: item["id"])
    edges = [semantic_edge(e) for e in doc.edges if isinstance(e, Mapping)]
    edges.sort(key=lambda item: (item["source"], item["target"], str(item["sourceHandle"]), str(item["targetHandle"])))
    return {"nodes": nodes, "edges": edges}


def diff_paths(a: Any, b: Any, path: str = "$", limit: int = 40) -> list[str]:
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
        preferred_id = compiled_identity(compiled)
        app_id, detail, selection_basis = select_app(
            read_client, current_user, args.app_id, args.app_name, preferred_id=preferred_id
        )
        live_app = app_object(detail, app_id)
        live_flow_raw = find_flow(live_app)
        if live_flow_raw is None:
            raise GenFarmerError("target app has no script.flow")
        live_flow = FlowDocument.from_flow(live_flow_raw)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = ROOT / "evidence" / f"genfarm-apply-{stamp}"
        private_dir = out_dir / "private"
        private_dir.mkdir(parents=True, exist_ok=True)
        (private_dir / "before.flow.json").write_text(
            json.dumps(live_flow.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (private_dir / "compiled.flow.json").write_text(
            json.dumps(compiled_flow.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report: dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "apply" if args.apply else "dry-run",
            "app_name": args.app_name,
            "selection_basis": selection_basis,
            "before_nodes": len(live_flow.nodes),
            "before_edges": len(live_flow.edges),
            "compiled_nodes": len(compiled_flow.nodes),
            "compiled_edges": len(compiled_flow.edges),
            "flow_changed": live_flow.sha256() != compiled_flow.sha256(),
            "exact_verified": False,
            "semantic_verified": False,
            "semantic_diff_paths": [],
        }

        verification_note = ""
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
            (private_dir / "verified.flow.json").write_text(
                json.dumps(verified.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )

            exact = verified.sha256() == compiled_flow.sha256()
            compiled_sem = semantic_flow(compiled_flow)
            verified_sem = semantic_flow(verified)
            semantic = canonical_hash(compiled_sem) == canonical_hash(verified_sem)
            report["exact_verified"] = exact
            report["semantic_verified"] = semantic
            if not semantic:
                report["semantic_diff_paths"] = diff_paths(compiled_sem, verified_sem)
                shareable = out_dir / "genfarm-apply.shareable.json"
                shareable.write_text(json.dumps(report, indent=2), encoding="utf-8")
                raise GenFarmerError(
                    "post-PUT runtime-semantic flow does not match compiled flow; "
                    f"verified live flow saved at {private_dir.relative_to(ROOT) / 'verified.flow.json'}; "
                    "run scripts/genfarm_verify_live.py for a read-only diff"
                )
            if exact:
                verification_note = "exact lossless match"
            else:
                verification_note = "runtime-semantic match; GenFarmer normalized editor/non-runtime fields"

        shareable = out_dir / "genfarm-apply.shareable.json"
        shareable.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("=" * 78)
        print("GENFARM COMPILED FLOW APPLY")
        print("=" * 78)
        print(f"Target app: {args.app_name}")
        print(f"Selection:  {selection_basis}")
        print(f"Compiled:   {args.compiled}")
        print(f"Current:    nodes={report['before_nodes']} edges={report['before_edges']}")
        print(f"Compiled:   nodes={report['compiled_nodes']} edges={report['compiled_edges']}")
        print(f"Flow changed: {'YES' if report['flow_changed'] else 'NO'}")
        print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
        if args.apply:
            print(f"Exact lossless verification: {'PASS' if report['exact_verified'] else 'NORMALIZED'}")
            print(f"Runtime-semantic verification: {'PASS' if report['semantic_verified'] else 'FAIL'}")
            print(f"Verification note: {verification_note}")
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
