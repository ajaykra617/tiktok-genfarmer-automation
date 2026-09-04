#!/usr/bin/env python3
"""Resolve GenFarmer palette action constants using canonical-map consensus.

V1 already resolved most H.* / Ht.* palette constants, but a few keys can have
multiple string candidates across the minified renderer. This V2 stays
fail-closed and uses a stronger rule:

1. discover exact palette rows with direct label + action + icon;
2. collect all direct constant->string evidence;
3. identify large object-literal maps that cover many palette constants;
4. score those maps against V1's globally unique constants and live-known
   script.flow anchors;
5. accept a canonical map only when it has zero conflicts with those anchors;
6. use that map to disambiguate otherwise-multi-valued constants;
7. use a live-flow literal only when that exact action was already observed in
   a saved GenFarmer script.flow.

No unresolved action is guessed. The report records provenance for every
resolved value: unique-source, canonical-map, or live-flow-anchor.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from genfarmer_action_constant_resolver import (  # noqa: E402
    LIVE_VALIDATION,
    TEXT_SUFFIXES,
    assignment_member,
    default_asar,
    direct_object_pairs,
    discover_palette_constants,
    js_string,
    parser_instance,
    walk,
)

try:
    from asar import AsarArchive
except ImportError:
    print('ERROR: missing package "asar"; run: python -m pip install -e ".[dev]"', file=sys.stderr)
    raise SystemExit(2)


def load_sources(archive_path: Path, assets_prefix: str, max_file_mb: int) -> list[tuple[str, bytes, Any]]:
    parser = parser_instance()
    max_bytes = max(1, max_file_mb) * 1024 * 1024
    out: list[tuple[str, bytes, Any]] = []
    try:
        ctx = AsarArchive(archive_path, mode="r")
    except TypeError:
        ctx = AsarArchive.open(str(archive_path))
    with ctx as archive:
        for raw_path in archive.list():
            path = str(raw_path).replace("\\", "/")
            pp = Path(path)
            if not path.startswith(assets_prefix) or pp.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                try:
                    raw = archive.read(pp, follow_link=True)
                except TypeError:
                    raw = archive.read(pp)
            except Exception:
                continue
            src = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
            if len(src) > max_bytes:
                continue
            out.append((path, src, parser.parse(src).root_node))
    return out


def gather_evidence(
    sources: list[tuple[str, bytes, Any]], constants: set[str]
) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, Any]]]:
    evidence: dict[str, list[dict[str, str]]] = defaultdict(list)
    groups: list[dict[str, Any]] = []

    for path, src, root in sources:
        for node in walk(root):
            if node.type == "object":
                pairs = direct_object_pairs(src, node)
                mappings: dict[str, str] = {}
                for key, value_node in pairs.items():
                    if key not in constants:
                        continue
                    literal = js_string(src, value_node)
                    if literal is None:
                        continue
                    evidence[key].append({"kind": "object-property", "literal": literal, "file": path})
                    mappings[key] = literal
                if len(mappings) >= 3:
                    groups.append({"file": path, "mappings": mappings})

            elif node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left is None or right is None:
                    continue
                owner, key = assignment_member(src, left)
                if not key or key not in constants:
                    continue
                literal = js_string(src, right)
                if literal is None:
                    continue
                evidence[key].append({
                    "kind": "member-assignment",
                    "literal": literal,
                    "file": path,
                    "owner": owner or "",
                })
    return evidence, groups


def global_unique(evidence: dict[str, list[dict[str, str]]], constants: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in constants:
        values = sorted({item["literal"] for item in evidence.get(key, [])})
        if len(values) == 1:
            out[key] = values[0]
    return out


def score_group(group: dict[str, Any], unique: dict[str, str]) -> dict[str, Any]:
    mappings: dict[str, str] = group["mappings"]
    consensus_matches = 0
    consensus_conflicts = 0
    live_matches = 0
    live_mismatches = 0

    for key, literal in mappings.items():
        if key in unique:
            if unique[key] == literal:
                consensus_matches += 1
            else:
                consensus_conflicts += 1
        if key in LIVE_VALIDATION:
            if LIVE_VALIDATION[key] == literal:
                live_matches += 1
            else:
                live_mismatches += 1

    coverage = len(mappings)
    score = (
        coverage * 10
        + consensus_matches * 3
        + live_matches * 30
        - consensus_conflicts * 100
        - live_mismatches * 300
    )
    return {
        "file": group["file"],
        "coverage": coverage,
        "consensus_matches": consensus_matches,
        "consensus_conflicts": consensus_conflicts,
        "live_matches": live_matches,
        "live_mismatches": live_mismatches,
        "score": score,
        "mappings": mappings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail-closed canonical GenFarmer action constant resolver V2")
    ap.add_argument("--asar", type=Path, default=default_asar())
    ap.add_argument("--assets-prefix", default="dist/render/assets/")
    ap.add_argument("--max-file-mb", type=int, default=8)
    args = ap.parse_args()

    archive_path = args.asar.expanduser().resolve()
    if not archive_path.exists():
        print(f"ERROR: app.asar not found: {archive_path}", file=sys.stderr)
        return 2

    sources = load_sources(archive_path, args.assets_prefix, args.max_file_mb)
    palette_rows, constants = discover_palette_constants(sources)
    evidence, raw_groups = gather_evidence(sources, constants)
    unique = global_unique(evidence, constants)

    scored = [score_group(g, unique) for g in raw_groups]
    scored.sort(key=lambda g: (-g["score"], -g["coverage"], g["file"]))

    minimum_coverage = max(10, len(constants) // 4)
    canonical_candidates = [
        g for g in scored
        if g["coverage"] >= minimum_coverage
        and g["consensus_conflicts"] == 0
        and g["live_mismatches"] == 0
    ]
    canonical = canonical_candidates[0] if canonical_candidates else None

    resolved: dict[str, dict[str, Any]] = {}
    for key in sorted(constants):
        values = Counter(item["literal"] for item in evidence.get(key, []))
        candidates = [{"literal": v, "count": c} for v, c in values.most_common()]
        literal = None
        provenance = None

        if key in unique:
            literal = unique[key]
            provenance = "unique-source"
        elif canonical and key in canonical["mappings"]:
            literal = canonical["mappings"][key]
            provenance = "canonical-map"
        elif key in LIVE_VALIDATION:
            # This is independent exact evidence from a real saved script.flow,
            # not an inference from the constant name.
            literal = LIVE_VALIDATION[key]
            provenance = "live-flow-anchor"

        validation = None
        if key in LIVE_VALIDATION:
            expected = LIVE_VALIDATION[key]
            validation = {
                "expected_live_literal": expected,
                "status": "match" if literal == expected else ("unresolved" if literal is None else "mismatch"),
            }

        resolved[key] = {
            "resolved_literal": literal,
            "provenance": provenance,
            "candidate_literals": candidates,
            "evidence_files": sorted({item["file"] for item in evidence.get(key, [])}),
            "validation": validation,
        }

    enriched_rows = []
    for row in palette_rows:
        info = resolved[row["constant"]]
        enriched = dict(row)
        enriched.update({
            "resolved_literal": info["resolved_literal"],
            "resolution_provenance": info["provenance"],
            "candidate_literals": info["candidate_literals"],
        })
        enriched_rows.append(enriched)

    unresolved = [k for k, v in resolved.items() if not v["resolved_literal"]]
    provenance_counts = Counter(v["provenance"] or "unresolved" for v in resolved.values())
    live_checks = [v["validation"] for v in resolved.values() if v.get("validation")]
    live_matches = sum(1 for x in live_checks if x and x.get("status") == "match")

    result = {
        "catalog_format": 2,
        "privacy": "shareable constant/literal consensus evidence only; no raw GenFarmer source snippets",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "renderer_assets_parsed": len(sources),
        "palette_row_count": len(palette_rows),
        "palette_constants_discovered": len(constants),
        "resolved_constant_count": len(constants) - len(unresolved),
        "unresolved_constants": unresolved,
        "resolution_provenance_counts": dict(provenance_counts),
        "live_validation_matches": live_matches,
        "live_validation_checks": len(live_checks),
        "canonical_map": None if canonical is None else {
            "file": canonical["file"],
            "coverage": canonical["coverage"],
            "consensus_matches": canonical["consensus_matches"],
            "consensus_conflicts": canonical["consensus_conflicts"],
            "live_matches": canonical["live_matches"],
            "live_mismatches": canonical["live_mismatches"],
            "score": canonical["score"],
        },
        "top_map_candidates": [
            {k: g[k] for k in (
                "file", "coverage", "consensus_matches", "consensus_conflicts",
                "live_matches", "live_mismatches", "score"
            )}
            for g in scored[:12]
        ],
        "palette_rows": enriched_rows,
        "constant_resolution": resolved,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "evidence" / f"genfarmer-action-constant-resolver-v2-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "action-constants-v2.shareable.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("GENFARMER CANONICAL ACTION CONSTANT RESOLVER V2")
    print("=" * 78)
    print(f"Renderer assets parsed: {len(sources)}")
    print(f"Palette rows discovered: {len(palette_rows)}")
    print(f"Palette constants discovered: {len(constants)}")
    print(f"Constants resolved: {len(constants) - len(unresolved)}/{len(constants)}")
    print(f"Live-known validation matches: {live_matches}/{len(live_checks)}")
    if canonical:
        print(
            "Canonical map: "
            f"{canonical['file']} coverage={canonical['coverage']} "
            f"consensus={canonical['consensus_matches']} conflicts={canonical['consensus_conflicts']} "
            f"live={canonical['live_matches']}/{canonical['live_matches'] + canonical['live_mismatches']}"
        )
    else:
        print("Canonical map: none accepted (fail-closed)")
    print("Resolution provenance:")
    for key, count in provenance_counts.most_common():
        print(f" - {key}: {count}")
    print("Unresolved constants:")
    if not unresolved:
        print(" - none")
    for key in unresolved:
        candidates = ", ".join(
            f"{x['literal']}({x['count']})" for x in resolved[key]["candidate_literals"]
        ) or "no direct literal candidates"
        print(f" - {key}: {candidates}")
    print("Resolved palette rows:")
    for row in enriched_rows:
        literal = row["resolved_literal"] or "?"
        prov = row["resolution_provenance"] or "unresolved"
        print(f" - {row['label']}: {row['expression']} -> {literal} [{prov}]")
    print(f"Shareable result: {out_path.relative_to(ROOT)}")
    print("Read-only: GenFarmer files were not modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
