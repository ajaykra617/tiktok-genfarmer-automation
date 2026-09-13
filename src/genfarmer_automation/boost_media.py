"""Approved local media staging and duplicate-history helpers for TikTok Boost."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Mapping


class BoostMediaError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaSpec:
    local_path: Path
    sha256: str
    media_kind: str
    mime_type: str
    remote_name: str
    remote_path: str
    collection_uri: str


@dataclass(frozen=True)
class StagedMedia:
    spec: MediaSpec
    content_uri: str


_VIDEO_EXTENSIONS = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
}
_IMAGE_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def media_spec(path: Path) -> MediaSpec:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise BoostMediaError("approved media file does not exist")
    suffix = path.suffix.lower()
    if suffix in _VIDEO_EXTENSIONS:
        kind = "video"
        mime = _VIDEO_EXTENSIONS[suffix]
        collection = "content://media/external/video/media"
    elif suffix in _IMAGE_EXTENSIONS:
        kind = "image"
        mime = _IMAGE_EXTENSIONS[suffix]
        collection = "content://media/external/images/media"
    else:
        raise BoostMediaError("unsupported media extension; use mp4/mov/m4v/jpg/jpeg/png/webp")
    digest = sha256_file(path)
    remote_name = f"gfboost-{digest[:16]}{suffix}"
    remote_path = f"/sdcard/Download/GenFarmerBoost/{remote_name}"
    return MediaSpec(path, digest, kind, mime, remote_name, remote_path, collection)


def parse_content_query(text: str, *, display_name: str) -> str | None:
    """Return exactly one MediaStore _id for display_name from `content query` output."""
    matches: list[str] = []
    for line in (text or "").splitlines():
        if f"_display_name={display_name}" not in line:
            continue
        match = re.search(r"(?:^|\s|,)_id=(\d+)(?:,|\s|$)", line)
        if match and match.group(1) not in matches:
            matches.append(match.group(1))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise BoostMediaError("MediaStore returned multiple rows for deterministic staged filename")
    return None


class AdbMediaStager:
    def __init__(self, device: str, *, timeout: float = 60.0) -> None:
        self.device = device
        self.timeout = timeout

    def _run(self, *args: str, timeout: float | None = None) -> str:
        try:
            proc = subprocess.run(
                ["adb", "-s", self.device, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout if timeout is None else timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise BoostMediaError("adb was not found in PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise BoostMediaError("ADB media operation timed out") from exc
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", errors="replace").strip()
            raise BoostMediaError(detail or f"adb exited {proc.returncode}")
        return proc.stdout.decode("utf-8", errors="replace").strip()

    def stage(self, spec: MediaSpec) -> StagedMedia:
        self._run("shell", "mkdir", "-p", "/sdcard/Download/GenFarmerBoost", timeout=10.0)
        self._run("push", str(spec.local_path), spec.remote_path, timeout=max(self.timeout, 120.0))
        self._run(
            "shell",
            "am",
            "broadcast",
            "-a",
            "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
            "-d",
            f"file://{spec.remote_path}",
            timeout=15.0,
        )

        media_id = None
        for attempt in range(8):
            rows = self._run(
                "shell",
                "content",
                "query",
                "--uri",
                spec.collection_uri,
                "--projection",
                "_id:_display_name",
                timeout=15.0,
            )
            media_id = parse_content_query(rows, display_name=spec.remote_name)
            if media_id is not None:
                break
            if attempt < 7:
                time.sleep(0.5)
        if media_id is None:
            raise BoostMediaError("staged media did not appear in Android MediaStore")
        return StagedMedia(spec=spec, content_uri=f"{spec.collection_uri}/{media_id}")

    def launch_tiktok_share(self, staged: StagedMedia, *, package: str) -> str:
        return self._run(
            "shell",
            "am",
            "start",
            "-W",
            "-a",
            "android.intent.action.SEND",
            "-t",
            staged.spec.mime_type,
            "--eu",
            "android.intent.extra.STREAM",
            staged.content_uri,
            "--grant-read-uri-permission",
            "-p",
            package,
            timeout=30.0,
        )


def load_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "items": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoostMediaError("boost history file is unreadable") from exc
    if not isinstance(data, Mapping):
        raise BoostMediaError("boost history root must be an object")
    items = data.get("items", {})
    if not isinstance(items, Mapping):
        raise BoostMediaError("boost history items must be an object")
    return {"version": 1, "items": dict(items)}


def already_published(history: Mapping[str, Any], sha256: str) -> bool:
    items = history.get("items", {}) if isinstance(history, Mapping) else {}
    entry = items.get(sha256) if isinstance(items, Mapping) else None
    return isinstance(entry, Mapping) and entry.get("status") == "published"


def record_history(path: Path, history: dict[str, Any], *, sha256: str, entry: Mapping[str, Any]) -> None:
    items = history.setdefault("items", {})
    if not isinstance(items, dict):
        raise BoostMediaError("boost history items are not writable")
    items[sha256] = dict(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
