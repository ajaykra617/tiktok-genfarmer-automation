#!/usr/bin/env python3
"""Verify that our Python flow model round-trips a GenFarmer app losslessly.

GET-only. It never sends an updated flow back to GenFarmer.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.flow import FlowDocument, FlowError, find_flow  # noqa: E402
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


def main() -> int:
    parser = argparse.ArgumentParser(description="GET-only lossless script.flow round-trip verification")
    parser.add_argument("--app-id", required=True)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("GENFARMER_BASE_URL")
    if not base_url:
        print("ERROR: configure GENFARMER_BASE_URL in .env", file=sys.stderr)
        return 2

    client = GenFarmerClient(base_url, timeout=12.0, allow_mutations=False)
    try:
        payload = client.get_app(args.app_id)
        original = find_flow(payload)
        if original is None:
            raise FlowError("app response does not contain script.flow")
        doc = FlowDocument.from_flow(original)
    except (GenFarmerError, FlowError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    emitted = doc.to_dict()
    exact = original == emitted
    warnings = doc.validate_basic()

    print("=" * 72)
    print("GENFARMER SCRIPT.FLOW LOSSLESS ROUND-TRIP")
    print("=" * 72)
    print(f"App ID: {args.app_id}")
    print(f"Nodes: {len(doc.nodes)}")
    print(f"Edges: {len(doc.edges)}")
    print(f"Canonical SHA-256: {doc.sha256()}")
    print(f"Exact dict equality after Python load/save: {'YES' if exact else 'NO'}")
    print(f"Basic graph warnings: {len(warnings)}")
    for warning in warnings[:30]:
        print(f" - {warning}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = ROOT / "evidence" / f"genfarmer-flow-roundtrip-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "app_id": args.app_id,
        "node_count": len(doc.nodes),
        "edge_count": len(doc.edges),
        "flow_sha256": doc.sha256(),
        "exact_roundtrip": exact,
        "warnings": warnings,
        "node_kinds": [kind for kind, _, _ in doc.node_kinds()],
        "safety": "GET-only; no app state modified",
    }
    out = evidence_dir / "summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Summary: {out.relative_to(ROOT)}")
    print("No GenFarmer state was modified.")
    print("=" * 72)
    return 0 if exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
