#!/usr/bin/env python3
"""Read-only per-action settings probe for GenFarmer's Electron renderer assets.

The Automation editor bundle already exposed internal identifiers such as
``actionTypeText`` and ``actionElementExists``.  This probe uses those identifiers
as anchors and searches renderer JS assets for implementation/settings metadata.
It emits only structural, shareable evidence: asset filenames, option/property
keys, generic settings-control names, runtime keys and nearby human-readable node
labels.  It never emits raw proprietary source snippets.

No GenFarmer files are modified and no workflow/API mutation is performed.
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

EDITOR_BUNDLE = "dist/render/assets/useScriptEditor-HioTuYH4.js"
ACTION_RE = re.compile(r"\baction[A-Z][A-Za-z0-9_]{1,80}\b")
STRING_RE = re.compile(r'(["\'])(?P<v>(?:\\.|(?!\1).){1,160})\1')
OBJECT_KEY_RE = re.compile(r'(?:^|[,{])\s*(?:["\'])?([A-Za-z_$][A-Za-z0-9_$]{1,80})(?:["\'])?\s*:')
DOT_KEY_RE = re.compile(r'\.([A-Za-z_$][A-Za-z0-9_$]{1,80})\b')

SETTINGS_CONTROLS = (
    "Input", "Input Number", "Select", "Switch", "CheckBox", "CheckBox Group",
    "Radio", "Slider", "TextArea", "File", "Grid", "Basic Field", "Advance Field",
    "HTML", "Link", "Inline", "Group", "Divider", "Alert",
)
RUNTIME_KEYS = (
    "successNode", "failNode", "nodeLog", "nodeSleep", "nodeTimeout",
    "timeoutAdbReconnect", "timeoutNextNode", "timeoutType", "timeoutFrom",
    "timeoutTo", "outputVariable", "casePaths", "breakpoint", "disabled",
    "sourceHandle", "targetHandle",
)

# Keys that are common implementation noise and should not dominate the output.
NOISY_KEYS = {
    "data", "value", "values", "key", "keys", "name", "label", "title", "type",
    "class", "className", "style", "children", "id", "x", "y", "width", "height",
    "length", "push", "map", "filter", "find", "forEach", "includes", "indexOf",
    "toString", "trim", "replace", "split", "join", "slice", "substring", "text",
    "description", "icon", "color", "component", "props", "options", "action",
}

LIKELY_OPTION_WORDS = {
    "timeout", "package", "packageName", "activity", "xpath", "xpathLite", "resourceId",
    "resourceid", "className", "contentDesc", "description", "text", "x", "y", "x1", "y1",
    "x2", "y2", "duration", "direction", "speed", "keyCode", "keycode", "command",
    "outputVariable", "variable", "variableName", "method", "url", "headers", "params",
    "query", "body", "cookies", "file", "filePath", "path", "source", "target", "append",
    "overwrite", "regex", "pattern", "attribute", "property", "service", "enabled", "mode",
    "prompt", "model", "apiKey", "folder", "host", "port", "username", "password",
    "delimiter", "sheet", "range", "cell", "rows", "columns", "selector", "actionType",
}

# Strong labels already surfaced from the editor bundle.  These are safe UI labels.
KNOWN_LABELS = (
    "Press Back", "Press Home", "Press Menu", "Change device", "Start App", "Stop App",
    "Install App", "Uninstall App", "Is installed App", "Clear App Data", "Transfer File",
    "Device actions", "Toggle service", "Check activity", "Press key", "Type text",
    "Update field", "Get property", "Element exists", "Multi Element exists", "Get attribute",
    "Write file", "Save assets", "Set variable", "Insert data", "Open AI", "Case Path",
    "ADB shell command", "Sleep", "Screenshot", "DeepSeek", "Context Menu", "Variables",
    "Touch", "Random", "HTTP", "Comment", "Loop", "While", "Stop", "Clipboard",
    "Spreadsheet", "Gemini", "Grok", "Javascript", "Reconnect", "Log", "Xpath", "GenRouter",
)


def default_asar() -> Path:
    local = os.getenv("LOCALAPPDATA")
    return Path(local or ".") / "Programs" / "GenFarmer" / "resources" / "app.asar"


def decode(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    return bytes(raw).decode("utf-8", errors="ignore")


def safe_string(value: str) -> str | None:
    value = value.strip()
    if not value or len(value) > 100:
        return None
    if any(x in value for x in ("\n", "\r", "@", "http://", "https://", "data:", "{", "}")):
        return None
    if not re.fullmatch(r"[A-Za-z0-9 _./:+()#%&,'!?\-]+", value):
        return None
    if value.count("-") >= 5 or value.count("/") >= 3:
        return None
    return value


def windows(text: str, needle: str, radius: int, max_hits: int = 40) -> list[str]:
    out: list[str] = []
    for m in re.finditer(rf"\b{re.escape(needle)}\b", text):
        out.append(text[max(0, m.start()-radius):min(len(text), m.end()+radius)])
        if len(out) >= max_hits:
            break
    return out


def basename_stem(path: str) -> str:
    name = Path(path).name
    if name.endswith(".js"):
        name = name[:-3]
    # Vite hashes normally follow the final dash.
    if "-" in name:
        left, right = name.rsplit("-", 1)
        if 5 <= len(right) <= 16 and re.fullmatch(r"[A-Za-z0-9_]+", right):
            return left
    return name


def key_score(key: str) -> int:
    if key in NOISY_KEYS:
        return -10
    score = 0
    if key in LIKELY_OPTION_WORDS:
        score += 8
    low = key.lower()
    if any(tok in low for tok in (
        "timeout", "xpath", "resource", "package", "activity", "variable", "output", "file",
        "path", "method", "header", "cookie", "param", "regex", "attribute", "property",
        "service", "duration", "direction", "prompt", "model", "sheet", "range", "selector",
        "command", "keycode", "actiontype", "clipboard", "device", "network", "url",
    )):
        score += 4
    if 3 <= len(key) <= 40:
        score += 1
    return score


def main() -> int:
    p = argparse.ArgumentParser(description="Probe GenFarmer per-action settings/options from renderer assets")
    p.add_argument("--asar", type=Path, default=default_asar())
    p.add_argument("--editor-bundle", default=EDITOR_BUNDLE)
    p.add_argument("--radius", type=int, default=5000)
    p.add_argument("--max-asset-mb", type=int, default=24)
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
    asset_texts: dict[str, str] = {}

    with ctx as archive:
        try:
            entries = [str(x).replace("\\", "/") for x in archive.list()]
            try:
                editor_raw = archive.read(Path(args.editor_bundle), follow_link=True)
            except TypeError:
                editor_raw = archive.read(Path(args.editor_bundle))
            editor_text = decode(editor_raw)
        except Exception as exc:
            print(f"ERROR reading editor bundle: {exc}", file=sys.stderr)
            return 1

        action_ids = sorted(set(ACTION_RE.findall(editor_text)))
        if not action_ids:
            print("ERROR: no action* identifiers discovered in editor bundle", file=sys.stderr)
            return 1

        js_entries = [e for e in entries if e.startswith("dist/render/assets/") and e.endswith(".js")]
        for entry in js_entries:
            try:
                try:
                    raw = archive.read(Path(entry), follow_link=True)
                except TypeError:
                    raw = archive.read(Path(entry))
            except Exception:
                continue
            if isinstance(raw, (bytes, bytearray)) and len(raw) > max_bytes:
                continue
            text = decode(raw)
            if any(action in text for action in action_ids):
                asset_texts[entry] = text

    records = []
    all_key_frequency: Counter[str] = Counter()
    for action in action_ids:
        file_hits = []
        aggregate_keys: Counter[str] = Counter()
        aggregate_controls: Counter[str] = Counter()
        aggregate_labels: Counter[str] = Counter()
        aggregate_runtime: Counter[str] = Counter()
        safe_literals: Counter[str] = Counter()

        for path, text in asset_texts.items():
            if action not in text:
                continue
            action_windows = windows(text, action, max(1200, args.radius))
            if not action_windows:
                continue

            local_keys: Counter[str] = Counter()
            local_controls: Counter[str] = Counter()
            local_labels: Counter[str] = Counter()
            local_runtime: Counter[str] = Counter()
            local_literals: Counter[str] = Counter()

            for chunk in action_windows:
                for key in OBJECT_KEY_RE.findall(chunk):
                    if key_score(key) > 0:
                        local_keys[key] += 1
                for key in DOT_KEY_RE.findall(chunk):
                    if key_score(key) > 0:
                        local_keys[key] += 1
                for control in SETTINGS_CONTROLS:
                    count = len(re.findall(rf"\b{re.escape(control)}\b", chunk, flags=re.IGNORECASE))
                    if count:
                        local_controls[control] += count
                for runtime in RUNTIME_KEYS:
                    count = len(re.findall(rf"\b{re.escape(runtime)}\b", chunk))
                    if count:
                        local_runtime[runtime] += count
                low = chunk.lower()
                for label in KNOWN_LABELS:
                    count = low.count(label.lower())
                    if count:
                        local_labels[label] += count
                for m in STRING_RE.finditer(chunk):
                    value = safe_string(m.group("v"))
                    if value and value not in KNOWN_LABELS and 2 <= len(value) <= 60:
                        # Keep only strings that look like setting labels/enums.
                        if " " in value or value[:1].isupper() or value.lower() in {
                            "fixed", "random", "append", "overwrite", "get", "post", "put", "delete",
                            "true", "false", "success", "failure", "text", "xpath", "coordinate",
                        }:
                            local_literals[value] += 1

            aggregate_keys.update(local_keys)
            aggregate_controls.update(local_controls)
            aggregate_labels.update(local_labels)
            aggregate_runtime.update(local_runtime)
            safe_literals.update(local_literals)
            all_key_frequency.update(local_keys)

            file_hits.append({
                "path": path,
                "basename_stem": basename_stem(path),
                "occurrences": len(action_windows),
                "top_option_keys": [
                    {"key": key, "count": count, "score": key_score(key)}
                    for key, count in sorted(local_keys.items(), key=lambda kv: (-key_score(kv[0]), -kv[1], kv[0]))[:40]
                ],
                "settings_controls": [{"control": k, "count": v} for k, v in local_controls.most_common(20)],
                "nearby_labels": [{"label": k, "count": v} for k, v in local_labels.most_common(20)],
                "runtime_keys": [{"key": k, "count": v} for k, v in local_runtime.most_common()],
            })

        records.append({
            "action_identifier": action,
            "semantic_hint": action[len("action"):],
            "asset_files": file_hits,
            "asset_file_count": len(file_hits),
            "top_option_keys": [
                {"key": key, "count": count, "score": key_score(key)}
                for key, count in sorted(aggregate_keys.items(), key=lambda kv: (-key_score(kv[0]), -kv[1], kv[0]))[:80]
            ],
            "settings_controls": [{"control": k, "count": v} for k, v in aggregate_controls.most_common(30)],
            "nearby_labels": [{"label": k, "count": v} for k, v in aggregate_labels.most_common(30)],
            "runtime_keys": [{"key": k, "count": v} for k, v in aggregate_runtime.most_common()],
            "safe_setting_literals": [{"value": k, "count": v} for k, v in safe_literals.most_common(60)],
        })

    result = {
        "catalog_format": 1,
        "privacy": "shareable per-action structural settings catalog; no raw GenFarmer source snippets or client data",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "genfarmer_package": "resources/app.asar",
        "editor_bundle": args.editor_bundle,
        "action_identifier_count": len(action_ids),
        "renderer_asset_files_with_action_hits": len(asset_texts),
        "actions": records,
        "global_option_key_frequency": [
            {"key": k, "count": v, "score": key_score(k)}
            for k, v in sorted(all_key_frequency.items(), key=lambda kv: (-key_score(kv[0]), -kv[1], kv[0]))[:150]
        ],
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-action-settings-probe-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "action-settings.shareable.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER PER-ACTION SETTINGS / OPTIONS PROBE")
    print("=" * 78)
    print(f"Action identifiers: {len(action_ids)}")
    print(f"Renderer assets with action hits: {len(asset_texts)}")
    print("Per-action summary:")
    for rec in records:
        labels = ", ".join(x["label"] for x in rec["nearby_labels"][:3]) or "-"
        keys = ", ".join(x["key"] for x in rec["top_option_keys"][:8]) or "-"
        controls = ", ".join(x["control"] for x in rec["settings_controls"][:5]) or "-"
        print(f" - {rec['action_identifier']}: files={rec['asset_file_count']} labels=[{labels}] keys=[{keys}] controls=[{controls}]")
    print(f"Shareable result: {out.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
