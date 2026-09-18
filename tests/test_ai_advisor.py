import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from genfarmer_automation.ai_advisor import (
    AdvisorAction,
    AdvisorDecision,
    FailureDomain,
    ModConRecoveryAdvisor,
    RecoveryDecisionContext,
    RecoveryPlanAction,
    build_recovery_plan,
    classify_failure_domain,
    summarize_trace_directory,
)


def context(reason: str, *, trace_available: bool = True) -> RecoveryDecisionContext:
    return RecoveryDecisionContext(
        device="192.168.4.138:5555",
        reason=reason,
        child_status="BLOCKED",
        returncode=1,
        consecutive_failures=2,
        trace_summary={
            "available": trace_available,
            "event_count": 12 if trace_available else 0,
            "adb_timeouts": 0,
            "last_fyp_state": "loading" if trace_available else None,
        },
    )


def test_failure_domain_classifies_media_without_restarting_app():
    reason = "no pending unreserved approved media is available"
    assert classify_failure_domain(reason) is FailureDomain.MEDIA_RESOURCE
    plan = build_recovery_plan(context(reason))
    assert plan.action is RecoveryPlanAction.COOLDOWN_ONLY
    assert plan.source == "deterministic"
    assert "cannot create an unreserved media item" in plan.rationale


def test_configuration_failure_stops_without_ai_or_app_recovery():
    plan = build_recovery_plan(context("demo media file does not exist"))
    assert plan.failure_domain is FailureDomain.CONFIGURATION
    assert plan.action is RecoveryPlanAction.STOP_NONRETRYABLE


def test_adb_transport_failure_does_not_force_stop_tiktok():
    plan = build_recovery_plan(context("adb transport remained unhealthy (offline)"))
    assert plan.failure_domain is FailureDomain.ADB_TRANSPORT
    assert plan.action is RecoveryPlanAction.COOLDOWN_ONLY


class FakeAdvisor:
    def __init__(self, decision: AdvisorDecision):
        self.decision = decision
        self.calls = 0

    def advise(self, _context):
        self.calls += 1
        return self.decision


def test_ai_can_choose_app_recovery_for_unknown_failure_when_trace_exists():
    advisor = FakeAdvisor(
        AdvisorDecision(
            failure_domain=FailureDomain.TIKTOK_APP,
            action=AdvisorAction.APP_RECOVERY,
            confidence=0.88,
            rationale="Runtime evidence points to TikTok rather than ADB.",
        )
    )
    plan = build_recovery_plan(context("unexpected runtime state"), advisor=advisor)
    assert advisor.calls == 1
    assert plan.action is RecoveryPlanAction.APP_RECOVERY
    assert plan.failure_domain is FailureDomain.TIKTOK_APP
    assert plan.source == "modcon"


def test_unknown_failure_without_trace_cannot_be_escalated_to_app_recovery_by_ai():
    advisor = FakeAdvisor(
        AdvisorDecision(
            failure_domain=FailureDomain.TIKTOK_APP,
            action=AdvisorAction.APP_RECOVERY,
            confidence=0.99,
            rationale="Guess.",
        )
    )
    plan = build_recovery_plan(
        context("unexpected runtime state", trace_available=False),
        advisor=advisor,
    )
    assert plan.action is RecoveryPlanAction.COOLDOWN_ONLY


def test_reboot_recommendation_never_becomes_reboot_execution():
    advisor = FakeAdvisor(
        AdvisorDecision(
            failure_domain=FailureDomain.TIKTOK_APP,
            action=AdvisorAction.RECOMMEND_REBOOT_APPROVAL,
            confidence=0.9,
            rationale="Repeated ANRs justify asking the operator.",
        )
    )
    plan = build_recovery_plan(
        context("TikTok/Android reported app-not-responding"),
        advisor=advisor,
    )
    assert plan.reboot_recommended is True
    assert plan.action is RecoveryPlanAction.APP_RECOVERY
    assert "reboot" not in plan.action.value


def test_known_app_domain_cannot_be_reclassified_as_media_by_model():
    advisor = FakeAdvisor(
        AdvisorDecision(
            failure_domain=FailureDomain.MEDIA_RESOURCE,
            action=AdvisorAction.COOLDOWN_ONLY,
            confidence=0.7,
            rationale="Incorrect model classification.",
        )
    )
    plan = build_recovery_plan(
        context("TikTok FYP remained loading after bounded settle"),
        advisor=advisor,
    )
    assert plan.failure_domain is FailureDomain.TIKTOK_APP


def test_trace_summary_is_compact_and_excludes_raw_ui_text(tmp_path):
    trace = tmp_path / "trace-device-pid1.jsonl"
    rows = [
        {
            "timestamp_utc": "2026-09-18T10:00:00+00:00",
            "pid": 1,
            "sequence": 1,
            "category": "live",
            "event": "live-hints-unclassified",
            "level": "WARNING",
            "details": {
                "classified_live_card": False,
                "fyp_state": "off_fyp",
                "text": "PRIVATE ACCOUNT NAME",
                "content_desc": "LIVE",
            },
        },
        {
            "timestamp_utc": "2026-09-18T10:00:01+00:00",
            "pid": 1,
            "sequence": 2,
            "category": "adb",
            "event": "command.timeout",
            "level": "ERROR",
            "details": {
                "mutation": True,
                "mutation_ambiguous": True,
                "transport_ready": True,
                "stdout": "PRIVATE RAW OUTPUT",
            },
        },
        {
            "timestamp_utc": "2026-09-18T10:00:02+00:00",
            "pid": 1,
            "sequence": 3,
            "category": "observer",
            "event": "observe.end",
            "level": "INFO",
            "details": {
                "interrupt": "none",
                "foreground_package": "com.zhiliaoapp.musically",
            },
        },
    ]
    trace.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    summary = summarize_trace_directory(tmp_path)
    serialized = json.dumps(summary)

    assert summary["event_count"] == 3
    assert summary["adb_timeouts"] == 1
    assert summary["mutation_timeouts"] == 1
    assert summary["unclassified_live_hint_events"] == 1
    assert summary["last_interrupt"] == "none"
    assert "PRIVATE ACCOUNT NAME" not in serialized
    assert "PRIVATE RAW OUTPUT" not in serialized


def test_modcon_response_is_strictly_validated_with_fake_openai_client():
    content = json.dumps(
        {
            "failure_domain": "ui_context",
            "action": "fresh_cycle",
            "confidence": 0.73,
            "rationale": "The hierarchy is readable but the expected search surface is absent.",
            "observations": ["ADB is healthy", "No ANR marker is present"],
            "collect_more_evidence": True,
        }
    )

    class FakeCompletions:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    advisor = ModConRecoveryAdvisor(client=client)
    decision = advisor.advise(context("search surface did not expose an enabled EditText"))

    assert decision.failure_domain is FailureDomain.UI_CONTEXT
    assert decision.action is AdvisorAction.FRESH_CYCLE
    assert decision.confidence == pytest.approx(0.73)
    assert completions.kwargs["model"] == "gpt-5.6-sol"
    sent = json.dumps(completions.kwargs["messages"])
    assert "192.168.4.138:5555" not in sent
