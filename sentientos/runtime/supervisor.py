"""Canonical, local-only SentientOS lifecycle supervisor.

Lifecycle authority is limited to adapters explicitly supplied by the operator/runtime.
It does not grant inference, memory, network, host-actuation, or repository authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from ..platform_fcntl import FLOCK_SUPPORTED, fcntl as platform_fcntl
from ..windows_handle_custody import WindowsHandleCustodyError, read_explicit_file
from .services import HealthResult, ServiceAdapter

SCHEMA = "sentientos.runtime_service:v1"
STATES = frozenset({"registered", "starting", "healthy", "degraded", "unhealthy", "restarting",
                    "stopped", "failed", "disabled", "panic_stopped"})
RESTART_POLICIES = frozenset({"on_failure", "never"})
MAX_LIFECYCLE_JOURNAL_BYTES = 8 * 1024 * 1024
MAX_LIFECYCLE_RECEIPT_BYTES = 64 * 1024
MAX_LIFECYCLE_STATE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class RuntimeServiceDescriptor:
    service_id: str
    display_name: str
    service_kind: str
    dependencies: tuple[str, ...] = ()
    enabled: bool = True
    startup_posture: str = "automatic"
    startup_timeout: float = 10.0
    health_posture: str = "semantic"
    health_timeout: float = 5.0
    shutdown_posture: str = "graceful_then_force"
    shutdown_timeout: float = 10.0
    restart_policy: str = "on_failure"
    restart_budget: int = 3
    rolling_restart_window: float = 300.0
    min_backoff: float = 0.1
    max_backoff: float = 30.0
    stable_interval: float = 300.0
    critical: bool = False
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if not self.service_id or self.schema != SCHEMA: raise ValueError("invalid_service_descriptor")
        if min(self.startup_timeout, self.health_timeout, self.shutdown_timeout) <= 0: raise ValueError("timeouts_must_be_positive")
        if self.restart_budget < 0 or self.min_backoff < 0 or self.max_backoff < self.min_backoff: raise ValueError("invalid_restart_policy")
        if self.restart_policy not in RESTART_POLICIES: raise ValueError("invalid_restart_policy")


class ServiceRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[RuntimeServiceDescriptor, ServiceAdapter]] = {}

    def register(self, descriptor: RuntimeServiceDescriptor, adapter: ServiceAdapter) -> None:
        if descriptor.service_id in self._entries: raise ValueError(f"duplicate_service_id:{descriptor.service_id}")
        self._entries[descriptor.service_id] = (descriptor, adapter)

    def freeze(self) -> None:
        unknown = sorted({d for descriptor, _ in self._entries.values() for d in descriptor.dependencies if d not in self._entries})
        if unknown: raise ValueError("unknown_dependencies:" + ",".join(unknown))
        self.startup_order()

    @property
    def descriptors(self) -> Mapping[str, RuntimeServiceDescriptor]:
        return MappingProxyType({key: value[0] for key, value in sorted(self._entries.items())})

    def adapter(self, service_id: str) -> ServiceAdapter: return self._entries[service_id][1]

    def startup_order(self) -> tuple[str, ...]:
        remaining = set(self._entries); done: list[str] = []
        while remaining:
            ready = sorted(x for x in remaining if set(self._entries[x][0].dependencies) <= set(done))
            if not ready: raise ValueError("dependency_cycle")
            done.extend(ready); remaining.difference_update(ready)
        return tuple(done)

    def shutdown_order(self) -> tuple[str, ...]: return tuple(reversed(self.startup_order()))

    def digest(self) -> str:
        rows = [asdict(self._entries[key][0]) for key in sorted(self._entries)]
        return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def runtime_state_root() -> Path:
    configured = os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT")
    if configured: return Path(configured).expanduser().resolve()
    data = os.getenv("SENTIENTOS_DATA_DIR") or os.getenv("SENTIENTOS_DATA_ROOT")
    return (Path(data).expanduser().resolve() if data else (Path.cwd() / "sentientos_data").resolve()) / "runtime"


class RuntimeSupervisor:
    def __init__(self, registry: ServiceRegistry, *, state_root: Path | None = None,
                 clock: Callable[[], float] = time.time, sleeper: Callable[[float], None] = time.sleep) -> None:
        registry.freeze(); self.registry = registry; self.root = (state_root or runtime_state_root()).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._root_fd: int | None = None
        if os.name == "posix":
            if not FLOCK_SUPPORTED:
                raise OSError("runtime_supervisor_interprocess_lock_unavailable")
            directory_flag = getattr(os, "O_DIRECTORY", None)
            nofollow_flag = getattr(os, "O_NOFOLLOW", None)
            if directory_flag is None or nofollow_flag is None:
                raise OSError("runtime_supervisor_directory_custody_unavailable")
            root_fd = os.open(self.root, os.O_RDONLY | directory_flag | nofollow_flag)
            root_metadata = os.fstat(root_fd)
            if (not stat.S_ISDIR(root_metadata.st_mode)
                    or root_metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(root_metadata.st_mode) & 0o022):
                os.close(root_fd)
                raise OSError("runtime_supervisor_state_root_owner_invalid")
            self._root_fd = root_fd
        self._state_path, self._receipt_path = self.root / "supervisor-state.json", self.root / "lifecycle-receipts.jsonl"
        self._clock, self._sleep, self._lock = clock, sleeper, threading.RLock()
        self._sequence = 0; self.generation = uuid.uuid4().hex; self.panic_latched = False
        self._journal_write_failed = False
        self._states = {key: ("disabled" if not d.enabled else "registered") for key, d in registry.descriptors.items()}
        self._health: dict[str, dict[str, object]] = {}; self._restarts: dict[str, list[float]] = {k: [] for k in self._states}
        self._latest: dict[str, str] = {k: "registered" for k in self._states}; self._exhausted: set[str] = set()
        self._load()
        if not self.panic_latched:
            self._receipt("registry_snapshot", None, {"registry_digest": registry.digest()})

    def _recovery_failure(self, reason: str) -> None:
        self.panic_latched = True
        self._journal_write_failed = True
        self._states = {key: "panic_stopped" if descriptor.enabled else "disabled"
                        for key, descriptor in self.registry.descriptors.items()}
        self._latest = {key: reason for key in self._states}

    def _read_custodied_file(self, path: Path, *, max_bytes: int) -> bytes | None:
        if self._root_fd is None:
            try:
                return read_explicit_file(path, max_bytes=max_bytes)
            except WindowsHandleCustodyError as exc:
                if exc.args == ("explicit_file_missing",):
                    return None
                raise ValueError("runtime_supervisor_custody_file_unavailable") from exc
        descriptor: int | None = None
        try:
            flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW")
                | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
            descriptor = os.open(path.name, flags, dir_fd=self._root_fd)
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) & 0o022
                    or before.st_size > max_bytes):
                raise ValueError("runtime_supervisor_custody_file_invalid")
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(descriptor)
            if (len(raw) > max_bytes or len(raw) != before.st_size
                    or after.st_size != before.st_size
                    or after.st_mtime_ns != before.st_mtime_ns
                    or after.st_ctime_ns != before.st_ctime_ns
                    or after.st_dev != before.st_dev or after.st_ino != before.st_ino):
                raise ValueError("runtime_supervisor_custody_file_changed")
            return raw
        except FileNotFoundError:
            return None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _read_lifecycle_receipts(self) -> list[dict[str, object]]:
        raw = self._read_custodied_file(
            self._receipt_path, max_bytes=MAX_LIFECYCLE_JOURNAL_BYTES)
        return [] if raw is None else self._parse_lifecycle_receipts(raw)

    def _parse_lifecycle_receipts(self, raw: bytes) -> list[dict[str, object]]:
        if len(raw) > MAX_LIFECYCLE_JOURNAL_BYTES:
            raise ValueError("lifecycle_receipt_journal_size_bound_exceeded")
        if raw and not raw.endswith(b"\n"):
            raise ValueError("lifecycle_receipt_journal_partial_tail")
        rows: list[dict[str, object]] = []
        seen_generations: set[str] = set()
        current_generation: str | None = None
        for sequence, line in enumerate(raw.splitlines(), start=1):
            if not line or len(line) > MAX_LIFECYCLE_RECEIPT_BYTES:
                raise ValueError("lifecycle_receipt_row_size_or_shape_invalid")
            row = json.loads(line.decode("utf-8"))
            fields = {"schema", "sequence", "timestamp", "generation", "event", "service_id", "detail"}
            if (not isinstance(row, dict) or set(row) != fields
                    or row.get("schema") != "sentientos.runtime_lifecycle_receipt:v1"
                    or type(row.get("sequence")) is not int or row["sequence"] != sequence
                    or not isinstance(row.get("timestamp"), str)
                    or not isinstance(row.get("generation"), str) or not row["generation"]
                    or len(row["generation"]) > 128
                    or not isinstance(row.get("event"), str) or not row["event"]
                    or len(row["event"]) > 128
                    or (row.get("service_id") is not None
                        and (not isinstance(row["service_id"], str) or len(row["service_id"]) > 128))
                    or not isinstance(row.get("detail"), dict)
                    or json.dumps(row, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
                        != line + b"\n"):
                raise ValueError("lifecycle_receipt_row_invalid")
            event_time = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if event_time.tzinfo is None or event_time.utcoffset() is None:
                raise ValueError("lifecycle_receipt_timestamp_invalid")
            generation = row["generation"]
            event = row["event"]
            if event == "registry_snapshot":
                if (row.get("service_id") is not None
                        or row["detail"] != {"registry_digest": self.registry.digest()}
                        or generation == current_generation
                        or generation in seen_generations):
                    raise ValueError("lifecycle_registry_snapshot_invalid")
                current_generation = generation
                seen_generations.add(generation)
            elif current_generation is None:
                # Retain compatibility with a legacy journal whose first
                # recorded event predates explicit generation anchors.
                current_generation = generation
                seen_generations.add(generation)
            elif generation != current_generation:
                if generation in seen_generations:
                    raise ValueError("lifecycle_generation_reused")
                raise ValueError("lifecycle_generation_missing_registry_snapshot")
            rows.append(row)
        return rows

    def _load(self) -> None:
        state_sequence = 0
        state_generation: str | None = None
        try:
            raw_state = self._read_custodied_file(
                self._state_path, max_bytes=MAX_LIFECYCLE_STATE_BYTES)
        except (OSError, UnicodeError, ValueError, TypeError, KeyError,
                json.JSONDecodeError):
            self._recovery_failure("malformed_durable_state")
            return
        state_exists = raw_state is not None
        if state_exists:
            try:
                assert raw_state is not None
                if len(raw_state) > MAX_LIFECYCLE_STATE_BYTES:
                    raise ValueError("runtime_supervisor_state_size_bound_exceeded")
                payload = json.loads(raw_state.decode("utf-8"))
                expected_fields = {"schema", "registry_digest", "generation", "sequence",
                    "panic_latched", "service_states", "latest_health", "restart_histories",
                    "exhausted_services", "latest_reasons"}
                service_ids = set(self._states)
                state_map = payload.get("service_states") if isinstance(payload, dict) else None
                health_map = payload.get("latest_health") if isinstance(payload, dict) else None
                restart_map = payload.get("restart_histories") if isinstance(payload, dict) else None
                exhausted = payload.get("exhausted_services") if isinstance(payload, dict) else None
                latest_reasons = payload.get("latest_reasons") if isinstance(payload, dict) else None
                if (not isinstance(payload, dict) or set(payload) != expected_fields
                        or raw_state != (json.dumps(payload, sort_keys=True,
                            allow_nan=False) + "\n").encode("utf-8")
                        or payload.get("schema") != "sentientos.runtime_supervisor_state:v1"
                        or payload.get("registry_digest") != self.registry.digest()
                        or type(payload.get("sequence")) is not int or payload["sequence"] < 0
                        or not isinstance(payload.get("generation"), str)
                        or not payload["generation"] or len(payload["generation"]) > 128
                        or type(payload.get("panic_latched")) is not bool
                        or not isinstance(state_map, dict) or set(state_map) != service_ids
                        or any(value not in STATES for value in state_map.values())
                        or not isinstance(health_map, dict)
                        or not set(health_map) <= service_ids
                        or any(not isinstance(value, dict) for value in health_map.values())
                        or not isinstance(restart_map, dict) or set(restart_map) != service_ids
                        or not isinstance(exhausted, list)
                        or exhausted != sorted(set(exhausted))
                        or not set(exhausted) <= service_ids
                        or not isinstance(latest_reasons, dict)
                        or set(latest_reasons) != service_ids
                        or any(not isinstance(value, str) for value in latest_reasons.values())):
                    raise ValueError("runtime_supervisor_state_invalid")
                for service_id, history in restart_map.items():
                    if (not isinstance(history, list)
                            or len(history) > self.registry.descriptors[service_id].restart_budget):
                        raise ValueError("runtime_supervisor_restart_history_invalid")
                    for item in history:
                        if type(item) not in (int, float):
                            raise ValueError("runtime_supervisor_restart_history_invalid")
                        try:
                            finite = math.isfinite(float(item))
                        except (OverflowError, ValueError):
                            finite = False
                        if not finite:
                            raise ValueError("runtime_supervisor_restart_history_invalid")
                self.panic_latched = payload["panic_latched"]
                state_sequence = payload["sequence"]
                state_generation = payload["generation"]
                self._restarts = {key: [float(item) for item in restart_map[key]]
                    for key in self._states}
                self._exhausted = set(exhausted)
                self._latest.update(latest_reasons)
                if self.panic_latched:
                    self._states = {key: "panic_stopped" if descriptor.enabled else "disabled"
                        for key, descriptor in self.registry.descriptors.items()}
            except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                self._recovery_failure("malformed_durable_state")
                return
        try:
            rows = self._read_lifecycle_receipts()
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
            self._recovery_failure("malformed_lifecycle_receipt_journal")
            return
        journal_sequence = len(rows)
        if state_sequence > journal_sequence:
            self._recovery_failure("lifecycle_receipt_journal_behind_state")
            return
        if state_sequence and rows[state_sequence - 1].get("generation") != state_generation:
            self._recovery_failure("lifecycle_receipt_state_generation_mismatch")
            return
        if not state_exists and any(row.get("event") != "registry_snapshot" for row in rows):
            self._recovery_failure("lifecycle_state_missing_after_runtime_events")
            return
        if state_exists and state_sequence == 0 and any(
                row.get("event") != "registry_snapshot" for row in rows):
            self._recovery_failure("lifecycle_receipt_without_state_anchor")
            return
        self._reconcile_restart_history(rows, state_sequence)
        self._sequence = max(state_sequence, journal_sequence)

    def _reconcile_restart_history(self, rows: list[dict[str, object]],
                                   state_sequence: int) -> None:
        """Recover only journaled retry debits newer than the state snapshot.

        The snapshot sequence is the publication boundary: schedule rows at or
        below it are already represented in the snapshot; rows after it were
        durably appended before a crash and must each consume one retry slot.
        Receipt sequence, rather than timestamp deduplication, preserves two
        legitimate retries even when a coarse/injected clock gives them the
        same timestamp.
        """
        now = self._clock()
        if not math.isfinite(now):
            self._recovery_failure("restart_recovery_clock_invalid")
            return
        for row in rows:
            if row.get("event") != "restart_scheduled":
                continue
            event_sequence = row.get("sequence")
            if type(event_sequence) is not int:
                self._recovery_failure("restart_schedule_sequence_invalid")
                return
            if event_sequence <= state_sequence:
                continue
            service_id = row.get("service_id")
            if not isinstance(service_id, str) or service_id not in self.registry.descriptors:
                self._recovery_failure("restart_schedule_service_invalid")
                return
            descriptor = self.registry.descriptors[service_id]
            detail = row.get("detail")
            if not isinstance(detail, Mapping):
                self._recovery_failure("restart_schedule_detail_invalid")
                return
            scheduled_at = detail.get("restart_at")
            if scheduled_at is None:
                try:
                    event_time = datetime.fromisoformat(
                        str(row.get("timestamp")).replace("Z", "+00:00"))
                    scheduled_at = event_time.timestamp()
                except (OverflowError, OSError, ValueError):
                    self._recovery_failure("restart_schedule_timestamp_invalid")
                    return
            if type(scheduled_at) not in (int, float):
                self._recovery_failure("restart_schedule_timestamp_invalid")
                return
            try:
                scheduled_at = float(scheduled_at)
            except (OverflowError, ValueError):
                self._recovery_failure("restart_schedule_timestamp_invalid")
                return
            if not math.isfinite(scheduled_at):
                self._recovery_failure("restart_schedule_timestamp_invalid")
                return
            if now - scheduled_at > descriptor.rolling_restart_window:
                continue
            history = self._restarts.get(service_id)
            if not isinstance(history, list):
                self._recovery_failure("restart_state_history_invalid")
                return
            if any(type(value) not in (int, float) or not math.isfinite(float(value))
                   for value in history):
                self._recovery_failure("restart_state_history_invalid")
                return
            active_history = [float(value) for value in history
                              if now - float(value) <= descriptor.rolling_restart_window]
            active_history.append(scheduled_at)
            active_history.sort()
            self._restarts[service_id] = active_history

    def _atomic(self, payload: object) -> None:
        encoded = (json.dumps(payload, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        if len(encoded) > MAX_LIFECYCLE_STATE_BYTES:
            raise ValueError("runtime_supervisor_state_size_bound_exceeded")
        if self._root_fd is None:
            fd, tmp = tempfile.mkstemp(prefix=".supervisor-", dir=self.root)
            try:
                with os.fdopen(fd, "wb") as stream:
                    written = stream.write(encoded)
                    if written != len(encoded):
                        raise OSError("short_runtime_supervisor_state_write")
                    stream.flush(); os.fsync(stream.fileno())
                os.replace(tmp, self._state_path)
                directory = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            return
        temporary_name = f".supervisor-{uuid.uuid4().hex}.tmp"
        descriptor: int | None = None
        try:
            flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW") | getattr(os, "O_CLOEXEC", 0))
            descriptor = os.open(temporary_name, flags, 0o600, dir_fd=self._root_fd)
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_uid != os.geteuid()):
                raise OSError("runtime_supervisor_temp_custody_invalid")
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short_runtime_supervisor_state_write")
                view = view[written:]
            os.fsync(descriptor)
            os.replace(temporary_name, self._state_path.name,
                src_dir_fd=self._root_fd, dst_dir_fd=self._root_fd)
            os.fsync(self._root_fd)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                os.unlink(temporary_name, dir_fd=self._root_fd)
            except FileNotFoundError:
                pass
    def _persist(self) -> None:
        self._atomic({"schema": "sentientos.runtime_supervisor_state:v1", "registry_digest": self.registry.digest(),
            "generation": self.generation, "sequence": self._sequence, "panic_latched": self.panic_latched,
            "service_states": self._states, "latest_health": self._health, "restart_histories": self._restarts,
            "exhausted_services": sorted(self._exhausted), "latest_reasons": self._latest})

    def _receipt(self, event: str, service_id: str | None,
                 detail: Mapping[str, object] | None = None) -> None:
        if self._journal_write_failed:
            raise RuntimeError("lifecycle_receipt_journal_unavailable")
        sequence = self._sequence + 1
        row = {"schema": "sentientos.runtime_lifecycle_receipt:v1", "sequence": sequence,
               "timestamp": datetime.fromtimestamp(self._clock(), timezone.utc).isoformat(),
               "generation": self.generation, "event": event, "service_id": service_id,
               "detail": dict(detail or {})}
        encoded = (json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        if len(encoded) > MAX_LIFECYCLE_RECEIPT_BYTES:
            raise ValueError("lifecycle_receipt_row_size_bound_exceeded")
        if self._root_fd is None:
            try:
                current_size = self._receipt_path.stat().st_size if self._receipt_path.exists() else 0
                if current_size + len(encoded) > MAX_LIFECYCLE_JOURNAL_BYTES:
                    raise ValueError("lifecycle_receipt_journal_size_bound_exceeded")
                self._receipt_path.parent.mkdir(parents=True, exist_ok=True)
                with self._receipt_path.open("ab") as stream:
                    written = stream.write(encoded)
                    if written != len(encoded):
                        raise OSError("short_lifecycle_receipt_write")
                    stream.flush(); os.fsync(stream.fileno())
            except Exception:
                self._journal_write_failed = True
                self.panic_latched = True
                self._states = {key: "panic_stopped" if descriptor.enabled else "disabled"
                    for key, descriptor in self.registry.descriptors.items()}
                raise
        else:
            descriptor: int | None = None
            locked = False
            try:
                flags = (os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW")
                    | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
                descriptor = os.open(self._receipt_path.name, flags, 0o600, dir_fd=self._root_fd)
                metadata = os.fstat(descriptor)
                if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                        or metadata.st_uid != os.geteuid()):
                    raise OSError("lifecycle_receipt_custody_invalid")
                os.fchmod(descriptor, 0o600)
                platform_fcntl.flock(descriptor, platform_fcntl.LOCK_EX)
                locked = True
                raw = bytearray()
                os.lseek(descriptor, 0, os.SEEK_SET)
                while len(raw) <= MAX_LIFECYCLE_JOURNAL_BYTES:
                    chunk = os.read(descriptor, min(65_536, MAX_LIFECYCLE_JOURNAL_BYTES + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                rows = self._parse_lifecycle_receipts(bytes(raw))
                if len(rows) != self._sequence:
                    raise OSError("lifecycle_owner_sequence_changed")
                if event == "registry_snapshot":
                    if any(item.get("generation") == self.generation for item in rows):
                        raise OSError("lifecycle_owner_generation_reused")
                elif rows and rows[-1].get("generation") != self.generation:
                    raise OSError("lifecycle_owner_generation_superseded")
                metadata = os.fstat(descriptor)
                if metadata.st_size + len(encoded) > MAX_LIFECYCLE_JOURNAL_BYTES:
                    raise ValueError("lifecycle_receipt_journal_size_bound_exceeded")
                view = memoryview(encoded)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError("short_lifecycle_receipt_write")
                    view = view[written:]
                os.fsync(descriptor)
                os.fsync(self._root_fd)
                # Keep the interprocess journal lock through snapshot publication
                # so a concurrent supervisor cannot publish stale recovered state.
                self._sequence = sequence
                self._persist()
            except Exception:
                self._journal_write_failed = True
                self.panic_latched = True
                self._states = {key: "panic_stopped" if descriptor.enabled else "disabled"
                    for key, descriptor in self.registry.descriptors.items()}
                raise
            finally:
                if descriptor is not None:
                    if locked:
                        platform_fcntl.flock(descriptor, platform_fcntl.LOCK_UN)
                    os.close(descriptor)
        if self._root_fd is None:
            # Preserve the established non-POSIX publication behavior. POSIX
            # keeps this same state write inside the journal lock above.
            self._sequence = sequence
            self._persist()
    def _call(self, fn: Callable[[], object], timeout: float) -> object:
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(fn)
        try: return future.result(timeout=timeout)
        except FutureTimeout as exc:
            future.cancel(); raise TimeoutError("adapter_timeout") from exc
        finally: pool.shutdown(wait=False, cancel_futures=True)

    def _transition(self, service_id: str, state: str, reason: str, event: str = "health_transition") -> None:
        assert state in STATES; previous = self._states[service_id]; self._states[service_id] = state; self._latest[service_id] = reason
        self._receipt(event, service_id, {"previous_state": previous, "state": state, "reason": reason})

    def start_all(self) -> None:
        with self._lock:
            if self.panic_latched: raise RuntimeError("panic_latched")
            for service_id in self.registry.startup_order(): self._start(service_id)

    def _start(self, service_id: str, restarting: bool = False) -> None:
        descriptor = self.registry.descriptors[service_id]
        if not descriptor.enabled:
            self._states[service_id] = "disabled"
            return
        blocked = [dependency for dependency in descriptor.dependencies
                   if self._states[dependency] != "healthy"]
        if blocked:
            self._transition(service_id, "degraded",
                "dependency_blocked:" + ",".join(blocked), "dependency_degradation")
            return
        self._transition(service_id, "restarting" if restarting else "starting",
            "restart_attempt" if restarting else "start_requested",
            "restart_attempted" if restarting else "start_requested")
        try:
            adapter = self.registry.adapter(service_id)
            bind_generation = getattr(adapter, "bind_runtime_supervisor_generation", None)
            if callable(bind_generation):
                self._call(lambda: bind_generation(self.generation), descriptor.startup_timeout)
            self._call(adapter.start, descriptor.startup_timeout)
        except Exception as exc:
            try:
                self._transition(service_id, "failed",
                    f"start_failed:{type(exc).__name__}",
                    "restart_failed" if restarting else "start_failed")
            except Exception:
                # A failed start transition receipt already latches the
                # supervisor. Do not attempt another lifecycle action here.
                pass
            return
        try:
            self._receipt("restart_succeeded" if restarting else "start_succeeded",
                          service_id)
        except Exception:
            # The child may already be running. Missing success custody must not
            # be rewritten as a failed start or trigger an automatic duplicate.
            self.panic_latched = True
            self._states[service_id] = "degraded"
            self._latest[service_id] = "start_succeeded_receipt_uncertain"
            return
        self._observe(service_id, restart_on_failure=False)

    def _observe(self, service_id: str, *, restart_on_failure: bool = True) -> None:
        descriptor = self.registry.descriptors[service_id]
        dependencies = {d: self._states[d] for d in descriptor.dependencies}
        blocked = [d for d, state in dependencies.items() if state != "healthy"]
        if blocked:
            if self._states[service_id] != "degraded": self._transition(service_id, "degraded", "dependency_blocked:" + ",".join(blocked), "dependency_degradation")
            return
        if self._states[service_id] == "degraded" and self._latest[service_id].startswith("dependency_blocked"):
            self._receipt("dependency_recovery", service_id, {"dependencies": dependencies})
        started = time.monotonic()
        try:
            adapter = self.registry.adapter(service_id)
            result = self._call(adapter.health, descriptor.health_timeout)
            if not isinstance(result, HealthResult): raise TypeError("invalid_health_result")
        except Exception as exc: result = HealthResult(False, f"health_failed:{type(exc).__name__}")
        latency = time.monotonic() - started
        self._health[service_id] = {"sequence": self._sequence + 1, "timestamp": self._clock(), "latency_seconds": latency,
                                    "ready": result.ready, "reason": result.reason, "dependency_state": dependencies,
                                    "metadata": dict(result.metadata or {})}
        if result.ready:
            self._transition(service_id, "healthy", result.reason)
        else:
            self._transition(service_id, "unhealthy", result.reason)
            if restart_on_failure: self._restart(service_id)

    def observe(self) -> None:
        with self._lock:
            if self.panic_latched: return
            for service_id in self.registry.startup_order():
                if self.registry.descriptors[service_id].enabled and self._states[service_id] not in {"failed", "disabled", "panic_stopped"}:
                    self._observe(service_id)

    def _observe_explicit_recovery(self, service_id: str) -> str:
        """Observe one externally admitted recovery without invoking auto-restart."""
        with self._lock:
            if self.panic_latched:
                raise RuntimeError("panic_latched")
            if service_id not in self.registry.descriptors:
                raise ValueError("unknown_service")
            self._observe(service_id, restart_on_failure=False)
            return self._states[service_id]

    def _restart(self, service_id: str) -> None:
        d = self.registry.descriptors[service_id]
        if self.panic_latched or d.restart_policy != "on_failure" or service_id in self._exhausted: return
        now = self._clock()
        history = [value for value in self._restarts[service_id]
                   if now - value <= d.rolling_restart_window]
        self._restarts[service_id] = history
        if len(history) >= d.restart_budget:
            self._exhausted.add(service_id)
            self._transition(service_id, "failed", "restart_budget_exhausted",
                "restart_budget_exhausted")
            return
        delay = min(d.max_backoff, d.min_backoff * (2 ** len(history)))
        scheduled_at = self._clock()
        history.append(scheduled_at)
        self._restarts[service_id] = history
        self._receipt("restart_scheduled", service_id, {
            "backoff_seconds": delay, "used": len(history) - 1,
            "budget": d.restart_budget, "restart_at": scheduled_at})
        self._sleep(delay)
        try:
            self._call(self.registry.adapter(service_id).force_stop, d.shutdown_timeout)
        except Exception as exc:
            self._exhausted.add(service_id)
            try:
                self._transition(service_id, "failed",
                    f"restart_force_stop_failed:{type(exc).__name__}",
                    "restart_force_stop_failed")
            except Exception:
                self.panic_latched = True
                self._states[service_id] = "failed"
                self._latest[service_id] = "restart_force_stop_failed_receipt_uncertain"
            return
        try:
            self._receipt("restart_force_stop_completed", service_id, {
                "backoff_seconds": delay, "used": len(history),
                "budget": d.restart_budget})
        except Exception:
            # The predecessor may already be stopped. Never launch a successor
            # if its stop outcome cannot be durably reconciled.
            self.panic_latched = True
            self._states[service_id] = "degraded"
            self._latest[service_id] = "restart_force_stop_receipt_uncertain"
            return
        self._start(service_id, restarting=True)

    def reset_restart_budget(self, service_id: str) -> None:
        with self._lock:
            self._restarts[service_id] = []; self._exhausted.discard(service_id)
            self._states[service_id] = "registered"; self._transition(service_id, "registered", "operator_budget_reset", "restart_budget_reset")

    def shutdown(self, *, panic: bool = False) -> None:
        with self._lock:
            if panic:
                self.panic_latched = True
            for service_id in self.registry.shutdown_order():
                if self._states[service_id] in {"disabled", "stopped", "panic_stopped"}:
                    continue
                descriptor = self.registry.descriptors[service_id]
                adapter = self.registry.adapter(service_id)
                previous = self._states[service_id]
                try:
                    self._receipt("panic_stop" if panic else "graceful_stop_requested",
                                  service_id)
                    request_posture = "recorded"
                except Exception:
                    # Journal failure must not prevent an already authorized
                    # shutdown from stopping its child.
                    request_posture = "unavailable"
                    self.panic_latched = True
                try:
                    self._call(adapter.stop, descriptor.shutdown_timeout)
                    state = "panic_stopped" if panic else "stopped"
                    reason = "panic_latched" if panic else "graceful_stop_completed"
                    event = "panic_stop" if panic else "graceful_stop_completed"
                except Exception:
                    try:
                        self._call(adapter.force_stop, descriptor.shutdown_timeout)
                        state, reason, event = (
                            "panic_stopped" if panic else "stopped",
                            "forced_terminal_stop", "forced_terminal_stop")
                    except Exception:
                        state, reason, event = (
                            "failed", "forced_terminal_stop_failed",
                            "forced_terminal_stop_failed")
                        self.panic_latched = True
                self._states[service_id] = state
                self._latest[service_id] = reason
                try:
                    self._receipt(event, service_id, {
                        "previous_state": previous, "state": state, "reason": reason,
                        "stop_request_receipt_posture": request_posture})
                except Exception:
                    # The stop result is already known. Keep that in-memory
                    # result separate from missing durable receipt custody and
                    # never retry the stop merely because publication failed.
                    self.panic_latched = True
                    self._latest[service_id] = reason + "_receipt_uncertain"

    def panic_stop(self) -> None: self.shutdown(panic=True)

    def clear_panic(self) -> None:
        with self._lock:
            if not self.panic_latched: return
            self.panic_latched = False
            for key, descriptor in self.registry.descriptors.items(): self._states[key] = "registered" if descriptor.enabled else "disabled"
            self._receipt("panic_clear", None, {"operator_action_required": True})

    def status(self) -> Mapping[str, object]:
        with self._lock:
            services = {key: {"descriptor": asdict(d), "state": self._states[key],
                              "dependency_state": {x: self._states[x] for x in d.dependencies},
                              "restart_count": len(self._restarts[key]), "restart_budget": d.restart_budget,
                              "restart_budget_exhausted": key in self._exhausted, "latest_health": self._health.get(key),
                              "latest_reason": self._latest[key]} for key, d in self.registry.descriptors.items()}
            return {"schema": "sentientos.runtime_supervisor_status:v1", "generation": self.generation,
                    "state": "panic" if self.panic_latched else "running", "panic_latched": self.panic_latched,
                    "registry_digest": self.registry.digest(), "services": services}
