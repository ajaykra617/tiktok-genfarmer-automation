#!/usr/bin/env python3
"""Read-only palette cluster/import probe for GenFarmer's minified editor bundle.

The Automation editor bundle is minified and has no source map. Object-boundary
heuristics are therefore weak. This probe instead uses two facts already proven
in the lab:

* `useScriptEditor-*.js` contains every known palette label in one file;
* additional real palette labels (for example `Uninstall App`) are present there.

The probe merges text neighborhoods around known palette anchors, extracts only
safe string tokens (not raw source), and inventories local JS imports/dynamic
imports. This can reveal sibling palette labels and node-specific chunks without
copying proprietary source code.

No GenFarmer files are modified and no workflow/API mutation is performed.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

try:
    from asar import AsarArchive
except ImportError:
    print('ERROR: missing package "asar"; run: python -m pip install -e ".[dev]"', file=sys.stderr)
    raise SystemExit(2)

KNOWN = (
    "Press Back", "Press Home", "Press Menu", "Change device", "Start App",
    "Stop App", "Install App", "Uninstall App", "Variables", "Context Menu",
    "ADB shell command", "Sleep", "Screenshot", "DeepSeek",
)

# Generic form-builder/control labels already observed in the same bundle. These
# are useful settings UI primitives, but should not be mistaken for automation
# palette nodes.
GENERIC_UI = {
    "Fields", "Field", "Advance Field", "Basic Field", "Start", "Alert",
    "CheckBox", "CheckBox Group", "Divider", "File", "Grid", "Group", "HTML",
    "Inline", "Input", "Input Number", "Layout", "Link", "Radio", "Select",
    "Slider", "Switch", "Text", "TextArea", "Title", "BaseEdge",
}

STRING_RE = re.compile(r'(["\'])(?P<v>(?:\\.|(?!\1).){1,160})\1')
IMPORT_RE = re.compile(
    r'(?:from\s*|import\s*\(\s*|import\s*)["\'](?P<p>\.?\.?/[A-Za-z0-9_./-]+\.js)["\']'
)
SAFE_PAIR_RE = re.compile(
    r'(?:(?:["\'])?(?P<k>label|title|name|action|type|nodeType|category|group|component|kind)(?:["\'])?)'
    r'\s*:\s*(?P<q>["\'])(?P<v>(?:\\.|(?!\2).){1,120})\2'
)
IDENT_PAIR_RE = re.compile(
    r'(?:(?:["\'])?(?P<k>action|type|nodeType|category|group|component|kind)(?:["\'])?)'
    r'\s*:\s*(?P<v>[A-Za-z_$][A-Za-z0-9_$]{0,80})(?=\s*[,}])'
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
    # Keep human-readable labels/tokens and reject minified/CSS-heavy strings.
    if not re.fullmatch(r"[A-Za-z0-9 _./:+()#%&,'!?\-]+", value):
        return None
    if value.count("-") >= 5 or value.count("/") >= 3:
        return None
    return value


def label_score(value: str) -> int:
    if value in KNOWN:
        return 100
    if value in GENERIC_UI:
        return -20
    score = 0
    words = value.split()
    if 1 <= len(words) <= 6:
        score += 1
    if any(ch.isupper() for ch in value):
        score += 1
    if " " in value:
        score += 2
    if value[:1].isupper():
        score += 1
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(?: [A-Za-z0-9][A-Za-z0-9]*){0,5}", value):
        score += 2
    if len(value) < 3 or len(value) > 60:
        score -= 2
    # Common implementation/library noise.
    if value.lower() in {
        "true", "false", "null", "undefined", "default", "object", "string",
        "number", "boolean", "function", "error", "success", "info", "warning",
        "primary", "secondary", "left", "right", "top", "bottom",
    }:
        score -= 10
    return score


def merge_intervals(intervals: list[tuple[int, int]], gap: int = 1500) -> list[tuple[int, int]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    out = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return [(a, b) for a, b in out]


def resolve_import(bundle: str, spec: str) -> str:
    base = PurePosixPath(bundle).parent
    # PurePosixPath does not collapse '..' by itself; normalize manually.
    parts: list[str] = []
    for part in (base / spec).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def main() -> int:
    p = argparse.ArgumentParser(description="Probe minified GenFarmer palette clusters and editor imports")
    p.add_argument("--asar", type=Path, default=default_asar())
    p.add_argument("--bundle", default="dist/render/assets/useScriptEditor-HioTuYH4.js")
    p.add_argument("--radius", type=int, default=5000)
    p.add_argument("--merge-gap", type=int, default=1800)
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
            entries = {str(x).replace("\\", "/") for x in archive.list()}
            try:
                raw = archive.read(Path(args.bundle), follow_link=True)
            except TypeError:
                raw = archive.read(Path(args.bundle))
        except Exception as exc:
            print(f"ERROR reading bundle {args.bundle}: {exc}", file=sys.stderr)
            return 1
        text = decode(raw)

        positions: dict[str, list[int]] = {}
        intervals: list[tuple[int, int]] = []
        for label in KNOWN:
            pos = [m.start() for m in re.finditer(re.escape(label), text, flags=re.IGNORECASE)]
            positions[label] = pos
            for x in pos:
                intervals.append((max(0, x - args.radius), min(len(text), x + len(label) + args.radius)))

        clusters = merge_intervals(intervals, gap=max(0, args.merge_gap))
        cluster_records = []
        global_candidates: Counter[str] = Counter()
        for idx, (start, end) in enumerate(clusters, 1):
            chunk = text[start:end]
            known_here = [label for label, pos in positions.items() if any(start <= x < end for x in pos)]

            ordered: list[str] = []
            seen_order: set[str] = set()
            counts: Counter[str] = Counter()
            for m in STRING_RE.finditer(chunk):
                value = safe_string(m.group("v"))
                if not value:
                    continue
                counts[value] += 1
                if value not in seen_order:
                    seen_order.add(value)
                    ordered.append(value)

            candidates = []
            for value in ordered:
                score = label_score(value)
                if score < 3:
                    continue
                global_candidates[value] += max(1, score) * counts[value]
                candidates.append({"label": value, "score": score, "count": counts[value]})

            safe_pairs = []
            for m in SAFE_PAIR_RE.finditer(chunk):
                value = safe_string(m.group("v"))
                if value:
                    safe_pairs.append({"field": m.group("k"), "value": value})
            # Deduplicate while preserving order.
            dedup_pairs = []
            seen_pairs = set()
            for item in safe_pairs:
                key = (item["field"], item["value"])
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    dedup_pairs.append(item)

            ident_pairs = []
            seen_ident = set()
            for m in IDENT_PAIR_RE.finditer(chunk):
                key = (m.group("k"), m.group("v"))
                if key in seen_ident or m.group("v") in {"true", "false", "null", "undefined"}:
                    continue
                seen_ident.add(key)
                ident_pairs.append({"field": m.group("k"), "identifier": m.group("v")})

            cluster_records.append({
                "cluster": idx,
                "start": start,
                "end": end,
                "length": end - start,
                "known_labels": known_here,
                "ordered_label_candidates": candidates[:250],
                "safe_string_field_pairs": dedup_pairs[:250],
                "identifier_field_pairs": ident_pairs[:250],
            })

        import_specs = []
        seen_specs = set()
        for m in IMPORT_RE.finditer(text):
            spec = m.group("p")
            if spec in seen_specs:
                continue
            seen_specs.add(spec)
            resolved = resolve_import(args.bundle, spec)
            import_specs.append({
                "specifier": spec,
                "resolved": resolved,
                "exists_in_asar": resolved in entries,
                "basename": PurePosixPath(resolved).name,
            })

        # Inspect imported modules structurally: only filenames, known-label hits,
        # runtime-key presence, and safe human-readable label candidates.
        imported_module_summaries = []
        runtime_keys = (
            "successNode", "failNode", "nodeLog", "nodeSleep", "nodeTimeout",
            "timeoutAdbReconnect", "timeoutNextNode", "timeoutType", "outputVariable",
            "casePaths", "breakpoint", "disabled", "action",
        )
        for item in import_specs[:300]:
            resolved = item["resolved"]
            if not item["exists_in_asar"]:
                continue
            try:
                try:
                    raw2 = archive.read(Path(resolved), follow_link=True)
                except TypeError:
                    raw2 = archive.read(Path(resolved))
                mod = decode(raw2)
            except Exception:
                continue
            known_hits = [x for x in KNOWN if x.lower() in mod.lower()]
            keys = [k for k in runtime_keys if re.search(rf"\b{re.escape(k)}\b", mod)]
            # Filename itself is often highly informative in Vite chunks.
            basename_stem = PurePosixPath(resolved).name.rsplit("-", 1)[0]
            imported_module_summaries.append({
                "path": resolved,
                "basename_stem": basename_stem,
                "characters": len(mod),
                "known_label_hits": known_hits,
                "runtime_keys_present": keys,
            })

    result = {
        "catalog_format": 1,
        "privacy": "shareable minified-bundle token/import structure only; no raw GenFarmer source snippets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "bundle": args.bundle,
        "bundle_characters": len(text),
        "known_labels": {k: len(v) for k, v in positions.items()},
        "cluster_count": len(cluster_records),
        "clusters": cluster_records,
        "global_label_candidates": [
            {"label": label, "score": score}
            for label, score in global_candidates.most_common(300)
            if label not in GENERIC_UI
        ],
        "local_js_imports": import_specs,
        "imported_module_summaries": imported_module_summaries,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-palette-cluster-probe-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "palette-cluster.shareable.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER MINIFIED PALETTE CLUSTER / IMPORT PROBE")
    print("=" * 78)
    print(f"Bundle: {args.bundle}")
    print(f"Known labels present: {sum(1 for v in positions.values() if v)}/{len(KNOWN)}")
    print(f"Merged palette clusters: {len(cluster_records)}")
    for cluster in cluster_records:
        print(f" - cluster {cluster['cluster']}: {len(cluster['known_labels'])} known labels, {len(cluster['ordered_label_candidates'])} candidate labels")
    print(f"Local JS imports discovered: {len(import_specs)}")
    print("Top global label candidates:")
    for item in result["global_label_candidates"][:60]:
        print(f" - {item['label']}: score={item['score']}")
    print("Imported module/chunk stems:")
    for item in imported_module_summaries[:80]:
        hit = f" labels={','.join(item['known_label_hits'])}" if item['known_label_hits'] else ""
        print(f" - {item['basename_stem']}{hit}")
    print(f"Shareable result: {out.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
