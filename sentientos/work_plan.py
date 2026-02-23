from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


WORK_PLAN_DIR = Path("glow/forge/work_plans")
WORK_PLAN_PULSE_PATH = Path("pulse/work_plans.jsonl")


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
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = []
    for row in payload.get("tasks", []):
        if not isinstance(row, dict):
            continue
        tasks.append(
            Task(
                schema_version=int(row.get("schema_version", 1)),
                task_id=str(row.get("task_id", "")),
                goal_id=str(row.get("goal_id", "")),
                kind=str(row.get("kind", "diagnostic")),
                commands=tuple(str(item) for item in row.get("commands", []) if isinstance(item, str)),
                callable_ref=str(row.get("callable_ref")) if isinstance(row.get("callable_ref"), str) else None,
                risk_cost=max(0, int(row.get("risk_cost", 0))),
                throughput_cost=max(0, int(row.get("throughput_cost", 0))),
                preconditions={str(k): v for k, v in (row.get("preconditions") if isinstance(row.get("preconditions"), dict) else {}).items()},
                expected_artifacts=tuple(str(item) for item in row.get("expected_artifacts", []) if isinstance(item, str)),
                destructive=bool(row.get("destructive", False)),
            )
        )
    return WorkPlan(
        schema_version=int(payload.get("schema_version", 1)),
        plan_id=str(payload.get("plan_id", "")),
        created_at=str(payload.get("created_at", "")),
        context=str(payload.get("context", "manual")),
        selected_goals=tuple(str(item) for item in payload.get("selected_goals", []) if isinstance(item, str)),
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
    "load_work_plan",
    "persist_work_plan",
    "persist_work_run",
]
