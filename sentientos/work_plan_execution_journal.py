from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from sentientos.work_plan import TaskRun, WorkPlan


MAX_JOURNAL_BYTES = 1_048_576
ZERO_DIGEST = "0" * 64
_FIELDS_V1 = {"schema_version", "sequence", "plan_id", "plan_digest", "task_id",
    "event", "status", "reason", "recorded_at", "previous_digest", "digest"}
_FIELDS_V2 = _FIELDS_V1 | {"task_result"}
_TASK_RESULT_FIELDS = {"task_id", "goal_id", "kind", "status", "reason", "started_at",
    "finished_at", "duration_ms", "artifacts", "destructive"}


class WorkPlanJournalError(ValueError):
    """A work-plan execution journal is corrupt or conflicts with its plan."""


class WorkPlanExecutionJournal:
    """Append-only task start/terminal records used to prevent replay after restart."""

    def __init__(self, root: Path, plan: WorkPlan) -> None:
        self.plan_id = plan.plan_id
        self.plan_digest = hashlib.sha256(_canonical(plan.to_dict())).hexdigest()
        journal_name = hashlib.sha256(plan.plan_id.encode("utf-8")).hexdigest() + ".jsonl"
        self.path = root.resolve() / "glow/forge/work_plan_journals" / journal_name
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
        self._sequence = 0
        self._head = ZERO_DIGEST
        self._recover()

    def state(self, task_id: str) -> str | None:
        return self._states.get(task_id)

    def result(self, task_id: str) -> TaskRun | None:
        return self._results.get(task_id)

    def start(self, task_id: str) -> None:
        if task_id not in self._known_task_ids or task_id in self._states:
            raise WorkPlanJournalError("work_plan_journal_start_conflict")
        self._append(task_id, "started", None, None, None)
        self._states[task_id] = "interrupted"

    def finish(self, task_id: str, *, status: str, reason: str | None,
            result: TaskRun | None = None) -> None:
        if (self._states.get(task_id) != "interrupted"
                or status not in {"success", "failed", "skipped"}
                or (reason is not None and not isinstance(reason, str))
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
            and result.kind == task.kind and result.status in {"success", "failed", "skipped"}
            and (result.reason is None or isinstance(result.reason, str))
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
        result = TaskRun(task_id=value.get("task_id"), goal_id=value.get("goal_id"),
            kind=value.get("kind"), status=value.get("status"), reason=value.get("reason"),
            started_at=value.get("started_at"), finished_at=value.get("finished_at"),
            duration_ms=value.get("duration_ms"), artifacts=tuple(artifacts),
            destructive=value.get("destructive"))
        if not self._valid_task_result(task_id, result):
            raise WorkPlanJournalError("work_plan_journal_task_result_invalid")
        return result

    def _recover(self) -> None:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise WorkPlanJournalError("work_plan_journal_unreadable") from exc
        if len(raw) > MAX_JOURNAL_BYTES or not raw.endswith(b"\n"):
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
                    or row["schema_version"] not in {1, 2}
                    or type(row.get("sequence")) is not int or row["sequence"] != self._sequence + 1
                    or row.get("plan_id") != self.plan_id
                    or row.get("plan_digest") != self.plan_digest
                    or not isinstance(row.get("task_id"), str)
                    or row["task_id"] not in self._known_task_ids
                    or not isinstance(row.get("event"), str)
                    or row["event"] not in {"started", "finished"}
                    or not isinstance(row.get("recorded_at"), str)
                    or row.get("previous_digest") != self._head
                    or not _is_digest(row.get("digest"))):
                raise WorkPlanJournalError("work_plan_journal_record_invalid")
            semantic = {key: value for key, value in row.items() if key != "digest"}
            if row["digest"] != hashlib.sha256(_canonical(semantic)).hexdigest():
                raise WorkPlanJournalError("work_plan_journal_digest_mismatch")
            task_id = row["task_id"]
            task_result = self._decode_task_result(task_id, row.get("task_result")) \
                if row["schema_version"] == 2 else None
            if row["event"] == "started":
                if (task_id in self._states or row["status"] is not None
                        or row["reason"] is not None or task_result is not None):
                    raise WorkPlanJournalError("work_plan_journal_transition_invalid")
                self._states[task_id] = "interrupted"
            else:
                if (self._states.get(task_id) != "interrupted"
                        or not isinstance(row.get("status"), str)
                        or row["status"] not in {"success", "failed", "skipped"}
                        or (row["reason"] is not None and not isinstance(row["reason"], str))
                        or (task_result is not None and (task_result.status != row["status"]
                            or task_result.reason != row["reason"]))
                        or (row["schema_version"] == 2 and task_result is None)):
                    raise WorkPlanJournalError("work_plan_journal_transition_invalid")
                self._states[task_id] = row["status"]
                if task_result is not None:
                    self._results[task_id] = task_result
            self._sequence += 1
            self._head = row["digest"]

    def _append(self, task_id: str, event: str, status: str | None,
            reason: str | None, task_result: dict[str, Any] | None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        semantic: dict[str, Any] = {"schema_version": 2,
            "sequence": self._sequence + 1, "plan_id": self.plan_id,
            "plan_digest": self.plan_digest, "task_id": task_id,
            "event": event, "status": status, "reason": reason,
            "task_result": task_result,
            "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "previous_digest": self._head}
        row = {**semantic, "digest": hashlib.sha256(_canonical(semantic)).hexdigest()}
        encoded = _canonical(row) + b"\n"
        if self.path.exists() and self.path.stat().st_size + len(encoded) > MAX_JOURNAL_BYTES:
            raise WorkPlanJournalError("work_plan_journal_bounds_invalid")
        try:
            with self.path.open("ab") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise WorkPlanJournalError("work_plan_journal_write_failed") from exc
        self._sequence += 1
        self._head = row["digest"]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _is_digest(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value))
