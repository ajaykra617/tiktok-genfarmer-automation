#!/usr/bin/env python3
"""Read-only local inspection for the Windows process serving GenFarmer.

This complements HTTP metadata discovery when the local service does not expose
OpenAPI/Swagger documentation. It identifies the process listening on the
configured GenFarmer port, records sanitized process/version metadata, and
optionally scans nearby text assets for route-like strings.

No files are modified and no HTTP mutation requests are sent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]

SENSITIVE_ARG_RE = re.compile(
    r"(?i)(--?(?:password|passwd|secret|token|api[-_]?key|authorization|cookie|credential)(?:=|\s+))(?:\"[^\"]*\"|'[^']*'|[^\s]+)"
)
URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@")
WINDOWS_PATH_RE = re.compile(r'(?i)(?:\"([A-Z]:\\[^\"]+)\"|\b([A-Z]:\\[^\s]+))')
ROUTE_RE = re.compile(
    r"(?<![A-Za-z0-9])/(?:"
    r"api(?:/v\d+)?|v\d+|devices?|projects?|profiles?|fingerprints?|"
    r"automations?|workflows?|tasks?|actions?|scripts?|groups?|instances?|"
    r"settings?|status|info|adb|farms?"
    r")(?:/[A-Za-z0-9_.:{}$-]+){0,10}",
    re.I,
)

TEXT_EXTENSIONS = {
    ".js", ".cjs", ".mjs", ".ts", ".tsx", ".jsx", ".json", ".html",
    ".py", ".txt", ".yaml", ".yml", ".toml", ".ini", ".conf", ".config",
}
SKIP_DIR_NAMES = {
    ".git", "node_modules", "evidence", "logs", "cache", "caches", "temp", "tmp",
}
SKIP_FILE_NAMES = {".env", ".env.local", ".env.production", ".npmrc", ".pypirc"}


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


def sanitize_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = URL_CREDENTIAL_RE.sub(r"\1<redacted>:<redacted>@", value)
    value = SENSITIVE_ARG_RE.sub(r"\1<redacted>", value)
    return value


def run_powershell_json(script: str) -> Any:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "$ProgressPreference='SilentlyContinue'; " + script,
    ]
    proc = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"PowerShell exited {proc.returncode}")
    text = proc.stdout.strip()
    if not text:
        return None
    return json.loads(text)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def process_record(pid: int) -> dict[str, Any]:
    ps = rf"""
$p = Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' -ErrorAction Stop
$parent = $null
if ($p.ParentProcessId) {{
  $parent = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $p.ParentProcessId) -ErrorAction SilentlyContinue
}}
$exePath = $p.ExecutablePath
if (-not $exePath) {{
  $gp = Get-Process -Id {pid} -ErrorAction SilentlyContinue
  if ($gp) {{ $exePath = $gp.Path }}
}}
$version = $null
if ($exePath -and (Test-Path -LiteralPath $exePath)) {{
  $item = Get-Item -LiteralPath $exePath
  $version = [PSCustomObject]@{{
    FileVersion = $item.VersionInfo.FileVersion
    ProductVersion = $item.VersionInfo.ProductVersion
    ProductName = $item.VersionInfo.ProductName
    CompanyName = $item.VersionInfo.CompanyName
  }}
}}
[PSCustomObject]@{{
  ProcessId = [int]$p.ProcessId
  Name = $p.Name
  ExecutablePath = $exePath
  ParentProcessId = [int]$p.ParentProcessId
  ParentName = if ($parent) {{ $parent.Name }} else {{ $null }}
  CommandLine = $p.CommandLine
  Version = $version
}} | ConvertTo-Json -Depth 5 -Compress
"""
    data = run_powershell_json(ps)
    if not isinstance(data, dict):
        raise RuntimeError(f"Could not read process metadata for PID {pid}")
    if data.get("CommandLine"):
        data["CommandLine"] = sanitize_text(str(data["CommandLine"]))
    return data


def existing_paths_from_command_line(command_line: str | None) -> Iterable[Path]:
    if not command_line:
        return []
    found: list[Path] = []
    for match in WINDOWS_PATH_RE.finditer(command_line):
        raw = (match.group(1) or match.group(2) or "").rstrip(",;)")
        if not raw:
            continue
        p = Path(raw)
        if p.exists():
            found.append(p)
    return found


def should_skip_path(path: Path) -> bool:
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts & SKIP_DIR_NAMES:
        return True
    if path.name.lower() in SKIP_FILE_NAMES:
        return True
    name_lower = path.name.lower()
    if any(word in name_lower for word in ("secret", "credential", "password", "cookie")):
        return True
    return False


def normalize_route(route: str) -> str:
    route = route.split("?", 1)[0].split("#", 1)[0]
    return route.rstrip(".,;)'\"`]") or "/"


def scan_route_strings(
    roots: list[Path],
    max_files: int,
    max_file_bytes: int,
) -> tuple[list[str], list[dict[str, str]], int]:
    routes: set[str] = set()
    examples: list[dict[str, str]] = []
    scanned = 0
    seen_files: set[Path] = set()

    for root in roots:
        base = root if root.is_dir() else root.parent
        if not base.exists():
            continue
        try:
            iterator = base.rglob("*")
            for path in iterator:
                if scanned >= max_files:
                    break
                try:
                    if not path.is_file() or path in seen_files or should_skip_path(path):
                        continue
                    if path.suffix.lower() not in TEXT_EXTENSIONS:
                        continue
                    if path.stat().st_size > max_file_bytes:
                        continue
                    seen_files.add(path)
                    scanned += 1
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except (OSError, PermissionError):
                    continue

                for match in ROUTE_RE.finditer(text):
                    route = normalize_route(match.group(0))
                    if len(route) > 200:
                        continue
                    if route not in routes:
                        routes.add(route)
                        if len(examples) < 200:
                            try:
                                rel = str(path.relative_to(base))
                            except ValueError:
                                rel = path.name
                            examples.append({"route": route, "source_file": rel})
                if len(routes) >= 500:
                    break
        except (OSError, PermissionError):
            continue
        if scanned >= max_files or len(routes) >= 500:
            break

    return sorted(routes), examples, scanned


def candidate_files(root: Path, limit: int = 80) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    base = root if root.is_dir() else root.parent
    out: list[dict[str, Any]] = []
    try:
        for path in base.rglob("*"):
            if len(out) >= limit:
                break
            try:
                if not path.is_file() or should_skip_path(path):
                    continue
                lower = path.name.lower()
                if (
                    path.suffix.lower() in {".asar", ".js", ".json", ".py", ".exe"}
                    or any(word in lower for word in ("server", "route", "api", "app", "package"))
                ):
                    out.append({
                        "path": str(path.relative_to(base)),
                        "size": path.stat().st_size,
                    })
            except (OSError, PermissionError, ValueError):
                continue
    except (OSError, PermissionError):
        return out
    return out


def main() -> int:
    if os.name != "nt":
        print("ERROR: this inspection script is Windows-only", file=sys.stderr)
        return 2

    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Read-only local GenFarmer process/API surface inspection")
    parser.add_argument("--base-url", default=os.getenv("GENFARMER_BASE_URL"))
    parser.add_argument("--no-scan", action="store_true", help="Skip nearby text-asset route scan")
    parser.add_argument("--scan-limit", type=int, default=800, help="Maximum text files to scan")
    parser.add_argument("--max-file-bytes", type=int, default=2_000_000)
    args = parser.parse_args()

    if not args.base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env or pass --base-url", file=sys.stderr)
        return 2

    parsed = urllib.parse.urlparse(args.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        print("ERROR: GENFARMER_BASE_URL must be an http(s) URL", file=sys.stderr)
        return 2
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    listener_ps = rf"""
@(Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,OwningProcess) | ConvertTo-Json -Depth 3 -Compress
"""
    listeners = as_list(run_powershell_json(listener_ps))
    if not listeners:
        print(f"ERROR: no listening process found on TCP port {port}", file=sys.stderr)
        return 1

    pids = sorted({int(x["OwningProcess"]) for x in listeners if x.get("OwningProcess")})
    processes = [process_record(pid) for pid in pids]

    roots: list[Path] = []
    for proc in processes:
        exe = proc.get("ExecutablePath")
        if exe:
            p = Path(str(exe))
            if p.exists():
                roots.append(p.parent)
        roots.extend(existing_paths_from_command_line(proc.get("CommandLine")))

    # Deduplicate while preserving order and avoid scanning drive roots.
    unique_roots: list[Path] = []
    seen: set[str] = set()
    for item in roots:
        base = item if item.is_dir() else item.parent
        try:
            resolved = base.resolve()
        except OSError:
            continue
        if resolved.parent == resolved:  # filesystem root
            continue
        key = str(resolved).lower()
        if key not in seen:
            seen.add(key)
            unique_roots.append(resolved)

    routes: list[str] = []
    route_examples: list[dict[str, str]] = []
    files_scanned = 0
    if not args.no_scan:
        routes, route_examples, files_scanned = scan_route_strings(
            unique_roots,
            max_files=max(1, args.scan_limit),
            max_file_bytes=max(1024, args.max_file_bytes),
        )

    inventory: list[dict[str, Any]] = []
    for root in unique_roots[:8]:
        inventory.append({
            "root": str(root),
            "candidate_files": candidate_files(root),
        })

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = ROOT / "evidence" / f"genfarmer-local-inspect-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_path = evidence_dir / "result.json"

    output = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": f"{parsed.scheme}://{parsed.hostname}:{port}",
        "port": port,
        "safety": "read-only Windows process metadata and nearby text-asset route-string scan",
        "listeners": listeners,
        "processes": processes,
        "candidate_roots": [str(x) for x in unique_roots],
        "files_scanned": files_scanned,
        "route_candidates": routes,
        "route_examples": route_examples,
        "file_inventory": inventory,
    }
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 72)
    print("GENFARMER LOCAL PROCESS / ROUTE DISCOVERY")
    print("=" * 72)
    print(f"Listening port: {port}")
    for proc in processes:
        print(f"PID: {proc.get('ProcessId')}  Process: {proc.get('Name')}")
        print(f"Executable: {proc.get('ExecutablePath')}")
        version = proc.get("Version") or {}
        if version:
            print(f"Product: {version.get('ProductName')}  Version: {version.get('ProductVersion') or version.get('FileVersion')}")
        if proc.get("ParentName"):
            print(f"Parent: {proc.get('ParentName')} ({proc.get('ParentProcessId')})")
        if proc.get("CommandLine"):
            print(f"Command line (sanitized): {proc.get('CommandLine')}")

    print("\nCandidate application roots:")
    for path in unique_roots[:8]:
        print(f" - {path}")

    print(f"\nText files scanned: {files_scanned}")
    print(f"Route-like strings discovered: {len(routes)}")
    for route in routes[:80]:
        print(f" - {route}")
    if len(routes) > 80:
        print(f" ... {len(routes) - 80} more saved in local evidence")

    print(f"\nResult: {out_path.relative_to(ROOT)}")
    print("No files were modified.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
