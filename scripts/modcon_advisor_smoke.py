#!/usr/bin/env python3
"""Harmless ModCon advisor connectivity/JSON-contract smoke test.

This script never touches ADB or a device. It sends one synthetic recovery context
through the constrained advisor so the operator can validate credentials, endpoint,
model ID, JSON compatibility and response validation before enabling AI on workers.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from genfarmer_automation.ai_advisor import (  # noqa: E402
    AdvisorError,
    ModConRecoveryAdvisor,
    RecoveryDecisionContext,
)


def main() -> int:
    try:
        advisor = ModConRecoveryAdvisor()
        context = RecoveryDecisionContext(
            device="synthetic-device",
            reason="TikTok FYP remained loading after bounded settle; last counts=(0, 0)",
            child_status="BLOCKED",
            returncode=1,
            consecutive_failures=2,
            trace_summary={
                "available": True,
                "event_count": 42,
                "adb_timeouts": 0,
                "mutation_timeouts": 0,
                "live_hint_events": 1,
                "unclassified_live_hint_events": 1,
                "last_fyp_state": "loading",
                "last_interrupt": "none",
                "last_foreground_package": "com.zhiliaoapp.musically",
                "last_hierarchy_provider": "service",
                "important_events": [
                    {
                        "category": "live",
                        "event": "live-hints-unclassified",
                        "level": "WARNING",
                        "details": {
                            "classified_live_card": False,
                            "fyp_state": "loading",
                        },
                    }
                ],
            },
        )
        decision = advisor.advise(context)
    except AdvisorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("=" * 78)
    print("MODCON RECOVERY ADVISOR SMOKE")
    print("=" * 78)
    print(f"Endpoint: {advisor.base_url}")
    print(f"Model:    {advisor.model}")
    print("Device/ADB actions: NONE")
    print("Decision:")
    print(json.dumps(decision.to_dict(), indent=2, ensure_ascii=False))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
