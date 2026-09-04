#!/usr/bin/env python3
"""Read-only packaged-application inspection for the local GenFarmer install.

Use this after `genfarmer_local_inspect.py` identifies the GenFarmer executable but
no route strings are present in loose text files. The script inventories the
install directory, detects common desktop packaging layouts (Electron/Tauri),
and scans selected packaged resources for API/route-related printable strings.

It does not extract, overwrite, patch, or execute GenFarmer application files.
Only local evidence under this repository's ignored `evidence/` directory is
written.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]

SENSITIVE_RE = re.compile(
    r"(?i)(password|passwd|secret|token|authorization|api[_-]?key|cookie|credential)"
)
URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@")

ROUTE_RE = re.compile(
    r"(?<![A-Za-z0-9])/(?:"
    r"api(?:/v\d+)?|v\d+|devices?|projects?|profiles?|fingerprints?|"
    r"automations?|workflows?|tasks?|actions?|scripts?|groups?|instances?|"
    r"settings?|status|info|adb|farms?|apps?|packages?|phones?|proxies?"
    r")(?:/[A-Za-z0-9_.:{}$?&=+%-]+){0,12}",
    re.I,
)

KEYWORDS = {
    "api",
    "device",
    "devices",
    "project",
    "projects",
    "profile",
    "fingerprint",
    "automation",
    "workflow",
    "adb",
    "55554",
    "localhost",
    "127.0.0.1",
    "axios",
    "fetch(",
    "express",
    "fastify",
    "electron",
    "tauri",
}

INTERESTING_EXTENSIONS = {
    ".asar", ".js", ".cjs", ".mjs", ".json", ".html", ".pak", ".bin",
    ".dat", ".exe", ".dll", ".node", ".wasm",
}

PRIORITY_NAMES = {
    "app.asar",
    "package.json",
    "resources.pak",
    "main.js",
    "index.js",
    "electron.asar",
}

SKIP_NAMES = {
    ".env", ".env.local", ".env.production", ".npmrc", ".pypirc",
}


def sanitize_text(value: str) -> str:
    value = URL_CREDENTIAL_RE.sub(r"\1<redacted>:<redacted>@", value)
    value = re.sub(
        r'(?i)(["\']?(?:password|passwd|secret|token|authorization|api[_-]?key|cookie|credential)["\']?\s*[:=]\s*)["\']?[^,}\]\s<]+',
        r"\1<redacted>",
        value,
    )
    return value


def default_install_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return Path.home() / "AppData" / "Local" / "Programs" / "GenFarmer"
    return Path(local) / "Programs" / "GenFarmer"


def safe_rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return path.name


def file_inventory(base: Path, max_files: int = 5000) -> tuple[list[dict[str, Any]], Counter[str]]:
    records: list[dict[str, Any]] = []
    extensions: Counter[str] = Counter()

    for path in base.rglob("*"):
        if len(records) >= max_files:
            break
        try:
            if not path.is_file() or path.name.lower() in SKIP_NAMES:
                continue
            st = path.stat()
        except (OSError, PermissionError):
            continue

        suffix = path.suffix.lower() or "<none>"
        extensions[suffix] += 1
        records.append({
            "path": safe_rel(path, base),
            "size": st.st_size,
            "extension": suffix,
        })

    records.sort(key=lambda x: x["path"].lower())
    return records, extensions


def detect_packaging(base: Path, inventory: list[dict[str, Any]]) -> dict[str, Any]:
    names = {Path(x["path"]).name.lower() for x in inventory}
    rels = {x["path"].replace("\\", "/").lower() for x in inventory}

    electron_markers = sorted(
        marker
        for marker in (
            "resources/app.asar",
            "resources.pak",
            "chrome_100_percent.pak",
            "chrome_200_percent.pak",
            "icudtl.dat",
        )
        if marker in rels or marker in names
    )
    tauri_markers = sorted(
        marker
        for marker in ("webview2loader.dll", "tauri.conf.json")
        if marker in names
    )

    return {
        "electron_likely": bool(electron_markers),
        "electron_markers": electron_markers,
        "tauri_likely": bool(tauri_markers) and not bool(electron_markers),
        "tauri_markers": tauri_markers,
    }


def candidate_files(base: Path, inventory: list[dict[str, Any]], max_candidates: int) -> list[Path]:
    scored: list[tuple[int, int, str, Path]] = []

    for item in inventory:
        rel = item["path"]
        path = base / rel
        name = path.name.lower()
        suffix = path.suffix.lower()
        size = int(item["size"])

        if name in SKIP_NAMES:
            continue
        if suffix not in INTERESTING_EXTENSIONS and name not in PRIORITY_NAMES:
            continue

        score = 0
        if name in PRIORITY_NAMES:
            score += 100
        if suffix == ".asar":
            score += 90
        if suffix in {".js", ".cjs", ".mjs", ".json", ".html"}:
            score += 70
        if "resource" in rel.lower():
            score += 30
        if any(k in name for k in ("app", "main", "server", "api", "route", "bundle")):
            score += 25
        if suffix in {".exe", ".dll", ".pak", ".bin", ".dat"}:
            score += 10

        scored.append((-score, size, rel.lower(), path))

    scored.sort()
    return [entry[3] for entry in scored[:max_candidates]]


def interesting_line(text: str) -> bool:
    lower = text.lower()
    return any(keyword in lower for keyword in KEYWORDS)


def printable_ascii_runs(data: bytes, min_len: int = 6) -> Iterable[str]:
    # Printable ASCII runs. App.asar JavaScript content is normally directly visible here.
    for match in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, data):
        yield match.group(0).decode("ascii", errors="ignore")


def printable_utf16le_runs(data: bytes, min_len: int = 6) -> Iterable[str]:
    pattern = rb"(?:[\x20-\x7e]\x00){%d,}" % min_len
    for match in re.finditer(pattern, data):
        yield match.group(0).decode("utf-16le", errors="ignore")


def scan_file(
    path: Path,
    base: Path,
    max_scan_bytes: int,
    max_matches: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": safe_rel(path, base),
        "size": None,
        "bytes_scanned": 0,
        "truncated": False,
        "route_candidates": [],
        "interesting_strings": [],
        "error": None,
    }

    try:
        size = path.stat().st_size
        result["size"] = size
        scan_size = min(size, max_scan_bytes)
        result["truncated"] = size > scan_size

        # Read from both beginning and end for capped large files. This remains read-only.
        if size <= max_scan_bytes:
            data = path.read_bytes()
        else:
            half = max_scan_bytes // 2
            with path.open("rb") as fh:
                head = fh.read(half)
                fh.seek(max(0, size - half))
                tail = fh.read(half)
            data = head + b"\n<SCAN_GAP>\n" + tail

        result["bytes_scanned"] = len(data)
    except (OSError, PermissionError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    routes: set[str] = set()
    strings: list[str] = []
    seen_strings: set[str] = set()

    def consider(value: str) -> None:
        nonlocal strings
        value = sanitize_text(value.strip())
        if not value or len(value) > 1200:
            return

        for match in ROUTE_RE.finditer(value):
            route = match.group(0).rstrip(".,;)'\"`]")
            if route and len(route) <= 240:
                routes.add(route)

        if interesting_line(value):
            compact = re.sub(r"\s+", " ", value)
            if compact not in seen_strings:
                seen_strings.add(compact)
                strings.append(compact[:1000])

    for value in printable_ascii_runs(data):
        consider(value)
        if len(strings) >= max_matches and len(routes) >= max_matches:
            break

    if len(strings) < max_matches or len(routes) < max_matches:
        for value in printable_utf16le_runs(data):
            consider(value)
            if len(strings) >= max_matches and len(routes) >= max_matches:
                break

    result["route_candidates"] = sorted(routes)[:max_matches]
    result["interesting_strings"] = strings[:max_matches]
    return result


def main() -> int:
    if os.name != "nt":
        print("ERROR: this script is intended for the Windows GenFarmer workstation", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(description="Read-only GenFarmer packaged-application inspection")
    parser.add_argument("--install-root", default=str(default_install_root()))
    parser.add_argument("--max-files", type=int, default=5000)
    parser.add_argument("--max-candidates", type=int, default=40)
    parser.add_argument(
        "--max-scan-mb",
        type=int,
        default=64,
        help="Maximum bytes sampled per candidate file (split head/tail for larger files)",
    )
    parser.add_argument("--max-matches", type=int, default=120)
    args = parser.parse_args()

    base = Path(args.install_root).expanduser().resolve()
    if not base.is_dir():
        print(f"ERROR: install root not found: {base}", file=sys.stderr)
        return 1

    print("=" * 76)
    print("GENFARMER PACKAGED APPLICATION INSPECTION")
    print("=" * 76)
    print(f"Install root: {base}")
    print("Mode: read-only")

    inventory, extensions = file_inventory(base, max_files=max(1, args.max_files))
    packaging = detect_packaging(base, inventory)
    candidates = candidate_files(base, inventory, max_candidates=max(1, args.max_candidates))

    print(f"Files inventoried: {len(inventory)}")
    print(
        "Packaging: "
        + ("Electron likely" if packaging["electron_likely"] else "Tauri likely" if packaging["tauri_likely"] else "undetermined")
    )

    priority_present = [
        item for item in inventory
        if Path(item["path"]).name.lower() in PRIORITY_NAMES or Path(item["path"]).suffix.lower() == ".asar"
    ]
    if priority_present:
        print("\nHigh-value packaged resources:")
        for item in priority_present[:30]:
            print(f" - {item['path']} ({item['size']} bytes)")

    max_scan_bytes = max(1, args.max_scan_mb) * 1024 * 1024
    scans: list[dict[str, Any]] = []
    all_routes: set[str] = set()

    print(f"\nScanning up to {len(candidates)} candidate resource files...")
    for idx, path in enumerate(candidates, 1):
        record = scan_file(
            path,
            base,
            max_scan_bytes=max_scan_bytes,
            max_matches=max(1, args.max_matches),
        )
        scans.append(record)
        all_routes.update(record.get("route_candidates", []))
        route_count = len(record.get("route_candidates", []))
        string_count = len(record.get("interesting_strings", []))
        if route_count or string_count or path.suffix.lower() == ".asar":
            print(
                f"[{idx:02d}] {record['path']} -> "
                f"routes={route_count}, interesting_strings={string_count}, "
                f"scanned={record['bytes_scanned']}"
            )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = ROOT / "evidence" / f"genfarmer-package-inspect-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_path = evidence_dir / "result.json"

    output = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "safety": "read-only inventory and printable-string scan; GenFarmer install files were not modified",
        "install_root": str(base),
        "packaging": packaging,
        "inventory_count": len(inventory),
        "extension_counts": dict(extensions.most_common()),
        "high_value_resources": priority_present[:100],
        "candidate_files": [safe_rel(p, base) for p in candidates],
        "route_candidates": sorted(all_routes),
        "scans": scans,
    }
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nUnique route-like candidates: {len(all_routes)}")
    for route in sorted(all_routes)[:100]:
        print(f" - {route}")
    if len(all_routes) > 100:
        print(f" ... {len(all_routes) - 100} more saved in local evidence")

    print("\nTop file extensions:")
    for ext, count in extensions.most_common(15):
        print(f" - {ext}: {count}")

    print(f"\nResult: {out_path.relative_to(ROOT)}")
    print("No GenFarmer files were modified or extracted.")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
