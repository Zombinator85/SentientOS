from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


WORK_PLAN_DIR = Path("glow/forge/work_plans")
WORK_PLAN_PULSE_PATH = Path("pulse/work_plans.jsonl")
_PLAN_FIELDS = {"schema_version", "plan_id", "created_at", "context", "selected_goals", "tasks"}
_TASK_FIELDS = {"schema_version", "task_id", "goal_id", "kind", "commands", "callable_ref",
    "risk_cost", "throughput_cost", "preconditions", "expected_artifacts", "destructive"}


class WorkPlanError(ValueError):
    """A persisted plan is malformed or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class Task:
    schema_version: int
    task_id: str
    goal_id: str
    kind: str
    commands: tuple[str, ...]
    callable_ref: str | None
    risk_cost: int
    throughput_cost: int
    preconditions: dict[str, object]
    expected_artifacts: tuple[str, ...]
    destructive: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["commands"] = list(self.commands)
        payload["expected_artifacts"] = list(self.expected_artifacts)
        return payload


@dataclass(frozen=True, slots=True)
class WorkPlan:
    schema_version: int
    plan_id: str
    created_at: str
    context: str
    selected_goals: tuple[str, ...]
    tasks: tuple[Task, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "context": self.context,
            "selected_goals": list(self.selected_goals),
            "tasks": [task.to_dict() for task in self.tasks],
        }


@dataclass(frozen=True, slots=True)
class TaskRun:
    task_id: str
    goal_id: str
    kind: str
    status: str
    reason: str | None
    started_at: str
    finished_at: str
    duration_ms: int
    artifacts: tuple[str, ...]
    destructive: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["artifacts"] = list(self.artifacts)
        return payload


@dataclass(frozen=True, slots=True)
class WorkPlanRun:
    schema_version: int
    run_id: str
    plan_id: str
    created_at: str
    status: str
    operating_mode: str
    quarantine_active: bool
    task_runs: tuple[TaskRun, ...]
    reason_stack: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "status": self.status,
            "operating_mode": self.operating_mode,
            "quarantine_active": self.quarantine_active,
            "task_runs": [task.to_dict() for task in self.task_runs],
            "reason_stack": list(self.reason_stack),
        }



def persist_work_plan(repo_root: Path, plan: WorkPlan) -> str:
    root = repo_root.resolve()
    plan_path = root / WORK_PLAN_DIR / f"plan_{_safe_id(plan.created_at)}.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _append_jsonl(
        root / WORK_PLAN_PULSE_PATH,
        {
            "created_at": plan.created_at,
            "plan_id": plan.plan_id,
            "context": plan.context,
            "selected_goals": list(plan.selected_goals),
            "task_count": len(plan.tasks),
            "path": str(plan_path.relative_to(root)),
        },
    )
    return str(plan_path.relative_to(root))


def persist_work_run(repo_root: Path, run: WorkPlanRun) -> str:
    root = repo_root.resolve()
    run_path = root / "glow/forge/work_runs" / f"run_{_safe_id(run.created_at)}_{run.plan_id}.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(json.dumps(run.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _append_jsonl(
        root / "pulse/work_runs.jsonl",
        {
            "created_at": run.created_at,
            "run_id": run.run_id,
            "plan_id": run.plan_id,
            "status": run.status,
            "operating_mode": run.operating_mode,
            "quarantine_active": run.quarantine_active,
            "task_count": len(run.task_runs),
            "path": str(run_path.relative_to(root)),
        },
    )
    return str(run_path.relative_to(root))


def load_work_plan(path: Path) -> WorkPlan:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkPlanError("work_plan_unreadable") from exc
    if (not isinstance(payload, dict) or set(payload) != _PLAN_FIELDS
            or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1
            or any(not isinstance(payload.get(key), str) or not payload[key] or len(payload[key]) > 512
                for key in ("plan_id", "created_at", "context"))
            or not isinstance(payload.get("selected_goals"), list)
            or any(not isinstance(item, str) or not item or len(item) > 256
                for item in payload["selected_goals"])
            or len(payload["selected_goals"]) != len(set(payload["selected_goals"]))
            or not isinstance(payload.get("tasks"), list)):
        raise WorkPlanError("work_plan_shape_invalid")
    tasks = []
    task_ids: set[str] = set()
    goals = set(payload["selected_goals"])
    for row in payload["tasks"]:
        if (not isinstance(row, dict) or set(row) != _TASK_FIELDS
                or type(row.get("schema_version")) is not int or row["schema_version"] != 1
                or any(not isinstance(row.get(key), str) or not row[key] or len(row[key]) > 256
                    for key in ("task_id", "goal_id", "kind"))
                or row["goal_id"] not in goals or row["task_id"] in task_ids
                or not isinstance(row.get("commands"), list)
                or any(not isinstance(item, str) or len(item) > 4096 for item in row["commands"])
                or (row.get("callable_ref") is not None and not isinstance(row["callable_ref"], str))
                or any(type(row.get(key)) is not int or row[key] < 0
                    for key in ("risk_cost", "throughput_cost"))
                or not isinstance(row.get("preconditions"), dict)
                or ("requires_mutation" in row["preconditions"]
                    and type(row["preconditions"]["requires_mutation"]) is not bool)
                or not isinstance(row.get("expected_artifacts"), list)
                or any(not isinstance(item, str) or len(item) > 1024 for item in row["expected_artifacts"])
                or type(row.get("destructive")) is not bool):
            raise WorkPlanError("work_plan_task_invalid")
        inferred_destructive = (row["kind"] == "forge_apply"
            or row["preconditions"].get("requires_mutation") is True)
        if row["destructive"] != inferred_destructive:
            raise WorkPlanError("work_plan_destructive_classification_mismatch")
        task_ids.add(row["task_id"])
        tasks.append(Task(schema_version=row["schema_version"], task_id=row["task_id"],
            goal_id=row["goal_id"], kind=row["kind"], commands=tuple(row["commands"]),
            callable_ref=row["callable_ref"], risk_cost=row["risk_cost"],
            throughput_cost=row["throughput_cost"], preconditions=dict(row["preconditions"]),
            expected_artifacts=tuple(row["expected_artifacts"]), destructive=row["destructive"]))
    return WorkPlan(
        schema_version=payload["schema_version"],
        plan_id=payload["plan_id"],
        created_at=payload["created_at"],
        context=payload["context"],
        selected_goals=tuple(payload["selected_goals"]),
        tasks=tuple(tasks),
    )


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _safe_id(value: str) -> str:
    return value.replace(":", "-").replace(".", "-")


__all__ = [
    "Task",
    "TaskRun",
    "WorkPlan",
    "WorkPlanRun",
    "WorkPlanError",
    "load_work_plan",
    "persist_work_plan",
    "persist_work_run",
]
