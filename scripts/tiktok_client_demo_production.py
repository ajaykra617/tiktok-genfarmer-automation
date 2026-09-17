#!/usr/bin/env python3
"""Production-oriented wrapper for the resilient TikTok client demo.

This composes three layers without duplicating workflow logic:
1. ``tiktok_client_demo`` owns the checkpointed Warm-up + Boost orchestration;
2. ``tiktok_client_demo_resilient`` installs FYP-variant/loading handling;
3. this wrapper replaces the runtime supervisor with a diagnostic subclass that
   captures private Android evidence immediately before and after every hard
   TikTok process restart.

Production also adds one hierarchy-only settle guard for a device-specific race:
GenFarmer's existing UiAutomator helper can report that its service started before
``/dump/hierarchy`` is actually ready. The guard polls that positively identified
helper for a few bounded seconds before allowing the workflow to spend a TikTok
app-restart budget.

The diagnostics are read-only and best-effort. They never block recovery and are
kept under ``evidence/runtime-recovery-diagnostics`` rather than shareable output.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Importing the resilient wrapper installs its FYP proof/restoration hooks into
# the base demo module. Keep this import before replacing the supervisor class.
import tiktok_client_demo_resilient  # noqa: F401,E402
import tiktok_client_demo as demo  # noqa: E402

from genfarmer_automation import hierarchy_runtime  # noqa: E402
from genfarmer_automation.hierarchy_settle import wrap_discover_helper_port  # noqa: E402
from genfarmer_automation.runtime_diagnostics import capture_tiktok_runtime_diagnostics  # noqa: E402
from genfarmer_automation.runtime_supervisor import TikTokRuntimeSupervisor  # noqa: E402


# ``capture_hierarchy_batch`` was imported by the base demo as a function object,
# but it resolves ``discover_helper_port`` through hierarchy_runtime's module
# globals on each call. Replacing that one global therefore hardens every demo
# hierarchy capture without duplicating the orchestration or changing semantics.
if not getattr(hierarchy_runtime.discover_helper_port, "_gf_service_settle_wrapped", False):
    _settled_discover = wrap_discover_helper_port(
        hierarchy_runtime.discover_helper_port,
        hierarchy_runtime._capture_helper_once,
        hierarchy_runtime.HierarchyRuntimeError,
    )
    setattr(_settled_discover, "_gf_service_settle_wrapped", True)
    hierarchy_runtime.discover_helper_port = _settled_discover


class DiagnosticTikTokRuntimeSupervisor(TikTokRuntimeSupervisor):
    """Runtime supervisor that records private before/after restart evidence."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_device = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.device)
        self._diagnostic_dir = (
            ROOT / "evidence" / "runtime-recovery-diagnostics" / f"{safe_device}-{stamp}"
        )
        self._diagnostic_restart_index = 0

    def hard_restart(self, *, reason: str, settle_seconds: float = 1.5) -> None:
        self._diagnostic_restart_index += 1
        prefix = f"restart-{self._diagnostic_restart_index:02d}"

        before = capture_tiktok_runtime_diagnostics(
            self.device,
            self._diagnostic_dir,
            f"{prefix}-before",
        )
        print(
            "      DIAGNOSTICS BEFORE RESTART: "
            f"pid={before.pid or 'NONE'} anr={'YES' if before.anr_detected else 'NO'} "
            f"crash_hint={'YES' if before.crash_marker_detected else 'NO'}"
        )

        succeeded = False
        try:
            super().hard_restart(reason=reason, settle_seconds=settle_seconds)
            succeeded = True
        finally:
            suffix = "after" if succeeded else "after-failed"
            after = capture_tiktok_runtime_diagnostics(
                self.device,
                self._diagnostic_dir,
                f"{prefix}-{suffix}",
            )
            print(
                "      DIAGNOSTICS AFTER RESTART:  "
                f"pid={after.pid or 'NONE'} anr={'YES' if after.anr_detected else 'NO'} "
                f"foreground={after.foreground_package or 'UNKNOWN'}"
            )
            print(
                "      Private recovery evidence:  "
                f"{self._diagnostic_dir.relative_to(ROOT)}"
            )


# The base demo resolves this global when main() constructs its supervisor.
demo.TikTokRuntimeSupervisor = DiagnosticTikTokRuntimeSupervisor


if __name__ == "__main__":
    raise SystemExit(demo.main())
