from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
from typing import Any

from sentientos.platform_fcntl import fcntl as posix_fcntl, require_flock
from sentientos.private_file_custody import PrivateFileCustodyError, open_private_directory
from sentientos.work_plan import TaskRun, WorkPlan


MAX_JOURNAL_BYTES = 1_048_576
ZERO_DIGEST = "0" * 64
_FIELDS_V1 = {"schema_version", "sequence", "plan_id", "plan_digest", "task_id",
    "event", "status", "reason", "recorded_at", "previous_digest", "digest"}
_FIELDS_V2 = _FIELDS_V1 | {"task_result"}
_FIELDS_V3 = _FIELDS_V2 | {"attempt"}
_TASK_RESULT_FIELDS = {"task_id", "goal_id", "kind", "status", "reason", "started_at",
    "finished_at", "duration_ms", "artifacts", "destructive"}
_RETRYABLE_TASK_KINDS = frozenset({"diagnostic", "verify"})


class WorkPlanJournalError(ValueError):
    """A work-plan execution journal is corrupt or conflicts with its plan."""


class WorkPlanExecutionJournal:
    """Append-only task start/terminal records used to prevent replay after restart."""

    def __init__(self, root: Path, plan: WorkPlan) -> None:
        self.plan_id = plan.plan_id
        self.plan_digest = plan.identity_digest()
        journal_root = root.resolve() / "glow/forge/work_plan_journals"
        journal_name = hashlib.sha256(self.plan_digest.encode("ascii")).hexdigest() + ".jsonl"
        self.path = journal_root / journal_name
        legacy_name = hashlib.sha256(plan.plan_id.encode("utf-8")).hexdigest() + ".jsonl"
        legacy_path = journal_root / legacy_name
        try:
            self.path.lstat()
            current_path_exists = True
        except FileNotFoundError:
            current_path_exists = False
        except OSError as exc:
            raise WorkPlanJournalError("work_plan_journal_unreadable") from exc
        if not current_path_exists:
            try:
                legacy_metadata = legacy_path.lstat()
            except FileNotFoundError:
                legacy_metadata = None
            except OSError as exc:
                raise WorkPlanJournalError("work_plan_journal_unreadable") from exc
            if legacy_metadata is not None:
                legacy_raw = _read_journal_path(legacy_path, legacy_metadata)
                try:
                    first_row = json.loads(legacy_raw.splitlines()[0]) if legacy_raw else None
                except (UnicodeError, json.JSONDecodeError, IndexError) as exc:
                    raise WorkPlanJournalError("work_plan_journal_unreadable") from exc
                if not isinstance(first_row, dict) or not isinstance(
                        first_row.get("plan_digest"), str):
                    raise WorkPlanJournalError("work_plan_journal_record_invalid")
                if first_row["plan_digest"] == self.plan_digest:
                    self.path = legacy_path
        self._known_task_ids = {task.task_id for task in plan.tasks}
        self._tasks = {task.task_id: task for task in plan.tasks}
        if len(self._known_task_ids) != len(plan.tasks):
            raise WorkPlanJournalError("work_plan_task_identity_duplicate")
        task_positions = {task.task_id: index for index, task in enumerate(plan.tasks)}
        for index, task in enumerate(plan.tasks):
            if (not isinstance(task.depends_on, tuple)
                    or any(not isinstance(dependency, str) for dependency in task.depends_on)
                    or len(task.depends_on) != len(set(task.depends_on))
                    or any(dependency not in task_positions
                        or task_positions[dependency] >= index for dependency in task.depends_on)):
                raise WorkPlanJournalError("work_plan_task_dependencies_invalid")
        self._states: dict[str, str] = {}
        self._results: dict[str, TaskRun] = {}
        self._attempts: dict[str, int] = {}
        self._sequence = 0
        self._head = ZERO_DIGEST
        self._file_size = 0
        self._file_digest = hashlib.sha256(b"").hexdigest()
        self._thread_lock = threading.RLock()
        self._recover()

    def state(self, task_id: str) -> str | None:
        return self._states.get(task_id)

    @property
    def head_digest(self) -> str:
        """Return the verified append-only journal head for plan evidence."""
        return self._head

    def result(self, task_id: str) -> TaskRun | None:
        return self._results.get(task_id)

    def start(self, task_id: str) -> None:
        with self._thread_lock:
            if task_id not in self._known_task_ids or task_id in self._states:
                raise WorkPlanJournalError("work_plan_journal_start_conflict")
            self._append(task_id, "started", None, None, None)
            self._states[task_id] = "interrupted"
            self._attempts[task_id] = 1

    def retry_start(self, task_id: str) -> None:
        """Record an idempotent diagnostic/verification replay after interruption."""
        with self._thread_lock:
            task = self._tasks.get(task_id)
            if (task is None or self._states.get(task_id) != "interrupted"
                    or task.kind not in _RETRYABLE_TASK_KINDS or task.destructive):
                raise WorkPlanJournalError("work_plan_journal_retry_not_allowed")
            attempt = self._attempts.get(task_id, 0) + 1
            self._append(task_id, "retry_started", None, None, None, attempt=attempt)
            self._attempts[task_id] = attempt

    def attempt_count(self, task_id: str) -> int:
        return self._attempts.get(task_id, 0)

    def finish(self, task_id: str, *, status: str, reason: str | None,
            result: TaskRun | None = None) -> None:
        with self._thread_lock:
            if (self._states.get(task_id) != "interrupted"
                    or status not in {"success", "failed", "skipped", "partial"}
                    or (reason is not None and not isinstance(reason, str))
                    or (status == "partial" and (not isinstance(reason, str) or not reason))
                    or result is None or not self._valid_task_result(task_id, result)
                    or result.status != status or result.reason != reason):
                raise WorkPlanJournalError("work_plan_journal_finish_conflict")
            self._append(task_id, "finished", status, reason,
                result.to_dict() if result is not None else None)
            self._states[task_id] = status
            if result is not None:
                self._results[task_id] = result

    def _valid_task_result(self, task_id: str, result: TaskRun) -> bool:
        task = self._tasks.get(task_id)
        return (task is not None and isinstance(result, TaskRun)
            and result.task_id == task_id and result.goal_id == task.goal_id
            and result.kind == task.kind
            and result.status in {"success", "failed", "skipped", "partial"}
            and (result.reason is None or isinstance(result.reason, str))
            and (result.status != "partial" or bool(result.reason))
            and isinstance(result.started_at, str) and bool(result.started_at)
            and isinstance(result.finished_at, str) and bool(result.finished_at)
            and type(result.duration_ms) is int and result.duration_ms >= 0
            and isinstance(result.artifacts, tuple)
            and all(isinstance(item, str) and len(item) <= 1024 for item in result.artifacts)
            and type(result.destructive) is bool
            and result.destructive == (task.destructive or task.kind == "forge_apply"))

    def _decode_task_result(self, task_id: str, value: Any) -> TaskRun | None:
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != _TASK_RESULT_FIELDS:
            raise WorkPlanJournalError("work_plan_journal_task_result_invalid")
        artifacts = value.get("artifacts")
        if not isinstance(artifacts, list) or any(not isinstance(item, str) or len(item) > 1024
                for item in artifacts):
            raise WorkPlanJournalError("work_plan_journal_task_result_invalid")
        task_result_fields = ("task_id", "goal_id", "kind", "status", "started_at", "finished_at")
        if any(not isinstance(value.get(key), str) for key in task_result_fields):
            raise WorkPlanJournalError("work_plan_journal_task_result_invalid")
        if (value.get("reason") is not None and not isinstance(value.get("reason"), str)
                or type(value.get("duration_ms")) is not int
                or type(value.get("destructive")) is not bool):
            raise WorkPlanJournalError("work_plan_journal_task_result_invalid")
        result = TaskRun(task_id=str(value["task_id"]), goal_id=str(value["goal_id"]),
            kind=str(value["kind"]), status=str(value["status"]), reason=value.get("reason"),
            started_at=str(value["started_at"]), finished_at=str(value["finished_at"]),
            duration_ms=int(value["duration_ms"]), artifacts=tuple(artifacts),
            destructive=bool(value["destructive"]))
        if not self._valid_task_result(task_id, result):
            raise WorkPlanJournalError("work_plan_journal_task_result_invalid")
        return result

    def _recover(self) -> None:
        try:
            metadata = self.path.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise WorkPlanJournalError("work_plan_journal_unreadable") from exc
        raw = _read_journal_path(self.path, metadata)
        if not raw.endswith(b"\n"):
            raise WorkPlanJournalError("work_plan_journal_bounds_invalid")
        for line in raw.splitlines():
            try:
                row = json.loads(line)
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise WorkPlanJournalError("work_plan_journal_record_invalid") from exc
            if (not isinstance(row, dict)
                    or type(row.get("schema_version")) is not int
                    or (row["schema_version"] == 1 and set(row) != _FIELDS_V1)
                    or (row["schema_version"] == 2 and set(row) != _FIELDS_V2)
                    or (row["schema_version"] == 3 and set(row) != _FIELDS_V3)
                    or row["schema_version"] not in {1, 2, 3}
                    or type(row.get("sequence")) is not int or row["sequence"] != self._sequence + 1
                    or row.get("plan_id") != self.plan_id
                    or row.get("plan_digest") != self.plan_digest
                    or not isinstance(row.get("task_id"), str)
                    or row["task_id"] not in self._known_task_ids
                    or not isinstance(row.get("event"), str)
                    or row["event"] not in {"started", "finished", "retry_started"}
                    or (row["schema_version"] == 3 and row["event"] != "retry_started")
                    or not isinstance(row.get("recorded_at"), str)
                    or row.get("previous_digest") != self._head
                    or not _is_digest(row.get("digest"))):
                raise WorkPlanJournalError("work_plan_journal_record_invalid")
            semantic = {key: value for key, value in row.items() if key != "digest"}
            if row["digest"] != hashlib.sha256(_canonical(semantic)).hexdigest():
                raise WorkPlanJournalError("work_plan_journal_digest_mismatch")
            task_id = row["task_id"]
            task_result = self._decode_task_result(task_id, row.get("task_result")) \
                if row["schema_version"] in {2, 3} else None
            if row["event"] == "started":
                if (task_id in self._states or row["status"] is not None
                        or row["reason"] is not None or task_result is not None
                        or row["schema_version"] not in {1, 2}):
                    raise WorkPlanJournalError("work_plan_journal_transition_invalid")
                self._states[task_id] = "interrupted"
                self._attempts[task_id] = 1
            elif row["event"] == "retry_started":
                attempt = row.get("attempt")
                if (row["schema_version"] != 3 or self._states.get(task_id) != "interrupted"
                        or self._tasks[task_id].kind not in _RETRYABLE_TASK_KINDS
                        or self._tasks[task_id].destructive
                        or type(attempt) is not int
                        or attempt != self._attempts.get(task_id, 0) + 1
                        or row["status"] is not None or row["reason"] is not None
                        or task_result is not None):
                    raise WorkPlanJournalError("work_plan_journal_transition_invalid")
                self._attempts[task_id] = attempt
            else:
                if (self._states.get(task_id) != "interrupted"
                        or not isinstance(row.get("status"), str)
                        or row["status"] not in {"success", "failed", "skipped", "partial"}
                        or (row["reason"] is not None and not isinstance(row["reason"], str))
                        or (row["status"] == "partial"
                            and (not isinstance(row.get("reason"), str) or not row["reason"]))
                        or (task_result is not None and (task_result.status != row["status"]
                            or task_result.reason != row["reason"]))
                        or (row["schema_version"] in {2, 3} and task_result is None)):
                    raise WorkPlanJournalError("work_plan_journal_transition_invalid")
                self._states[task_id] = row["status"]
                if task_result is not None:
                    self._results[task_id] = task_result
            self._sequence += 1
            self._head = row["digest"]
        self._file_size = len(raw)
        self._file_digest = hashlib.sha256(raw).hexdigest()

    def _append(self, task_id: str, event: str, status: str | None,
            reason: str | None, task_result: dict[str, Any] | None,
            *, attempt: int | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        schema_version = 3 if event == "retry_started" else 2
        semantic: dict[str, Any] = {"schema_version": schema_version,
            "sequence": self._sequence + 1, "plan_id": self.plan_id,
            "plan_digest": self.plan_digest, "task_id": task_id,
            "event": event, "status": status, "reason": reason,
            "task_result": task_result,
            "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "previous_digest": self._head}
        if schema_version == 3:
            semantic["attempt"] = attempt
        row = {**semantic, "digest": hashlib.sha256(_canonical(semantic)).hexdigest()}
        encoded = _canonical(row) + b"\n"
        flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        directory_fd = -1
        descriptor = -1
        try:
            try:
                require_flock()
            except OSError as exc:
                raise WorkPlanJournalError("work_plan_journal_lock_unavailable") from exc
            try:
                directory_fd = open_private_directory(self.path.parent, create=True)
            except PrivateFileCustodyError as exc:
                raise WorkPlanJournalError("work_plan_journal_directory_unavailable") from exc
            descriptor = os.open(self.path.name, flags, 0o600, dir_fd=directory_fd)
            try:
                try:
                    posix_fcntl.flock(descriptor, posix_fcntl.LOCK_EX)
                except OSError as exc:
                    raise WorkPlanJournalError("work_plan_journal_lock_unavailable") from exc
                metadata = os.fstat(descriptor)
                path_metadata = os.stat(self.path.name, dir_fd=directory_fd, follow_symlinks=False)
                if (not stat.S_ISREG(metadata.st_mode) or not stat.S_ISREG(path_metadata.st_mode)
                        or metadata.st_dev != path_metadata.st_dev
                        or metadata.st_ino != path_metadata.st_ino):
                    raise WorkPlanJournalError("work_plan_journal_bounds_invalid")
                current_bytes = _read_descriptor_bounded(descriptor)
                if (len(current_bytes) != self._file_size
                        or hashlib.sha256(current_bytes).hexdigest() != self._file_digest):
                    raise WorkPlanJournalError("work_plan_journal_stale_writer")
                if (metadata.st_size != len(current_bytes)
                        or len(current_bytes) + len(encoded) > MAX_JOURNAL_BYTES):
                    raise WorkPlanJournalError("work_plan_journal_bounds_invalid")
                view = memoryview(encoded)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError("journal append made no progress")
                    view = view[written:]
                os.fsync(descriptor)
                os.fsync(directory_fd)
            finally:
                try:
                    os.close(descriptor)
                finally:
                    descriptor = -1
        except WorkPlanJournalError:
            raise
        except OSError as exc:
            raise WorkPlanJournalError("work_plan_journal_write_failed") from exc
        finally:
            try:
                if descriptor >= 0:
                    os.close(descriptor)
            finally:
                if directory_fd >= 0:
                    os.close(directory_fd)
        self._sequence += 1
        self._head = row["digest"]
        self._file_size += len(encoded)
        self._file_digest = hashlib.sha256(current_bytes + encoded).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _read_descriptor_bounded(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = MAX_JOURNAL_BYTES + 1
    while remaining:
        chunk = os.read(descriptor, min(65_536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > MAX_JOURNAL_BYTES:
        raise WorkPlanJournalError("work_plan_journal_bounds_invalid")
    return raw


def _read_journal_path(path: Path, metadata: os.stat_result) -> bytes:
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_JOURNAL_BYTES:
        raise WorkPlanJournalError("work_plan_journal_bounds_invalid")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise WorkPlanJournalError("work_plan_journal_unreadable") from exc
    try:
        try:
            require_flock()
            posix_fcntl.flock(descriptor, posix_fcntl.LOCK_SH)
        except OSError as exc:
            raise WorkPlanJournalError("work_plan_journal_lock_unavailable") from exc
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_dev != metadata.st_dev
                or opened.st_ino != metadata.st_ino or opened.st_size > MAX_JOURNAL_BYTES):
            raise WorkPlanJournalError("work_plan_journal_bounds_invalid")
        return _read_descriptor_bounded(descriptor)
    except OSError as exc:
        raise WorkPlanJournalError("work_plan_journal_unreadable") from exc
    finally:
        os.close(descriptor)


def _is_digest(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value))
