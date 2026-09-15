#!/usr/bin/env python3
"""Release one deferred Boost preparation lease after an explicit decision not to publish.

This is queue hygiene for Phase A. It does not delete media, history, or evidence
and cannot release a lease owned by a different device when --device is supplied.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.boost_media import media_spec  # noqa: E402
from genfarmer_automation.boost_prepare import PreparationLeaseStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Release one TikTok Boost Phase A media reservation")
    ap.add_argument("--media", type=Path, required=True, help="exact local approved media used by the preparation")
    ap.add_argument("--device", required=True, help="device that owns the reservation")
    ap.add_argument(
        "--reservations",
        type=Path,
        default=ROOT / "evidence" / "boost-preparation-leases.private",
    )
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    try:
        spec = media_spec(args.media)
        store = PreparationLeaseStore(args.reservations)
        path = store.lease_path(spec.sha256)
        if not path.exists():
            print("Status:                     NOT_RESERVED")
            print("Mutation:                   NONE")
            return 0
        if not args.apply:
            print("Status:                     DRY_RUN_READY")
            print("Reservation found:          YES")
            print("Release mutation:           NOT PERFORMED (add --apply)")
            return 0
        if not store.release(spec.sha256, device=args.device):
            print("ERROR: reservation exists but is not owned by the supplied device, or could not be released", file=sys.stderr)
            return 1
        print("Status:                     RELEASED")
        print("Reservation released:       YES")
        print("Media/history/evidence:     UNCHANGED")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
