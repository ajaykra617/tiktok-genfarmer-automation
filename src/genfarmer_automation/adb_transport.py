"""Process-safe, self-healing ADB transport for multi-device automation.

The goal is not to pretend ADB can never fail. Network ADB, Android's adbd,
the host adb server, and individual Android shell commands can all fail
independently. This layer makes those failures bounded and observable:

- serialize our commands per physical device across Python processes;
- never kill the shared adb server from a device worker;
- retry read-only commands only after a bounded health/reconnect ladder;
- never replay a timed-out UI mutation, because it may already have executed;
- distinguish an ADB transport failure from a healthy transport carrying a
  wedged Android command (for example an input injection blocked by an ANR).

The per-device lock coordinates this repository's workers. GenFarmer itself does
not participate in that lock, so callers must still treat mutation timeouts as
ambiguous and prove postconditions before continuing.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Iterable, Iterator


class AdbFailureKind(str, Enum):
    BINARY_MISSING = "binary_missing"
    TIMEOUT = "timeout"
    DEVICE_OFFLINE = "device_offline"
    DEVICE_UNAUTHORIZED = "device_unauthorized"
    DEVICE_MISSING = "device_missing"
    COMMAND_FAILED = "command_failed"


class AdbTransportError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: AdbFailureKind,
        mutation_ambiguous: bool = False,
        transport_healthy: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.mutation_ambiguous = mutation_ambiguous
        self.transport_healthy = transport_healthy


@dataclass(frozen=True)
class AdbCommandResult:
    stdout: bytes
    stderr: bytes
    returncode: int
    elapsed_seconds: float
    attempts: int
    recovered: bool

    def stdout_text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace").strip()

    def stderr_text(self) -> str:
        return self.stderr.decode("utf-8", errors="replace").strip()


@dataclass(frozen=True)
class AdbHealth:
    ready: bool
    state: str
    shell_ok: bool
    detail: str


_TCP_SERIAL_RE = re.compile(r"^[A-Za-z0-9._-]+:\d{1,5}$")


class _RawTimeout(RuntimeError):
    pass


def _failure_kind(text: str) -> AdbFailureKind:
    lowered = (text or "").casefold()
    if "unauthorized" in lowered:
        return AdbFailureKind.DEVICE_UNAUTHORIZED
    if "offline" in lowered:
        return AdbFailureKind.DEVICE_OFFLINE
    if (
        "device not found" in lowered
        or "no devices/emulators found" in lowered
        or "cannot connect to daemon" in lowered
        or "more than one device/emulator" in lowered
    ):
        return AdbFailureKind.DEVICE_MISSING
    return AdbFailureKind.COMMAND_FAILED


class _CrossProcessLock:
    """Tiny stdlib file lock that works on Windows and POSIX."""

    def __init__(self, path: Path, *, timeout: float = 8.0, poll: float = 0.05) -> None:
        self.path = path
        self.timeout = timeout
        self.poll = poll
        self._fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.path.open("a+b")
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"0")
            fh.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fh = fh
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    fh.close()
                    raise AdbTransportError(
                        f"timed out waiting for ADB device lane lock: {self.path.name}",
                        kind=AdbFailureKind.TIMEOUT,
                    )
                time.sleep(self.poll)

    def __exit__(self, exc_type, exc, tb):
        fh = self._fh
        self._fh = None
        if fh is None:
            return
        try:
            fh.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


class AdbTransport:
    """Bounded ADB command transport with per-device recovery and isolation."""

    def __init__(
        self,
        device: str,
        *,
        adb_path: str = "adb",
        timeout: float = 12.0,
        health_timeout: float = 3.0,
        lane_timeout: float = 8.0,
        read_retries: int = 1,
        sleeper=time.sleep,
        lock_root: str | Path | None = None,
    ) -> None:
        if not isinstance(device, str) or not device.strip():
            raise ValueError("device must be a non-empty ADB serial")
        if timeout <= 0 or health_timeout <= 0 or lane_timeout <= 0:
            raise ValueError("ADB timeouts must be positive")
        if not 0 <= read_retries <= 3:
            raise ValueError("read_retries must be between 0 and 3")
        self.device = device.strip()
        self.adb_path = adb_path
        self.timeout = float(timeout)
        self.health_timeout = float(health_timeout)
        self.lane_timeout = float(lane_timeout)
        self.read_retries = int(read_retries)
        self.sleeper = sleeper
        root = Path(lock_root) if lock_root is not None else Path(tempfile.gettempdir()) / "gf-adb-lanes"
        digest = hashlib.sha256(self.device.encode("utf-8")).hexdigest()[:20]
        self._device_lock_path = root / f"device-{digest}.lock"
        self._host_lock_path = root / "host-server.lock"

    @contextmanager
    def _lane(self) -> Iterator[None]:
        with _CrossProcessLock(self._device_lock_path, timeout=self.lane_timeout):
            yield

    def _raw(
        self,
        args: Iterable[str],
        *,
        timeout: float,
        device_scoped: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        command = [self.adb_path]
        if device_scoped:
            command.extend(["-s", self.device])
        command.extend(str(item) for item in args)
        try:
            return subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AdbTransportError(
                "adb was not found in PATH",
                kind=AdbFailureKind.BINARY_MISSING,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise _RawTimeout(f"adb command timed out after {timeout:.1f}s") from exc

    def _health_unlocked(self) -> AdbHealth:
        try:
            state_proc = self._raw(["get-state"], timeout=self.health_timeout)
        except _RawTimeout:
            return AdbHealth(False, "timeout", False, "get-state timed out")
        except AdbTransportError as exc:
            return AdbHealth(False, "error", False, str(exc))

        state = state_proc.stdout.decode("utf-8", errors="replace").strip()
        if state_proc.returncode != 0 or state != "device":
            detail = state_proc.stderr.decode("utf-8", errors="replace").strip()
            return AdbHealth(False, state or "unknown", False, detail or "device is not ready")

        try:
            shell_proc = self._raw(
                ["shell", "echo", "__GF_ADB_OK__"],
                timeout=self.health_timeout,
            )
        except _RawTimeout:
            return AdbHealth(False, state, False, "shell echo timed out")
        except AdbTransportError as exc:
            return AdbHealth(False, state, False, str(exc))

        shell_text = shell_proc.stdout.decode("utf-8", errors="replace").strip()
        shell_ok = shell_proc.returncode == 0 and "__GF_ADB_OK__" in shell_text
        detail = (
            "get-state and shell channel healthy"
            if shell_ok
            else shell_proc.stderr.decode("utf-8", errors="replace").strip() or "shell probe failed"
        )
        return AdbHealth(shell_ok, state, shell_ok, detail)

    def health(self) -> AdbHealth:
        with self._lane():
            return self._health_unlocked()

    def _start_server_unlocked(self) -> None:
        # start-server is host-wide but non-destructive when the daemon is already
        # running. Serialize it so parallel workers do not race daemon startup.
        with _CrossProcessLock(self._host_lock_path, timeout=self.lane_timeout):
            try:
                proc = self._raw(
                    ["start-server"],
                    timeout=max(self.health_timeout, 5.0),
                    device_scoped=False,
                )
            except _RawTimeout:
                return
            if proc.returncode != 0:
                return

    def _recover_unlocked(self) -> AdbHealth:
        self._start_server_unlocked()
        health = self._health_unlocked()
        if health.ready:
            return health

        # Network ADB can leave a stale host transport while the phone itself is
        # reachable. Repair only this serial. Never use kill-server here because
        # that would disrupt every device in a 20-phone farm.
        if _TCP_SERIAL_RE.fullmatch(self.device):
            try:
                self._raw(
                    ["disconnect", self.device],
                    timeout=max(self.health_timeout, 4.0),
                    device_scoped=False,
                )
            except (AdbTransportError, _RawTimeout):
                pass
            try:
                self._raw(
                    ["connect", self.device],
                    timeout=max(self.health_timeout, 6.0),
                    device_scoped=False,
                )
            except (AdbTransportError, _RawTimeout):
                pass
            self.sleeper(0.35)
            health = self._health_unlocked()
        return health

    def ensure_ready(self) -> AdbHealth:
        with self._lane():
            health = self._health_unlocked()
            if health.ready:
                return health
            health = self._recover_unlocked()
            if health.ready:
                return health
            kind = _failure_kind(health.detail)
            raise AdbTransportError(
                f"ADB device transport is not ready: state={health.state}; {health.detail}",
                kind=kind,
                transport_healthy=False,
            )

    def run(
        self,
        args: Iterable[str],
        *,
        timeout: float | None = None,
        mutation: bool = False,
    ) -> AdbCommandResult:
        """Run one device-scoped ADB command.

        Read-only commands may be retried after the bounded transport recovery
        ladder. Mutations are never replayed after a timeout or non-zero result.
        """
        command_args = tuple(str(item) for item in args)
        effective_timeout = self.timeout if timeout is None else float(timeout)
        if effective_timeout <= 0:
            raise ValueError("timeout must be positive")

        with self._lane():
            attempts = 0
            recovered = False
            while True:
                attempts += 1
                started = time.monotonic()
                try:
                    proc = self._raw(command_args, timeout=effective_timeout)
                    elapsed = time.monotonic() - started
                except _RawTimeout as exc:
                    elapsed = time.monotonic() - started
                    health = self._health_unlocked()
                    if mutation:
                        status = "healthy" if health.ready else f"unhealthy ({health.state}: {health.detail})"
                        raise AdbTransportError(
                            f"adb mutation timed out after {effective_timeout:.1f}s; "
                            f"transport remained {status}; mutation outcome is ambiguous",
                            kind=AdbFailureKind.TIMEOUT,
                            mutation_ambiguous=True,
                            transport_healthy=health.ready,
                        ) from exc

                    if attempts <= self.read_retries + 1:
                        health = self._recover_unlocked()
                        recovered = True
                        if health.ready:
                            continue
                    raise AdbTransportError(
                        f"adb read-only command timed out after {effective_timeout:.1f}s; "
                        f"transport recovery did not restore a healthy channel",
                        kind=AdbFailureKind.TIMEOUT,
                        transport_healthy=health.ready,
                    ) from exc

                if proc.returncode == 0:
                    return AdbCommandResult(
                        stdout=proc.stdout,
                        stderr=proc.stderr,
                        returncode=0,
                        elapsed_seconds=elapsed,
                        attempts=attempts,
                        recovered=recovered,
                    )

                stderr = proc.stderr.decode("utf-8", errors="replace").strip()
                stdout = proc.stdout.decode("utf-8", errors="replace").strip()
                detail = stderr or stdout or f"adb exited {proc.returncode}"
                kind = _failure_kind(detail)

                if mutation:
                    health = self._health_unlocked()
                    raise AdbTransportError(
                        f"adb mutation failed: {detail}; mutation outcome is ambiguous",
                        kind=kind,
                        mutation_ambiguous=True,
                        transport_healthy=health.ready,
                    )

                if attempts <= self.read_retries + 1:
                    health = self._recover_unlocked()
                    recovered = True
                    if health.ready:
                        continue
                raise AdbTransportError(
                    detail,
                    kind=kind,
                    transport_healthy=False,
                )
