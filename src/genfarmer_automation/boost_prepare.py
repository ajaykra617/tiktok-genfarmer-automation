"""Preparation primitives for the non-publishing TikTok Boost lane.

This module deliberately stops before TikTok's Create/Upload/Post UI. It owns the
parts of Boost that are reliable and useful today: approved-media discovery,
duplicate filtering, and atomic per-media preparation leases so concurrent
devices cannot accidentally prepare the same file.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Iterable, Mapping, Any

from .boost_media import BoostMediaError, MediaSpec, already_published, media_spec


class BoostPrepareError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedMedia:
    spec: MediaSpec
    lease_path: Path | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def discover_approved_media(paths: Iterable[Path]) -> tuple[MediaSpec, ...]:
    """Return supported, existing media specs in deterministic path order.

    Directories are expanded one level only. Unsupported files are ignored;
    explicit missing paths fail closed rather than silently disappearing.
    """
    expanded: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            expanded.extend(item for item in path.iterdir() if item.is_file())
        elif path.is_file():
            expanded.append(path)
        else:
            raise BoostPrepareError(f"approved media path does not exist: {path}")

    specs: list[MediaSpec] = []
    for path in sorted(expanded, key=lambda item: str(item).casefold()):
        try:
            specs.append(media_spec(path))
        except BoostMediaError as exc:
            if "unsupported media extension" in str(exc):
                continue
            raise BoostPrepareError(str(exc)) from exc
    if not specs:
        raise BoostPrepareError("no supported approved media files were found")
    return tuple(specs)


def pending_media(
    specs: Iterable[MediaSpec],
    history: Mapping[str, Any],
) -> tuple[MediaSpec, ...]:
    """Filter hashes already recorded as successfully published."""
    return tuple(spec for spec in specs if not already_published(history, spec.sha256))


class PreparationLeaseStore:
    """Atomic local-file leases for prepared media hashes.

    `O_CREAT|O_EXCL` gives us an atomic claim on the shared orchestration host.
    Expired leases can be reclaimed. The lease contains no credentials or media
    bytes, only the hash and private orchestration labels.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def lease_path(self, sha256: str) -> Path:
        if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256.casefold()):
            raise BoostPrepareError("invalid SHA-256 for preparation lease")
        return self.root / f"{sha256.casefold()}.json"

    def _read(self, path: Path) -> Mapping[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, Mapping) else None

    @staticmethod
    def _parse_expiry(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def is_active(self, sha256: str, *, now: datetime | None = None) -> bool:
        path = self.lease_path(sha256)
        if not path.exists():
            return False
        payload = self._read(path)
        if payload is None:
            return True  # unreadable lease fails closed
        expires = self._parse_expiry(payload.get("expires_utc"))
        if expires is None:
            return True  # malformed lease fails closed
        current = (now or _utcnow()).astimezone(timezone.utc)
        return expires > current

    def reserve(
        self,
        sha256: str,
        *,
        device: str,
        account_key: str,
        ttl_seconds: float = 7200.0,
        now: datetime | None = None,
    ) -> Path | None:
        if ttl_seconds <= 0 or ttl_seconds > 86400:
            raise BoostPrepareError("lease ttl_seconds must be >0 and <=86400")
        current = (now or _utcnow()).astimezone(timezone.utc)
        path = self.lease_path(sha256)
        self.root.mkdir(parents=True, exist_ok=True)

        # Reclaim only a well-formed, definitely-expired lease.
        if path.exists():
            payload = self._read(path)
            expires = self._parse_expiry(payload.get("expires_utc")) if payload else None
            if expires is not None and expires <= current:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            else:
                return None

        payload = {
            "version": 1,
            "sha256": sha256.casefold(),
            "device": str(device),
            "account_key": str(account_key),
            "created_utc": current.isoformat(),
            "expires_utc": (current + timedelta(seconds=float(ttl_seconds))).isoformat(),
            "purpose": "boost_prepare_only",
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            return None
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except Exception:
            try:
                path.unlink()
            except OSError:
                pass
            raise
        return path

    def release(self, sha256: str, *, device: str | None = None) -> bool:
        path = self.lease_path(sha256)
        if not path.exists():
            return False
        if device is not None:
            payload = self._read(path)
            if not payload or payload.get("device") != device:
                return False
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True


def choose_and_reserve_media(
    specs: Iterable[MediaSpec],
    history: Mapping[str, Any],
    store: PreparationLeaseStore,
    *,
    device: str,
    account_key: str,
    ttl_seconds: float = 7200.0,
    now: datetime | None = None,
) -> PreparedMedia:
    """Choose the first deterministic pending hash that can be atomically leased."""
    candidates = pending_media(specs, history)
    if not candidates:
        raise BoostPrepareError("all approved media hashes are already recorded as published")
    for spec in candidates:
        lease = store.reserve(
            spec.sha256,
            device=device,
            account_key=account_key,
            ttl_seconds=ttl_seconds,
            now=now,
        )
        if lease is not None:
            return PreparedMedia(spec=spec, lease_path=lease)
    raise BoostPrepareError("all pending approved media hashes are currently reserved by other preparation jobs")
