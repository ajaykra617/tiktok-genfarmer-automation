"""Constrained AI recovery advisor for the authorized Android/TikTok worker.

The model is advisory, never an execution surface. It receives a redacted structured
summary and may recommend only a tiny allowlisted set of recovery actions.
Deterministic safety policy remains authoritative and can override the model.

No reboot, data clearing, global ADB server restart, publishing, engagement, raw
shell command, or arbitrary coordinate action is exposed to this module.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping


class FailureDomain(str, Enum):
    ADB_TRANSPORT = "adb_transport"
    ANDROID_RUNTIME = "android_runtime"
    TIKTOK_APP = "tiktok_app"
    HIERARCHY_PROVIDER = "hierarchy_provider"
    UI_CONTEXT = "ui_context"
    MEDIA_RESOURCE = "media_resource"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class AdvisorAction(str, Enum):
    APP_RECOVERY = "app_recovery"
    COOLDOWN_ONLY = "cooldown_only"
    FRESH_CYCLE = "fresh_cycle"
    RECOMMEND_REBOOT_APPROVAL = "recommend_reboot_approval"


class RecoveryPlanAction(str, Enum):
    APP_RECOVERY = "app_recovery"
    COOLDOWN_ONLY = "cooldown_only"
    FRESH_CYCLE = "fresh_cycle"
    RECOMMEND_REBOOT_APPROVAL = "recommend_reboot_approval"
    STOP_NONRETRYABLE = "stop_nonretryable"


class AdvisorError(RuntimeError):
    pass


class AdvisorConfigurationError(AdvisorError):
    pass


class AdvisorResponseError(AdvisorError):
    pass


@dataclass(frozen=True)
class AdvisorDecision:
    failure_domain: FailureDomain
    action: AdvisorAction
    confidence: float
    rationale: str
    observations: tuple[str, ...] = ()
    collect_more_evidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["failure_domain"] = self.failure_domain.value
        value["action"] = self.action.value
        value["observations"] = list(self.observations)
        return value


@dataclass(frozen=True)
class RecoveryDecisionContext:
    device: str
    reason: str
    child_status: str | None
    returncode: int
    consecutive_failures: int
    trace_summary: Mapping[str, Any]

    def redacted_payload(self) -> dict[str, Any]:
        device_hash = hashlib.sha256(self.device.encode("utf-8")).hexdigest()[:12]
        return {
            "device_id_hash": device_hash,
            "reason": self.reason[:1200],
            "child_status": self.child_status,
            "returncode": int(self.returncode),
            "consecutive_failures": int(self.consecutive_failures),
            "trace_summary": dict(self.trace_summary),
        }


@dataclass(frozen=True)
class RecoveryPlan:
    action: RecoveryPlanAction
    failure_domain: FailureDomain
    source: str
    rationale: str
    advisor_decision: AdvisorDecision | None = None
    advisor_error: str | None = None
    reboot_recommended: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "failure_domain": self.failure_domain.value,
            "source": self.source,
            "rationale": self.rationale,
            "advisor_decision": (
                self.advisor_decision.to_dict() if self.advisor_decision else None
            ),
            "advisor_error": self.advisor_error,
            "reboot_recommended": self.reboot_recommended,
        }


def classify_failure_domain(reason: str | None) -> FailureDomain:
    text = (reason or "").casefold()

    configuration_markers = (
        "media file does not exist",
        "candidate file does not contain requested candidate",
        "--dwell must be",
        "--max-app-restarts must be",
        "demo media file does not exist",
    )
    if any(marker in text for marker in configuration_markers):
        return FailureDomain.CONFIGURATION

    media_markers = (
        "no pending unreserved approved media",
        "no unreserved approved media",
        "approved media is unavailable",
        "media inventory exhausted",
        "media reservation unavailable",
    )
    if any(marker in text for marker in media_markers):
        return FailureDomain.MEDIA_RESOURCE

    adb_markers = (
        "device offline",
        "device unauthorized",
        "adb transport",
        "transport remained unhealthy",
        "adb device is missing",
        "no devices/emulators found",
    )
    if any(marker in text for marker in adb_markers):
        return FailureDomain.ADB_TRANSPORT

    android_markers = (
        "android reported app-not-responding",
        "appnotrespondingdialog",
        "android runtime",
    )
    if any(marker in text for marker in android_markers):
        return FailureDomain.ANDROID_RUNTIME

    app_markers = (
        "app-not-responding",
        "anr",
        "hard-restart budget exhausted",
        "tiktok fyp remained loading",
        "tiktok fyp remained in loading state",
    )
    if any(marker in text for marker in app_markers):
        return FailureDomain.TIKTOK_APP

    hierarchy_markers = (
        "no healthy hierarchy source",
        "hierarchy provider",
        "uiautomator",
        "helper-service",
        "helper returned invalid hierarchy",
    )
    if any(marker in text for marker in hierarchy_markers):
        return FailureDomain.HIERARCHY_PROVIDER

    ui_markers = (
        "search surface did not expose",
        "enabled edittext",
        "off-fyp",
        "off_fyp",
        "semantic node",
        "exploration failed",
    )
    if any(marker in text for marker in ui_markers):
        return FailureDomain.UI_CONTEXT

    return FailureDomain.UNKNOWN


def _safe_event_details(category: str, event: str, details: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "adb": {
            "mutation",
            "timeout_seconds",
            "elapsed_seconds",
            "attempts",
            "recovered",
            "transport_ready",
            "transport_state",
            "shell_ok",
            "mutation_ambiguous",
            "returncode",
        },
        "observer": {
            "deep",
            "adb_state",
            "foreground_package",
            "foreground_activity",
            "tiktok_foreground",
            "interrupt",
        },
        "fyp": {
            "gate_passed",
            "gate_counts",
            "fyp_state",
            "fyp_signals",
            "post_restart",
            "current_restarts",
            "check",
            "checks",
            "provider",
            "provider_attempts",
        },
        "live": {
            "classified_live_card",
            "fyp_state",
            "fyp_signals",
            "result",
            "signals",
        },
        "workflow": {
            "label",
            "video_index",
            "total_videos",
            "watch_seconds",
            "result",
            "recovered_via_checkpoint",
        },
        "recovery": {
            "label",
            "restart_number",
            "recovery_budget",
            "result",
        },
        "worker": {
            "cycle",
            "returncode",
            "timed_out",
            "child_status",
            "success",
            "process_gone",
            "stable_foreground",
            "cooldown_seconds",
            "reboot_recommended",
            "reboot_attempted",
        },
    }
    names = allowed.get(category, set())
    return {name: details[name] for name in names if name in details}


def summarize_trace_directory(trace_dir: str | Path, *, max_events: int = 80) -> dict[str, Any]:
    """Return a compact privacy-reduced summary suitable for a remote advisor."""
    path = Path(trace_dir)
    if not path.is_dir():
        return {"available": False, "event_count": 0}

    rows: list[dict[str, Any]] = []
    invalid_lines = 0
    for file in sorted(path.glob("trace-*.jsonl")):
        try:
            lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                invalid_lines += 1
                continue
            if isinstance(value, dict):
                rows.append(value)

    rows.sort(
        key=lambda row: (
            str(row.get("timestamp_utc", "")),
            int(row.get("pid", 0) or 0),
            int(row.get("sequence", 0) or 0),
        )
    )

    categories = Counter(str(row.get("category") or "unknown") for row in rows)
    levels = Counter(str(row.get("level") or "INFO").upper() for row in rows)

    adb_timeouts = 0
    mutation_timeouts = 0
    live_hints = 0
    unclassified_live_hints = 0
    last_fyp_state: str | None = None
    last_interrupt: str | None = None
    last_foreground_package: str | None = None
    last_hierarchy_provider: str | None = None

    important: list[dict[str, Any]] = []
    for row in rows:
        category = str(row.get("category") or "unknown")
        event = str(row.get("event") or "unknown")
        level = str(row.get("level") or "INFO").upper()
        details = row.get("details")
        if not isinstance(details, Mapping):
            details = {}

        if category == "adb" and "timeout" in event:
            adb_timeouts += 1
            if bool(details.get("mutation")) or bool(details.get("mutation_ambiguous")):
                mutation_timeouts += 1
        if category == "live" and event == "live-hints":
            live_hints += 1
        if category == "live" and event == "live-hints-unclassified":
            unclassified_live_hints += 1
        if category == "fyp" and isinstance(details.get("fyp_state"), str):
            last_fyp_state = str(details["fyp_state"])
        if category == "observer":
            if isinstance(details.get("interrupt"), str):
                last_interrupt = str(details["interrupt"])
            if isinstance(details.get("foreground_package"), str):
                last_foreground_package = str(details["foreground_package"])
        if category == "fyp" and isinstance(details.get("provider"), str):
            last_hierarchy_provider = str(details["provider"])

        keep = (
            level in {"ERROR", "WARNING"}
            or category in {"live", "recovery"}
            or event in {
                "command.timeout",
                "warm-scroll.swipe.result",
                "settle.exhausted",
                "cycle.result",
                "app-recovery.end",
                "client-demo.error",
            }
        )
        if keep:
            important.append(
                {
                    "timestamp_utc": row.get("timestamp_utc"),
                    "category": category,
                    "event": event,
                    "level": level,
                    "details": _safe_event_details(category, event, details),
                }
            )

    if max_events > 0:
        important = important[-max_events:]

    return {
        "available": True,
        "event_count": len(rows),
        "invalid_lines": invalid_lines,
        "categories": dict(categories),
        "levels": dict(levels),
        "adb_timeouts": adb_timeouts,
        "mutation_timeouts": mutation_timeouts,
        "live_hint_events": live_hints,
        "unclassified_live_hint_events": unclassified_live_hints,
        "last_fyp_state": last_fyp_state,
        "last_interrupt": last_interrupt,
        "last_foreground_package": last_foreground_package,
        "last_hierarchy_provider": last_hierarchy_provider,
        "important_events": important,
    }


class ModConRecoveryAdvisor:
    """OpenAI-compatible ModCon client with strict response validation."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 20.0,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("MODCON_API_KEY")
        self.base_url = base_url or os.getenv("MODCON_BASE_URL", "https://modcon.top/v1")
        self.model = model or os.getenv("MODCON_MODEL", "gpt-5.6-sol")
        self.timeout_seconds = float(timeout_seconds)
        if not self.api_key and client is None:
            raise AdvisorConfigurationError("MODCON_API_KEY is required when AI advisor is enabled")
        if not 1.0 <= self.timeout_seconds <= 60.0:
            raise AdvisorConfigurationError("AI advisor timeout must be between 1 and 60 seconds")
        self._client = client

    def _client_instance(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AdvisorConfigurationError(
                "openai package is required for ModCon advisor; install the project ai extra"
            ) from exc
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
        )
        return self._client

    @staticmethod
    def _parse_decision(content: str) -> AdvisorDecision:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AdvisorResponseError(f"advisor returned invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise AdvisorResponseError("advisor response must be a JSON object")

        try:
            domain = FailureDomain(str(payload["failure_domain"]))
            action = AdvisorAction(str(payload["action"]))
        except (KeyError, ValueError) as exc:
            raise AdvisorResponseError("advisor returned unsupported failure_domain/action") from exc

        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError) as exc:
            raise AdvisorResponseError("advisor confidence must be numeric") from exc
        confidence = max(0.0, min(1.0, confidence))

        rationale = str(payload.get("rationale") or "").strip()[:600]
        if not rationale:
            rationale = "No rationale supplied."

        raw_observations = payload.get("observations", [])
        if not isinstance(raw_observations, list):
            raw_observations = []
        observations = tuple(
            str(item).strip()[:240]
            for item in raw_observations[:6]
            if str(item).strip()
        )

        return AdvisorDecision(
            failure_domain=domain,
            action=action,
            confidence=confidence,
            rationale=rationale,
            observations=observations,
            collect_more_evidence=bool(payload.get("collect_more_evidence", False)),
        )

    def advise(self, context: RecoveryDecisionContext) -> AdvisorDecision:
        client = self._client_instance()
        system = (
            "You are a constrained recovery advisor for an authorized Android/TikTok test farm. "
            "You do not execute actions. Choose exactly one allowlisted recovery recommendation. "
            "Never recommend or describe raw shell commands, arbitrary taps/coordinates, device reboot, "
            "data/cache clearing, global ADB server restart, engagement, login bypass, or publishing. "
            "Allowed actions: app_recovery, cooldown_only, fresh_cycle, recommend_reboot_approval. "
            "Use only the supplied structured evidence. If evidence is ambiguous, prefer cooldown_only "
            "or fresh_cycle and request more evidence. Return JSON only with keys: failure_domain, action, "
            "confidence, rationale, observations, collect_more_evidence. failure_domain must be one of: "
            + ", ".join(item.value for item in FailureDomain)
            + ". rationale must be a short evidence-based justification, not hidden chain-of-thought."
        )
        user = json.dumps(context.redacted_payload(), ensure_ascii=False, separators=(",", ":"))
        try:
            # Keep the request surface deliberately small for OpenAI-compatible
            # gateways. Strict JSON is enforced by the prompt and local parser,
            # rather than relying on provider-specific response_format support.
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as exc:
            raise AdvisorError(f"ModCon advisor request failed: {exc}") from exc

        try:
            content = response.choices[0].message.content
        except Exception as exc:
            raise AdvisorResponseError("advisor response did not contain message content") from exc
        if not isinstance(content, str) or not content.strip():
            raise AdvisorResponseError("advisor returned empty content")
        return self._parse_decision(content)


def build_recovery_plan(
    context: RecoveryDecisionContext,
    *,
    advisor: ModConRecoveryAdvisor | None = None,
) -> RecoveryPlan:
    """Combine deterministic safety policy with optional AI advice."""
    domain = classify_failure_domain(context.reason)

    if domain is FailureDomain.CONFIGURATION:
        return RecoveryPlan(
            action=RecoveryPlanAction.STOP_NONRETRYABLE,
            failure_domain=domain,
            source="deterministic",
            rationale="Configuration/input failures cannot be repaired by restarting TikTok.",
        )

    if domain is FailureDomain.MEDIA_RESOURCE:
        return RecoveryPlan(
            action=RecoveryPlanAction.COOLDOWN_ONLY,
            failure_domain=domain,
            source="deterministic",
            rationale=(
                "Approved-media availability is a shared resource condition; app recovery "
                "cannot create an unreserved media item."
            ),
        )

    if domain is FailureDomain.ADB_TRANSPORT:
        return RecoveryPlan(
            action=RecoveryPlanAction.COOLDOWN_ONLY,
            failure_domain=domain,
            source="deterministic",
            rationale=(
                "ADB transport health is handled by the transport layer; force-stopping TikTok "
                "would not repair an unhealthy device transport."
            ),
        )

    deterministic_default = RecoveryPlan(
        action=(
            RecoveryPlanAction.APP_RECOVERY
            if domain in {
                FailureDomain.ANDROID_RUNTIME,
                FailureDomain.TIKTOK_APP,
                FailureDomain.HIERARCHY_PROVIDER,
                FailureDomain.UI_CONTEXT,
            }
            else RecoveryPlanAction.COOLDOWN_ONLY
        ),
        failure_domain=domain,
        source="deterministic-fallback",
        rationale=(
            "Known app/UI failure domain uses bounded app-only recovery."
            if domain is not FailureDomain.UNKNOWN
            else "Unknown failure defaults to cooldown rather than destructive recovery."
        ),
    )

    if advisor is None:
        return deterministic_default

    try:
        decision = advisor.advise(context)
    except AdvisorError as exc:
        return RecoveryPlan(
            action=deterministic_default.action,
            failure_domain=domain,
            source="advisor-error-fallback",
            rationale=deterministic_default.rationale,
            advisor_error=str(exc)[:600],
        )

    # The deterministic classifier owns hard resource/transport/config boundaries.
    # For app/UI/unknown domains, the advisor may choose only non-destructive actions.
    action = RecoveryPlanAction(decision.action.value)
    reboot_recommended = action is RecoveryPlanAction.RECOMMEND_REBOOT_APPROVAL

    # "Recommend reboot" is advisory only. Continue using the safe deterministic
    # action underneath it because reboot is outside the approved execution set.
    if reboot_recommended:
        action = deterministic_default.action

    # A model must never convert an unknown error into an aggressive recovery with
    # high confidence based on no useful trace evidence. Require some trace signal.
    if (
        domain is FailureDomain.UNKNOWN
        and action is RecoveryPlanAction.APP_RECOVERY
        and not bool(context.trace_summary.get("available"))
    ):
        action = RecoveryPlanAction.COOLDOWN_ONLY

    resolved_domain = decision.failure_domain if domain is FailureDomain.UNKNOWN else domain
    return RecoveryPlan(
        action=action,
        failure_domain=resolved_domain,
        source="modcon",
        rationale=decision.rationale,
        advisor_decision=decision,
        reboot_recommended=reboot_recommended,
    )
