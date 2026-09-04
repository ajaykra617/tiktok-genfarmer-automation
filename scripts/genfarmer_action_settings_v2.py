#!/usr/bin/env python3
"""Read-only scoped/differential settings probe for GenFarmer Automation actions.

The first per-action settings probe intentionally favored recall and therefore
picked up shared editor/form-builder infrastructure around many actions.  This
second pass ranks the *smallest, least-shared renderer assets* that mention each
``action*`` identifier, inspects tight local windows around exact occurrences,
and subtracts keys/controls that appear across many actions.

The report is privacy-safe: it emits identifiers, property names, control names,
asset paths and human-readable UI-like labels only.  It never emits raw bundled
source snippets, secrets, selectors, commands, workflow values, or client data.

No GenFarmer file is modified and no workflow/API mutation is performed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

try:
    from asar import AsarArchive
except ImportError:
    print('ERROR: missing package "asar"; run: python -m pip install -e ".[dev]"', file=sys.stderr)
    raise SystemExit(2)

ACTION_RE = re.compile(r"\baction[A-Z][A-Za-z0-9_]{1,80}\b")
KEY_RE = re.compile(r'(?:^|[,{])\s*(?:["\'])?([A-Za-z_$][A-Za-z0-9_$]{1,64})(?:["\'])?\s*:')
STRING_RE = re.compile(r'(["\'])(?P<v>(?:\\.|(?!\1).){1,100})\1')

CONTROLS = (
    "Input", "Input Number", "Select", "Switch", "CheckBox", "CheckBox Group",
    "Radio", "Slider", "TextArea", "File", "Grid", "Group", "Inline", "Divider",
    "Alert", "Link", "HTML", "Text", "Title",
)

RUNTIME_KEYS = {
    "successNode", "failNode", "nodeLog", "nodeSleep", "nodeTimeout",
    "timeoutAdbReconnect", "timeoutNextNode", "timeoutType", "timeoutFrom",
    "timeoutTo", "outputVariable", "casePaths", "breakpoint", "disabled",
    "sourceHandle", "targetHandle",
}

# Broad implementation/framework names that are not useful as node settings.
NOISE_KEYS = {
    "data", "value", "values", "key", "name", "label", "title", "type", "id",
    "children", "props", "style", "class", "className", "component", "components",
    "render", "setup", "modelValue", "defaultValue", "options", "items", "item",
    "length", "index", "target", "source", "event", "events", "ref", "refs",
    "state", "store", "dispatch", "payload", "result", "results", "status",
    "message", "error", "success", "loading", "visible", "disabled", "readonly",
    "required", "placeholder", "size", "width", "height", "x", "y", "top",
    "left", "right", "bottom", "color", "icon", "text", "description", "path",
    "file", "folder", "password", "variables", "hasOwnProperty",
}

GENERIC_LABELS = {
    "HTTP", "Loop", "Variables", "Stop", "custom", "helper", "File", "Input",
    "Select", "Switch", "CheckBox", "Group", "Grid", "Inline", "Radio", "Slider",
    "Text", "Title", "Alert", "Divider",
}


def default_asar() -> Path:
    local = os.getenv("LOCALAPPDATA")
    return Path(local or ".") / "Programs" / "GenFarmer" / "resources" / "app.asar"


def decode(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    return bytes(raw).decode("utf-8", errors="ignore")


def safe_label(value: str) -> str | None:
    value = value.strip()
    if not (2 <= len(value) <= 70):
        return None
    if value in GENERIC_LABELS:
        return None
    if any(x in value for x in ("\n", "\r", "@", "http://", "https://", "data:", "{", "}")):
        return None
    if not re.fullmatch(r"[A-Za-z0-9 _./:+()#%&,'!?\-]+", value):
        return None
    # Prefer strings that look like UI labels/tokens rather than minified code.
    words = value.split()
    if len(words) > 8:
        return None
    if not (" " in value or value[:1].isupper()):
        return None
    return value


def read_asset(archive: Any, path: str) -> str | None:
    try:
        try:
            raw = archive.read(Path(path), follow_link=True)
        except TypeError:
            raw = archive.read(Path(path))
    except Exception:
        return None
    return decode(raw)


def main() -> int:
    p = argparse.ArgumentParser(description="Scoped differential settings probe for GenFarmer action identifiers")
    p.add_argument("--asar", type=Path, default=default_asar())
    p.add_argument("--editor-bundle", default="dist/render/assets/useScriptEditor-HioTuYH4.js")
    p.add_argument("--radius", type=int, default=700, help="Characters on each side of an exact action occurrence")
    p.add_argument("--max-asset-mb", type=int, default=24)
    p.add_argument("--common-fraction", type=float, default=0.28, help="Keys seen in this fraction of actions are treated as shared infrastructure")
    args = p.parse_args()

    asar_path = args.asar.expanduser().resolve()
    if not asar_path.exists():
        print(f"ERROR: app.asar not found: {asar_path}", file=sys.stderr)
        return 2

    try:
        ctx = AsarArchive(asar_path, mode="r")
    except TypeError:
        ctx = AsarArchive.open(str(asar_path))

    max_bytes = max(1, args.max_asset_mb) * 1024 * 1024

    with ctx as archive:
        entries = [str(x).replace("\\", "/") for x in archive.list()]
        js_assets = [
            e for e in entries
            if e.startswith("dist/render/assets/") and e.endswith(".js")
        ]
        editor_text = read_asset(archive, args.editor_bundle)
        if editor_text is None:
            print(f"ERROR: cannot read editor bundle: {args.editor_bundle}", file=sys.stderr)
            return 1
        actions = sorted(set(ACTION_RE.findall(editor_text)))
        if not actions:
            print("ERROR: no action* identifiers discovered in editor bundle", file=sys.stderr)
            return 1

        # First pass: cache only renderer assets that contain at least one action.
        asset_records: dict[str, dict[str, Any]] = {}
        for path in js_assets:
            text = read_asset(archive, path)
            if text is None:
                continue
            size = len(text.encode("utf-8", errors="ignore"))
            if size > max_bytes:
                continue
            present = sorted(set(ACTION_RE.findall(text)) & set(actions))
            if not present:
                continue
            asset_records[path] = {
                "text": text,
                "characters": len(text),
                "actions": present,
                "action_count": len(present),
            }

    raw_by_action: dict[str, dict[str, Any]] = {}
    key_action_support: defaultdict[str, set[str]] = defaultdict(set)
    control_action_support: defaultdict[str, set[str]] = defaultdict(set)

    for action in actions:
        file_hits: list[dict[str, Any]] = []
        all_keys: Counter[str] = Counter()
        all_controls: Counter[str] = Counter()
        all_labels: Counter[str] = Counter()
        runtime: Counter[str] = Counter()

        for path, rec in asset_records.items():
            text = rec["text"]
            positions = [m.start() for m in re.finditer(rf"\b{re.escape(action)}\b", text)]
            if not positions:
                continue

            file_keys: Counter[str] = Counter()
            file_controls: Counter[str] = Counter()
            file_labels: Counter[str] = Counter()
            file_runtime: Counter[str] = Counter()

            for pos in positions[:40]:
                lo = max(0, pos - max(100, args.radius))
                hi = min(len(text), pos + len(action) + max(100, args.radius))
                chunk = text[lo:hi]

                for key in KEY_RE.findall(chunk):
                    if key != action:
                        file_keys[key] += 1
                for control in CONTROLS:
                    count = len(re.findall(rf"\b{re.escape(control)}\b", chunk))
                    if count:
                        file_controls[control] += count
                for rkey in RUNTIME_KEYS:
                    count = len(re.findall(rf"\b{re.escape(rkey)}\b", chunk))
                    if count:
                        file_runtime[rkey] += count
                for sm in STRING_RE.finditer(chunk):
                    label = safe_label(sm.group("v"))
                    if label:
                        file_labels[label] += 1

            # Prefer an action-specific small asset over a giant shared editor bundle.
            basename = Path(path).name
            suffix = action.removeprefix("action").lower()
            filename_bonus = 0 if suffix and suffix in basename.lower() else 1
            scope_rank = (
                rec["action_count"],
                filename_bonus,
                rec["characters"],
                -len(positions),
            )
            file_hits.append({
                "path": path,
                "characters": rec["characters"],
                "action_identifiers_in_file": rec["action_count"],
                "occurrences": len(positions),
                "scope_rank": list(scope_rank),
                "candidate_keys": [{"key": k, "count": c} for k, c in file_keys.most_common(60)],
                "controls": [{"control": k, "count": c} for k, c in file_controls.most_common()],
                "runtime_keys": [{"key": k, "count": c} for k, c in file_runtime.most_common()],
                "labels": [{"label": k, "count": c} for k, c in file_labels.most_common(40)],
            })

            all_keys.update(file_keys)
            all_controls.update(file_controls)
            all_labels.update(file_labels)
            runtime.update(file_runtime)

        file_hits.sort(key=lambda x: tuple(x["scope_rank"]))
        raw_by_action[action] = {
            "files": file_hits,
            "keys": all_keys,
            "controls": all_controls,
            "labels": all_labels,
            "runtime": runtime,
        }
        for key in all_keys:
            key_action_support[key].add(action)
        for control in all_controls:
            control_action_support[control].add(action)

    common_threshold = max(3, int(len(actions) * max(0.05, min(0.95, args.common_fraction))))
    common_keys = {
        key for key, acts in key_action_support.items()
        if len(acts) >= common_threshold
    } | NOISE_KEYS
    common_controls = {
        c for c, acts in control_action_support.items()
        if len(acts) >= common_threshold
    }

    serial_actions: list[dict[str, Any]] = []
    for action in actions:
        rec = raw_by_action[action]
        unique_keys = [
            {"key": k, "count": c, "action_support": len(key_action_support[k])}
            for k, c in rec["keys"].most_common()
            if k not in common_keys and not k.startswith("_") and not k.startswith("$")
        ][:30]
        distinctive_controls = [
            {"control": k, "count": c, "action_support": len(control_action_support[k])}
            for k, c in rec["controls"].most_common()
            if k not in common_controls
        ][:15]
        labels = [
            {"label": k, "count": c}
            for k, c in rec["labels"].most_common()
            if k not in GENERIC_LABELS and not k.startswith("action")
        ][:20]
        serial_actions.append({
            "action_identifier": action,
            "best_scoped_files": rec["files"][:5],
            "distinctive_candidate_keys": unique_keys,
            "distinctive_controls": distinctive_controls,
            "runtime_keys": [{"key": k, "count": c} for k, c in rec["runtime"].most_common()],
            "nearby_labels": labels,
        })

    result = {
        "catalog_format": 2,
        "privacy": "shareable scoped/differential renderer analysis; no raw GenFarmer source snippets or workflow values",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "genfarmer_package": "resources/app.asar",
        "editor_bundle": args.editor_bundle,
        "action_identifier_count": len(actions),
        "renderer_assets_with_action_hits": len(asset_records),
        "tight_window_radius": args.radius,
        "common_action_support_threshold": common_threshold,
        "shared_keys_filtered": sorted(k for k in common_keys if k not in NOISE_KEYS),
        "shared_controls_filtered": sorted(common_controls),
        "actions": serial_actions,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-action-settings-v2-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "action-settings-v2.shareable.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER SCOPED / DIFFERENTIAL ACTION SETTINGS PROBE V2")
    print("=" * 78)
    print(f"Action identifiers: {len(actions)}")
    print(f"Renderer assets with action hits: {len(asset_records)}")
    print(f"Shared-key threshold: {common_threshold}/{len(actions)} actions")
    print("Per-action distinctive summary:")
    for item in serial_actions:
        best = item["best_scoped_files"][0] if item["best_scoped_files"] else None
        best_name = Path(best["path"]).name if best else "-"
        density = best["action_identifiers_in_file"] if best else 0
        keys = ", ".join(x["key"] for x in item["distinctive_candidate_keys"][:8]) or "-"
        controls = ", ".join(x["control"] for x in item["distinctive_controls"][:5]) or "-"
        runtime_keys = ", ".join(x["key"] for x in item["runtime_keys"][:5]) or "-"
        print(f" - {item['action_identifier']}: best={best_name} actions-in-file={density} keys=[{keys}] controls=[{controls}] runtime=[{runtime_keys}]")
    print(f"Shareable result: {out.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
