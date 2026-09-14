#!/usr/bin/env python3
"""Write the deterministic disposable MP4 used for Boost qualification."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.boost_fixture import FIXTURE_SHA256, FIXTURE_SIZE, write_fixture  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate disposable Boost qualification MP4")
    ap.add_argument("output", type=Path)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    try:
        target = write_fixture(args.output, overwrite=args.overwrite)
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("=" * 78)
    print("BOOST TEST MEDIA")
    print("=" * 78)
    print(f"Output:                     {target}")
    print("Format:                     H.264 / MP4")
    print("Video:                      360x640 @ 24fps, 3 seconds")
    print("Audio:                      NONE")
    print(f"Size:                       {FIXTURE_SIZE} bytes")
    print(f"SHA-256:                    {FIXTURE_SHA256}")
    print("Source:                     deterministic embedded qualification fixture")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
