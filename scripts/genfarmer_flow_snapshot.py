#!/usr/bin/env python3
"""Capture one GenFarmer Automation App flow for controlled differential learning.

The exact app payload and flow are written only under git-ignored evidence/.
A tiny shareable summary contains IDs only as hashes plus node/edge counts.

GET only. No state changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.flow import FlowDocument  # noqa: E402
from genfarmer_automation.genfarmer_client import GenFarmerClient, GenFarmerError  # noqa: E402


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


def hid(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot one GenFarmer script.flow for before/after learning")
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--tag", default="snapshot", help="Human label such as before/after; used only in local path")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    client = GenFarmerClient(base_url, timeout=12.0, allow_mutations=False)
    try:
        payload = client.get_app(args.app_id)
        doc = FlowDocument.from_app_payload(payload)
    except GenFarmerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: cannot read flow: {exc}", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_tag = "".join(ch for ch in args.tag if ch.isalnum() or ch in "-_")[:40] or "snapshot"
    evidence_dir = ROOT / "evidence" / f"genfarmer-flow-snapshot-{safe_tag}-{stamp}"
    private_dir = evidence_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)

    app_path = private_dir / "app.raw.json"
    flow_path = private_dir / "flow.raw.json"
    app_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    flow_path.write_text(json.dumps(doc.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    summary: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "app_id_hash": hid(str(args.app_id)),
        "flow_sha256": doc.sha256(),
        "nodes": len(doc.nodes),
        "edges": len(doc.edges),
        "warnings": doc.validate_basic(),
        "privacy": "shareable summary only; exact flow remains in private/ under ignored evidence",
    }
    summary_path = evidence_dir / "snapshot.shareable.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 72)
    print("GENFARMER FLOW SNAPSHOT")
    print("=" * 72)
    print(f"Tag: {safe_tag}")
    print(f"Nodes: {len(doc.nodes)}  Edges: {len(doc.edges)}")
    print(f"Flow SHA-256: {doc.sha256()}")
    print(f"PRIVATE flow: {flow_path.relative_to(ROOT)}")
    print(f"Shareable summary: {summary_path.relative_to(ROOT)}")
    print("GET only; no GenFarmer state was modified.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
