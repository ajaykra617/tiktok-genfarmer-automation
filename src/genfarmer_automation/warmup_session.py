"""Deterministic planning helpers for full TikTok warm-up sessions."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
import re
from typing import Any, Mapping


class WarmupSessionError(RuntimeError):
    pass


@dataclass(frozen=True)
class WarmupSessionPlan:
    video_count: int
    watch_seconds: tuple[float, ...]
    seed: int
    max_session_seconds: float
    step_retries: int
    failure_budget: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_count": self.video_count,
            "watch_seconds": list(self.watch_seconds),
            "seed": self.seed,
            "max_session_seconds": self.max_session_seconds,
            "step_retries": self.step_retries,
            "failure_budget": self.failure_budget,
        }


def build_plan(
    *,
    video_count: int,
    watch_min_seconds: float,
    watch_max_seconds: float,
    seed: int,
    max_session_minutes: float,
    step_retries: int,
    failure_budget: int,
) -> WarmupSessionPlan:
    if not 1 <= video_count <= 500:
        raise ValueError("video_count must be 1..500")
    if watch_min_seconds < 0 or watch_max_seconds < watch_min_seconds:
        raise ValueError("invalid watch-time range")
    if max_session_minutes <= 0 or max_session_minutes > 60:
        raise ValueError("max_session_minutes must be >0 and <=60")
    if not 0 <= step_retries <= 5:
        raise ValueError("step_retries must be 0..5")
    if not 0 <= failure_budget <= 20:
        raise ValueError("failure_budget must be 0..20")

    rng = random.Random(seed)
    schedule = tuple(
        round(rng.uniform(watch_min_seconds, watch_max_seconds), 2)
        for _ in range(video_count)
    )
    return WarmupSessionPlan(
        video_count=video_count,
        watch_seconds=schedule,
        seed=seed,
        max_session_seconds=max_session_minutes * 60.0,
        step_retries=step_retries,
        failure_budget=failure_budget,
    )


_SHAREABLE_RE = re.compile(r"Shareable result:\s*(?P<path>[^\r\n]+)")


def extract_shareable_path(output: str) -> str | None:
    matches = list(_SHAREABLE_RE.finditer(output or ""))
    if not matches:
        return None
    return matches[-1].group("path").strip()


def load_shareable(root: Path, output: str) -> Mapping[str, Any] | None:
    raw = extract_shareable_path(output)
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, Mapping) else None


def step_passed(returncode: int, payload: Mapping[str, Any] | None) -> bool:
    if returncode != 0 or payload is None:
        return False
    return payload.get("status") == "PASS"


def completed_index(checkpoint: Mapping[str, Any], *, total: int) -> int:
    value = checkpoint.get("completed_steps", 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise WarmupSessionError("checkpoint completed_steps is invalid")
    if not 0 <= value <= total:
        raise WarmupSessionError("checkpoint completed_steps is outside plan")
    return value
