#!/usr/bin/env python3
"""Targeted before/after learner for one GenFarmer node setting.

Usage:

    python scripts/genfarmer_setting_probe.py before --action Touch
    # change exactly ONE setting on the Touch node in GF Lab - Node Catalog and save
    python scripts/genfarmer_setting_probe.py after --action Touch

The script reads the dedicated lab app with GET requests only, selects exactly
one node by ``data.action``, stores exact before/after nodes under ignored private
evidence, and emits a shareable privacy-safe field diff.

This is intentionally action-scoped: the full lab contains one node per action,
so a one-setting UI change can be mapped directly to its serialized field path
without noise from the other 61 nodes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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

SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/+-]{1,80}$")
SAFE_ACTION_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")

# Fields whose string values can contain app/client/user content and therefore
# must always be masked in the shareable report.
SENSITIVE_LEAF_HINTS = {
    "text", "value", "xpath", "selector", "resourceid", "resource_id", "id",
    "packagename", "package", "activity", "command", "url", "uri", "body",
    "header", "headers", "password", "token", "secret", "cookie", "file",
    "filename", "folder", "path", "host", "email", "variable", "variables",
    "outputvariable", "script", "javascript", "code", "prompt", "message",
    "query", "data", "name", "label", "description", "content",
}

# These leaf names are strongly enum/implementation-like. Short token values
# are useful for reverse engineering and are safe to reveal.
SAFE_ENUM_LEAVES = {
    "action", "type", "mode", "method", "direction", "operator", "condition",
    "strategy", "timeouttype", "behavior", "operation", "sourceposition",
    "targetposition", "sourcehandle", "targethandle", "keytype", "selectortype",
    "touchtype", "swipetype", "inputtype", "valuetype", "comparetype",
}


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
        raise GenFarmerError(f"lab app not found by exact name {app_name!r}")
    if len(matches) != 1:
        raise GenFarmerError(f"found {len(matches)} apps named {app_name!r}; pass --app-id")
    return client.get_app(next(iter(matches)))


def node_action(node: Mapping[str, Any]) -> str | None:
    data = node.get("data")
    if not isinstance(data, Mapping):
        return None
    action = data.get("action")
    if isinstance(action, str) and SAFE_ACTION_RE.fullmatch(action):
        return action
    return None


def select_node(doc: FlowDocument, action: str) -> dict[str, Any]:
    matches = [dict(node) for node in doc.nodes if isinstance(node, Mapping) and node_action(node) == action]
    if not matches:
        raise GenFarmerError(f"no node with data.action={action!r} exists in the lab flow")
    if len(matches) != 1:
        raise GenFarmerError(
            f"found {len(matches)} nodes with data.action={action!r}; targeted differential requires exactly one"
        )
    return matches[0]


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, Mapping):
        if prefix:
            out[prefix] = {"__container__": "object", "keys": sorted(map(str, value.keys()))}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten(child, path))
    elif isinstance(value, list):
        if prefix:
            out[prefix] = {"__container__": "list", "length": len(value)}
        for idx, child in enumerate(value):
            path = f"{prefix}[{idx}]"
            out.update(flatten(child, path))
    else:
        out[prefix] = value
    return out


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def leaf_name(path: str) -> str:
    token = path.rsplit(".", 1)[-1]
    token = re.sub(r"\[\d+\]$", "", token)
    return token.lower()


def is_sensitive_leaf(leaf: str) -> bool:
    if leaf in SENSITIVE_LEAF_HINTS:
        return True
    return any(hint in leaf for hint in SENSITIVE_LEAF_HINTS if len(hint) >= 5)


def display_value(path: str, value: Any) -> Any:
    if isinstance(value, Mapping) and "__container__" in value:
        return value
    leaf = leaf_name(path)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        # Numeric UI settings such as timeouts/coordinates are not secrets and
        # seeing the exact changed number is useful for serialization learning.
        return value
    if isinstance(value, str):
        if not is_sensitive_leaf(leaf) and leaf in SAFE_ENUM_LEAVES and SAFE_TOKEN_RE.fullmatch(value):
            return value
        return {"type": "str", "length": len(value), "sha256_10": digest_text(value)}
    return {"type": type(value).__name__}


def compare(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    a = flatten(before)
    b = flatten(after)
    changes: list[dict[str, Any]] = []
    marker = object()
    for path in sorted(set(a) | set(b)):
        av = a.get(path, marker)
        bv = b.get(path, marker)
        if av == bv:
            continue
        changes.append(
            {
                "path": path,
                "before": "<missing>" if av is marker else display_value(path, av),
                "after": "<missing>" if bv is marker else display_value(path, bv),
            }
        )
    return changes


def safe_action_path(action: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", action)[:80]


def current_node(args: argparse.Namespace) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        raise GenFarmerError("configure GENFARMER_BASE_URL in .env")
    client = GenFarmerClient(base_url, timeout=12.0, allow_mutations=False)
    user_id = discover_user_id(client.get_current_user())
    detail = select_app(client, user_id, args.app_id, args.app_name)
    flow = find_flow(detail)
    if flow is None:
        raise GenFarmerError("selected lab app has no script.flow")
    doc = FlowDocument.from_flow(flow)
    return select_node(doc, args.action)


def main() -> int:
    ap = argparse.ArgumentParser(description="Targeted GET-only before/after GenFarmer node-setting learner")
    ap.add_argument("phase", choices=("before", "after"))
    ap.add_argument("--action", required=True, help="Exact data.action, e.g. Touch, TypeText, StartApp")
    ap.add_argument("--app-id")
    ap.add_argument("--app-name", default="GF Lab - Node Catalog")
    args = ap.parse_args()

    if not SAFE_ACTION_RE.fullmatch(args.action):
        print("ERROR: --action must be a short internal action token", file=sys.stderr)
        return 2

    try:
        node = current_node(args)
    except (GenFarmerError, Exception) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    study_dir = ROOT / "evidence" / "genfarmer-setting-study" / safe_action_path(args.action)
    private_dir = study_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)
    before_path = private_dir / "before.raw.json"
    after_path = private_dir / "after.raw.json"

    if args.phase == "before":
        before_path.write_text(json.dumps(node, ensure_ascii=False, indent=2), encoding="utf-8")
        if after_path.exists():
            after_path.unlink()
        print("=" * 78)
        print("GENFARMER TARGETED SETTING PROBE - BASELINE")
        print("=" * 78)
        print(f"Action: {args.action}")
        print(f"Private baseline: {before_path.relative_to(ROOT)}")
        print("Now change exactly ONE setting on this node in GenFarmer, save the app, then run:")
        print(f"  python scripts/genfarmer_setting_probe.py after --action {args.action}")
        print("GET only; no GenFarmer state was modified.")
        print("=" * 78)
        return 0

    if not before_path.exists():
        print(
            f"ERROR: baseline missing for {args.action}; first run: "
            f"python scripts/genfarmer_setting_probe.py before --action {args.action}",
            file=sys.stderr,
        )
        return 2

    try:
        before = json.loads(before_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read baseline: {exc}", file=sys.stderr)
        return 1
    if not isinstance(before, Mapping):
        print("ERROR: baseline node is malformed", file=sys.stderr)
        return 1

    after_path.write_text(json.dumps(node, ensure_ascii=False, indent=2), encoding="utf-8")
    changes = compare(before, node)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "catalog_format": 1,
        "privacy": "shareable targeted node diff; sensitive string values are hashed/masked",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "action": args.action,
        "changed_path_count": len(changes),
        "changes": changes,
    }
    shareable = study_dir / f"diff-{stamp}.shareable.json"
    shareable.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER TARGETED SETTING PROBE - DIFF")
    print("=" * 78)
    print(f"Action: {args.action}")
    print(f"Changed paths: {len(changes)}")
    if not changes:
        print(" - no serialized change detected")
    else:
        for item in changes:
            print(f" - {item['path']}: {item['before']} -> {item['after']}")
    print(f"Private before: {before_path.relative_to(ROOT)}")
    print(f"Private after:  {after_path.relative_to(ROOT)}")
    print(f"Shareable diff: {shareable.relative_to(ROOT)}")
    print("For another one-setting experiment, run the BEFORE phase again to reset the baseline.")
    print("GET only; no GenFarmer state was modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
