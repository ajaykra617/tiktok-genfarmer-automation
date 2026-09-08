#!/usr/bin/env python3
"""Read-only focused inspection of GenFarmer's packaged UI automation engine.

This is used when the GenFarmer editor exposes XPath fields but no element picker.
It scans the installed Electron app.asar for exact implementation-adjacent terms
such as ElementExists, XPath, page-source, UiAutomator/Appium and findElement.

The script never modifies GenFarmer. Full nearby source context is saved only
under ignored local evidence; console output prints hit counts and structural
neighbor tokens only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import mmap
import os
from pathlib import Path
import re
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

SEARCH_TERMS = (
    "ElementExists",
    "elementExists",
    "Element exists",
    "xpath",
    "XPath",
    "getPageSource",
    "pageSource",
    "page source",
    "findElement",
    "findElements",
    "uiautomator",
    "UiAutomator",
    "uiautomator2",
    "UiAutomator2",
    "dumpWindowHierarchy",
    "windowHierarchy",
    "accessibility",
    "resource-id",
    "content-desc",
    "appium",
    "webdriverio",
)

SENSITIVE = re.compile(r"(?i)(password|passwd|secret|token|authorization|api[_-]?key|cookie|credential)")
IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_.$:/-]{2,100}")


def default_resource() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "Programs" / "GenFarmer" / "resources" / "app.asar"
    return Path.home() / "AppData" / "Local" / "Programs" / "GenFarmer" / "resources" / "app.asar"


def sanitize_context(text: str) -> str:
    # Remove obvious credential-like assignments if they somehow exist in packaged source.
    text = re.sub(
        r'(?i)(["\']?(?:password|passwd|secret|token|authorization|api[_-]?key|cookie|credential)["\']?\s*[:=]\s*)["\'][^"\']*["\']',
        r"\1<redacted>",
        text,
    )
    return text


def offsets(mm: mmap.mmap, needle: bytes, limit: int) -> Iterable[int]:
    start = 0
    for _ in range(limit):
        idx = mm.find(needle, start)
        if idx < 0:
            break
        yield idx
        start = idx + max(1, len(needle))


def structural_tokens(text: str, *, limit: int = 40) -> list[str]:
    counts: Counter[str] = Counter()
    for token in IDENT.findall(text):
        lower = token.lower()
        if len(token) < 3 or SENSITIVE.search(token):
            continue
        if lower in {"true", "false", "null", "undefined", "function", "return", "const", "let", "var"}:
            continue
        counts[token] += 1
    return [token for token, _ in counts.most_common(limit)]


def main() -> int:
    if os.name != "nt":
        print("ERROR: this probe is intended for the Windows GenFarmer workstation", file=sys.stderr)
        return 2

    ap = argparse.ArgumentParser(description="Read-only focused scan of GenFarmer UI automation implementation strings")
    ap.add_argument("--resource", type=Path, default=default_resource())
    ap.add_argument("--context-bytes", type=int, default=1800)
    ap.add_argument("--hits-per-term", type=int, default=12)
    args = ap.parse_args()

    resource = args.resource.expanduser().resolve()
    if not resource.is_file():
        print(f"ERROR: GenFarmer packaged resource not found: {resource}", file=sys.stderr)
        return 1
    if not 200 <= args.context_bytes <= 20000:
        print("ERROR: --context-bytes must be 200..20000", file=sys.stderr)
        return 2
    if not 1 <= args.hits_per_term <= 100:
        print("ERROR: --hits-per-term must be 1..100", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence" / f"genfarmer-ui-engine-probe-{stamp}"
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "resource": str(resource),
        "size": resource.stat().st_size,
        "read_only": True,
        "terms": {},
    }

    print("=" * 78)
    print("GENFARMER UI ENGINE SOURCE PROBE")
    print("=" * 78)
    print(f"Resource: {resource}")
    print("Mode:     READ-ONLY")

    with resource.open("rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            for term in SEARCH_TERMS:
                term_hits = []
                for idx in offsets(mm, term.encode("utf-8"), args.hits_per_term):
                    left = max(0, idx - args.context_bytes)
                    right = min(len(mm), idx + len(term) + args.context_bytes)
                    raw = mm[left:right]
                    text = sanitize_context(raw.decode("utf-8", errors="replace"))
                    term_hits.append({
                        "offset": idx,
                        "context": text,
                        "tokens": structural_tokens(text),
                    })
                result["terms"][term] = term_hits
                if term_hits:
                    combined = "\n".join(hit["context"] for hit in term_hits)
                    tokens = structural_tokens(combined, limit=24)
                    print(f"{term:22} hits={len(term_hits):2d}  nearby={', '.join(tokens[:12]) or '<none>'}")
        finally:
            mm.close()

    private_path = private / "result.private.json"
    private_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    hit_terms = [term for term, hits in result["terms"].items() if hits]
    shareable = {
        "timestamp_utc": result["timestamp_utc"],
        "resource_name": resource.name,
        "resource_size": result["size"],
        "terms_with_hits": hit_terms,
        "hit_counts": {term: len(result["terms"][term]) for term in hit_terms},
        "read_only": True,
    }
    shareable_path = out / "genfarmer-ui-engine-probe.shareable.json"
    shareable_path.write_text(json.dumps(shareable, indent=2), encoding="utf-8")

    print("-" * 78)
    print(f"Terms with hits: {len(hit_terms)}/{len(SEARCH_TERMS)}")
    print(f"Private context: {private_path.relative_to(ROOT)}")
    print(f"Shareable result: {shareable_path.relative_to(ROOT)}")
    print("No GenFarmer files or device state were modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
