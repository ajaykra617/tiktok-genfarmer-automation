#!/usr/bin/env python3
"""Read-only action/label correlation probe for GenFarmer 2.6.1.

The minified Automation editor bundle contains both human-facing palette labels
and implementation identifiers such as ``actionElementExists``.  This probe
correlates those signals without dumping raw proprietary source.  It reports:

* ``action*`` implementation identifiers;
* likely human-facing labels near each identifier;
* likely semantic action names derived from identifier suffixes;
* nearby object/property keys and known runtime fields;
* a conservative list of likely Automation palette labels discovered from the
  same bundle.

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

KNOWN_LABELS = {
    "Press Back", "Press Home", "Press Menu", "Change device", "Start App",
    "Stop App", "Install App", "Uninstall App", "Variables", "Context Menu",
    "ADB shell command", "Sleep", "Screenshot", "DeepSeek",
}

# Strong candidates already discovered from the same Automation editor cluster.
DISCOVERED_LABELS = {
    "Is installed App", "Clear App Data", "Transfer File", "Device actions",
    "Toggle service", "Check activity", "Press key", "Type text", "Update field",
    "Get property", "Element exists", "Multi Element exists", "Get attribute",
    "Write file", "Save assets", "Set variable", "Insert data", "Open AI",
    "Case Path",
}

# These were also observed in the editor cluster but may be implementation
# tokens, action names, category names, or real palette labels. Keep them
# separate from the stronger human-label set until correlated.
AMBIGUOUS_TOKENS = {
    "Cmd", "Touch", "Random", "HTTP", "Comment", "Loop", "While", "Stop",
    "Clipboard", "Spreadsheet", "Gemini", "Grok", "Javascript", "Reconnect",
    "Log", "Xpath", "GenRouter", "custom", "helper", "loop", "tableAdd",
}

GENERIC_UI = {
    "Fields", "Field", "Advance Field", "Basic Field", "Start", "Alert",
    "CheckBox", "CheckBox Group", "Divider", "File", "Grid", "Group", "HTML",
    "Inline", "Input", "Input Number", "Layout", "Link", "Radio", "Select",
    "Slider", "Switch", "Text", "TextArea", "Title", "BaseEdge",
}

ACTION_IDENT_RE = re.compile(r"\b(action[A-Z][A-Za-z0-9_$]{1,80})\b")
STRING_RE = re.compile(r'(["\'])(?P<v>(?:\\.|(?!\1).){1,120})\1')
PROPERTY_RE = re.compile(r'(?:^|[,{])\s*(?:["\'])?([A-Za-z_$][A-Za-z0-9_$]{0,64})(?:["\'])?\s*:')

RUNTIME_KEYS = {
    "successNode", "failNode", "nodeLog", "nodeSleep", "nodeTimeout",
    "timeoutAdbReconnect", "timeoutNextNode", "timeoutType", "timeoutFrom",
    "timeoutTo", "timeout", "outputVariable", "casePaths", "breakpoint",
    "disabled", "sourceHandle", "targetHandle", "options", "action",
}

NOISY_PROPERTY_KEYS = {
    "id", "x", "y", "data", "value", "label", "name", "type", "style",
    "class", "className", "children", "icon", "color", "width", "height",
    "key", "title", "component", "props", "default", "length",
}


def default_asar() -> Path:
    local = os.getenv("LOCALAPPDATA")
    return Path(local or ".") / "Programs" / "GenFarmer" / "resources" / "app.asar"


def decode(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    return bytes(raw).decode("utf-8", errors="ignore")


def safe_string(value: str) -> str | None:
    value = value.strip()
    if not value or len(value) > 80:
        return None
    if any(x in value for x in ("\n", "\r", "@", "http://", "https://", "data:", "{", "}")):
        return None
    if not re.fullmatch(r"[A-Za-z0-9 _./:+()#%&,'!?\-]+", value):
        return None
    if value.count("-") >= 5 or value.count("/") >= 3:
        return None
    return value


def looks_like_label(value: str) -> bool:
    if value in GENERIC_UI:
        return False
    if value in KNOWN_LABELS or value in DISCOVERED_LABELS:
        return True
    if value in AMBIGUOUS_TOKENS:
        return True
    if len(value) < 3 or len(value) > 55:
        return False
    words = value.split()
    if not (1 <= len(words) <= 6):
        return False
    if value.lower() in {"true", "false", "null", "undefined", "default", "error", "success", "warning"}:
        return False
    if " " in value and value[0].isalpha():
        return True
    if re.fullmatch(r"[A-Z][A-Za-z0-9]{2,30}", value):
        return True
    return False


def normalize_action_identifier(identifier: str) -> str:
    suffix = identifier[len("action"):]
    return suffix or identifier


def distance_weight(distance: int) -> int:
    if distance <= 100:
        return 8
    if distance <= 250:
        return 6
    if distance <= 500:
        return 4
    if distance <= 900:
        return 2
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="Correlate GenFarmer action identifiers with palette labels")
    p.add_argument("--asar", type=Path, default=default_asar())
    p.add_argument("--bundle", default="dist/render/assets/useScriptEditor-HioTuYH4.js")
    p.add_argument("--radius", type=int, default=1200)
    args = p.parse_args()

    asar_path = args.asar.expanduser().resolve()
    if not asar_path.exists():
        print(f"ERROR: app.asar not found: {asar_path}", file=sys.stderr)
        return 2

    try:
        ctx = AsarArchive(asar_path, mode="r")
    except TypeError:
        ctx = AsarArchive.open(str(asar_path))

    with ctx as archive:
        try:
            try:
                raw = archive.read(Path(args.bundle), follow_link=True)
            except TypeError:
                raw = archive.read(Path(args.bundle))
        except Exception as exc:
            print(f"ERROR reading {args.bundle}: {exc}", file=sys.stderr)
            return 1
    text = decode(raw)

    occurrences: dict[str, list[int]] = defaultdict(list)
    for m in ACTION_IDENT_RE.finditer(text):
        occurrences[m.group(1)].append(m.start())

    action_records = []
    palette_evidence: Counter[str] = Counter()
    ambiguous_evidence: Counter[str] = Counter()

    for identifier in sorted(occurrences):
        label_scores: Counter[str] = Counter()
        key_counts: Counter[str] = Counter()
        runtime_counts: Counter[str] = Counter()

        for pos in occurrences[identifier][:50]:
            start = max(0, pos - max(200, args.radius))
            end = min(len(text), pos + len(identifier) + max(200, args.radius))
            chunk = text[start:end]

            for sm in STRING_RE.finditer(chunk):
                value = safe_string(sm.group("v"))
                if not value or not looks_like_label(value):
                    continue
                absolute = start + sm.start()
                distance = abs(absolute - pos)
                score = distance_weight(distance)
                if value in KNOWN_LABELS:
                    score += 12
                elif value in DISCOVERED_LABELS:
                    score += 8
                elif value in AMBIGUOUS_TOKENS:
                    score += 2
                label_scores[value] += score

            for key in PROPERTY_RE.findall(chunk):
                if key not in NOISY_PROPERTY_KEYS:
                    key_counts[key] += 1
            for key in RUNTIME_KEYS:
                count = len(re.findall(rf"\b{re.escape(key)}\b", chunk))
                if count:
                    runtime_counts[key] += count

        likely_labels = [
            {"label": label, "score": score}
            for label, score in label_scores.most_common(15)
        ]
        for item in likely_labels[:5]:
            if item["label"] in AMBIGUOUS_TOKENS:
                ambiguous_evidence[item["label"]] += item["score"]
            else:
                palette_evidence[item["label"]] += item["score"]

        action_records.append({
            "identifier": identifier,
            "derived_action": normalize_action_identifier(identifier),
            "occurrences": len(occurrences[identifier]),
            "likely_labels": likely_labels,
            "nearby_runtime_keys": dict(runtime_counts.most_common()),
            "nearby_property_keys": [
                {"key": key, "count": count}
                for key, count in key_counts.most_common(60)
            ],
        })

    # Independently record strong label presence in the editor bundle.
    direct_label_presence = []
    for label in sorted(KNOWN_LABELS | DISCOVERED_LABELS):
        count = len(re.findall(re.escape(label), text, flags=re.IGNORECASE))
        if count:
            direct_label_presence.append({
                "label": label,
                "occurrences": count,
                "status": "live-known" if label in KNOWN_LABELS else "source-discovered-strong-candidate",
            })

    ambiguous_presence = []
    for token in sorted(AMBIGUOUS_TOKENS):
        count = len(re.findall(rf"(?<![A-Za-z0-9_$]){re.escape(token)}(?![A-Za-z0-9_$])", text))
        if count:
            ambiguous_presence.append({"token": token, "occurrences": count})

    result = {
        "catalog_format": 1,
        "privacy": "shareable action/label correlation only; no raw GenFarmer source snippets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "bundle": args.bundle,
        "bundle_characters": len(text),
        "action_identifier_count": len(action_records),
        "actions": action_records,
        "direct_palette_label_presence": direct_label_presence,
        "palette_label_evidence_from_action_neighborhoods": [
            {"label": label, "score": score}
            for label, score in palette_evidence.most_common(100)
        ],
        "ambiguous_token_presence": ambiguous_presence,
        "ambiguous_token_action_neighborhood_evidence": [
            {"token": token, "score": score}
            for token, score in ambiguous_evidence.most_common(100)
        ],
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-action-label-probe-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "action-label-catalog.shareable.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER ACTION / PALETTE LABEL CORRELATION PROBE")
    print("=" * 78)
    print(f"Bundle: {args.bundle}")
    print(f"action* identifiers discovered: {len(action_records)}")
    print("Top action identifiers and likely labels:")
    for item in action_records[:80]:
        labels = ", ".join(f"{x['label']}({x['score']})" for x in item["likely_labels"][:4]) or "-"
        print(f" - {item['identifier']} -> {item['derived_action']}: {labels}")
    print("Strong palette labels present in bundle:")
    for item in direct_label_presence:
        print(f" - {item['label']}: {item['status']} occurrences={item['occurrences']}")
    print(f"Shareable result: {out.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
