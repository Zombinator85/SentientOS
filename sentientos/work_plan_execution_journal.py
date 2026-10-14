from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from sentientos.work_plan import WorkPlan


MAX_JOURNAL_BYTES = 1_048_576
ZERO_DIGEST = "0" * 64
_FIELDS = {"schema_version", "sequence", "plan_id", "plan_digest", "task_id",
    "event", "status", "reason", "recorded_at", "previous_digest", "digest"}


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
        self._sequence = 0
        self._head = ZERO_DIGEST
        self._recover()

    def state(self, task_id: str) -> str | None:
        return self._states.get(task_id)

    def start(self, task_id: str) -> None:
        if task_id not in self._known_task_ids or task_id in self._states:
            raise WorkPlanJournalError("work_plan_journal_start_conflict")
        self._append(task_id, "started", None, None)
        self._states[task_id] = "interrupted"

    def finish(self, task_id: str, *, status: str, reason: str | None) -> None:
        if (self._states.get(task_id) != "interrupted"
                or status not in {"success", "failed", "skipped"}
                or (reason is not None and not isinstance(reason, str))):
            raise WorkPlanJournalError("work_plan_journal_finish_conflict")
        self._append(task_id, "finished", status, reason)
        self._states[task_id] = status

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
            if (not isinstance(row, dict) or set(row) != _FIELDS
                    or type(row.get("schema_version")) is not int or row["schema_version"] != 1
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
            if row["event"] == "started":
                if task_id in self._states or row["status"] is not None or row["reason"] is not None:
                    raise WorkPlanJournalError("work_plan_journal_transition_invalid")
                self._states[task_id] = "interrupted"
            else:
                if (self._states.get(task_id) != "interrupted"
                        or not isinstance(row.get("status"), str)
                        or row["status"] not in {"success", "failed", "skipped"}
                        or (row["reason"] is not None and not isinstance(row["reason"], str))):
                    raise WorkPlanJournalError("work_plan_journal_transition_invalid")
                self._states[task_id] = row["status"]
            self._sequence += 1
            self._head = row["digest"]

    def _append(self, task_id: str, event: str, status: str | None,
            reason: str | None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        semantic: dict[str, Any] = {"schema_version": 1,
            "sequence": self._sequence + 1, "plan_id": self.plan_id,
            "plan_digest": self.plan_digest, "task_id": task_id,
            "event": event, "status": status, "reason": reason,
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
