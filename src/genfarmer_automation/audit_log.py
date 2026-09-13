"""Append-only automation audit log matching the client reporting contract."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditRecord:
    time: str
    account: str
    app: str
    mode: str
    action: str
    proxy: str
    result: str
    ai_text: str = ""

    @classmethod
    def now(
        cls,
        *,
        account: str,
        app: str,
        mode: str,
        action: str,
        proxy: str,
        result: str,
        ai_text: str = "",
    ) -> "AuditRecord":
        return cls(
            time=datetime.now(timezone.utc).isoformat(),
            account=account,
            app=app,
            mode=mode,
            action=action,
            proxy=proxy,
            result=result,
            ai_text=ai_text,
        )


def append_jsonl(path: Path, record: AuditRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def append_csv(path: Path, record: AuditRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    fields = ["time", "account", "app", "mode", "action", "proxy", "result", "ai_text"]
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(asdict(record))


def load_recent_jsonl(path: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows
