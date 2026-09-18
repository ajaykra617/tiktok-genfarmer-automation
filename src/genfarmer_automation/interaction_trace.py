"""Private high-resolution interaction tracing for Android/TikTok diagnostics.

Tracing is opt-in through environment variables so normal production runs stay
quiet. When enabled, every participating process writes its own JSONL stream
under one trace directory; this avoids cross-process file contention while
preserving wall-clock timestamps for later merge/sort.

Environment:
  GF_INTERACTION_TRACE_DIR       directory for private trace evidence
  GF_INTERACTION_TRACE_CONSOLE   "1" to mirror compact events to stdout
  GF_INTERACTION_TRACE_DEVICE    optional default device label/serial

Trace evidence is private diagnostic material. Callers should not copy it into
shareable result JSON because raw ADB arguments/UI text can contain account-local
context.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Mapping


_STARTED = time.monotonic()
_SEQUENCE = itertools.count(1)
_WRITE_LOCK = threading.Lock()


def _truthy(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "unknown")
    return cleaned[:120] or "unknown"


def _trace_root() -> Path | None:
    raw = os.environ.get("GF_INTERACTION_TRACE_DIR")
    if not raw:
        return None
    return Path(raw)


def enabled() -> bool:
    return _trace_root() is not None


def _default_device() -> str | None:
    value = os.environ.get("GF_INTERACTION_TRACE_DEVICE")
    return value.strip() if value and value.strip() else None


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return truncate_text(value, 800)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return str(value)


def console_safe_text(value: str, encoding: str | None = None) -> str:
    """Return text that cannot raise UnicodeEncodeError on the active console."""
    text = str(value)
    target = encoding or getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        return text.encode(target, errors="backslashreplace").decode(target, errors="strict")
    except (LookupError, UnicodeError):
        return text.encode("ascii", errors="backslashreplace").decode("ascii")


def _bytes_trace_text(value: bytes) -> str:
    """Render textual bytes, summarize binary bytes without dumping payload."""
    try:
        decoded = value.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        digest = hashlib.sha256(value).hexdigest()
        return f"<binary bytes={len(value)} sha256={digest}>"

    control_count = sum(
        1 for char in decoded
        if ord(char) < 32 and char not in "\r\n\t"
    )
    if decoded and control_count / max(1, len(decoded)) > 0.01:
        digest = hashlib.sha256(value).hexdigest()
        return f"<binary bytes={len(value)} sha256={digest}>"
    return decoded


def _trace_file(root: Path, device: str | None) -> Path:
    process = os.getpid()
    label = _safe(device or _default_device() or "host")
    return root / f"trace-{label}-pid{process}.jsonl"


def trace_event(
    event: str,
    *,
    device: str | None = None,
    category: str = "runtime",
    level: str = "INFO",
    **details: Any,
) -> int | None:
    """Append one structured trace event and optionally mirror it to stdout."""
    root = _trace_root()
    if root is None:
        return None
    root.mkdir(parents=True, exist_ok=True)
    seq = next(_SEQUENCE)
    now = datetime.now(timezone.utc)
    elapsed = time.monotonic() - _STARTED
    payload = {
        "sequence": seq,
        "timestamp_utc": now.isoformat(),
        "elapsed_seconds": round(elapsed, 6),
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
        "device": device or _default_device(),
        "category": category,
        "event": event,
        "level": level,
        "details": _jsonable(details),
    }
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path = _trace_file(root, payload["device"])
    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    if _truthy(os.environ.get("GF_INTERACTION_TRACE_CONSOLE")):
        compact = json.dumps(payload["details"], ensure_ascii=False, separators=(",", ":"))
        if len(compact) > 900:
            compact = compact[:897] + "..."
        rendered = (
            f"TRACE {seq:04d} +{elapsed:8.3f}s "
            f"[{payload['device'] or '-'}] {category}.{event} {compact}"
        )
        print(console_safe_text(rendered), flush=True)
    return seq


def trace_exception(
    event: str,
    error: BaseException,
    *,
    device: str | None = None,
    category: str = "runtime",
    **details: Any,
) -> int | None:
    return trace_event(
        event,
        device=device,
        category=category,
        level="ERROR",
        error_type=error.__class__.__name__,
        error=str(error),
        **details,
    )


def trace_text_artifact(
    label: str,
    content: str,
    *,
    device: str | None = None,
    suffix: str = ".txt",
    category: str = "artifact",
    **details: Any,
) -> str | None:
    """Write one private text artifact and emit a trace pointer to it."""
    root = _trace_root()
    if root is None:
        return None
    root.mkdir(parents=True, exist_ok=True)
    seq = next(_SEQUENCE)
    safe_label = _safe(label)
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    path = artifacts / f"{seq:04d}-{safe_label}{suffix}"
    path.write_text(content or "", encoding="utf-8", errors="replace")
    now = datetime.now(timezone.utc)
    elapsed = time.monotonic() - _STARTED
    payload = {
        "sequence": seq,
        "timestamp_utc": now.isoformat(),
        "elapsed_seconds": round(elapsed, 6),
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
        "device": device or _default_device(),
        "category": category,
        "event": "artifact",
        "level": "INFO",
        "details": {
            "label": label,
            "path": str(path),
            "bytes": len((content or "").encode("utf-8", errors="replace")),
            **_jsonable(details),
        },
    }
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    trace_path = _trace_file(root, payload["device"])
    with _WRITE_LOCK:
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    if _truthy(os.environ.get("GF_INTERACTION_TRACE_CONSOLE")):
        rendered = (
            f"TRACE {seq:04d} +{elapsed:8.3f}s "
            f"[{payload['device'] or '-'}] {category}.artifact "
            f"label={label!r} path={path}"
        )
        print(console_safe_text(rendered), flush=True)
    return str(path)


def truncate_text(value: str | bytes | None, limit: int = 800) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = _bytes_trace_text(value)
    else:
        text = str(value)
    text = text.replace("\x00", "\\0")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."
