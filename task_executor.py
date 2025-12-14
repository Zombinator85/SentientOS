from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Literal, Mapping, Sequence

from logging_config import get_log_path
from log_utils import append_json

StepKind = Literal["noop", "shell", "python", "mesh"]
StepStatus = Literal["completed", "failed"]
TaskStatus = Literal["completed", "failed"]


@dataclass(frozen=True)
class NoopPayload:
    note: str | None = None
    should_fail: bool = False


@dataclass(frozen=True)
class ShellPayload:
    command: str
    cwd: str | None = None
    should_fail: bool = False


@dataclass(frozen=True)
class PythonPayload:
    callable: Callable[[], Mapping[str, object]] | None = None
    name: str = "python_callable"


@dataclass(frozen=True)
class MeshPayload:
    job: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    should_fail: bool = False


StepPayload = NoopPayload | ShellPayload | PythonPayload | MeshPayload


@dataclass(frozen=True)
class Step:
    step_id: int
    kind: StepKind
    payload: StepPayload
    expects: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class StepTrace:
    step_id: int
    kind: StepKind
    status: StepStatus
    artifacts: Dict[str, object]
    error: str | None = None


@dataclass(frozen=True)
class Task:
    task_id: str
    objective: str
    constraints: Sequence[str] = field(default_factory=tuple)
    steps: Sequence[Step] = field(default_factory=tuple)


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    status: TaskStatus
    artifacts: Dict[str, Mapping[str, object]]
    trace: Sequence[StepTrace]


class StepExecutionError(Exception):
    def __init__(self, step: Step, message: str):
        super().__init__(message)
        self.step = step


LOG_PATH = get_log_path("task_executor.jsonl", "TASK_EXECUTOR_LOG")


def execute_task(task: Task) -> TaskResult:
    artifacts: Dict[str, Mapping[str, object]] = {}
    trace: list[StepTrace] = []
    for step in task.steps:
        step_trace = _run_step(step)
        trace.append(step_trace)
        artifacts[f"step_{step.step_id}"] = step_trace.artifacts
        _log_step(task.task_id, step_trace)
        if step_trace.status == "failed":
            return TaskResult(task_id=task.task_id, status="failed", artifacts=artifacts, trace=tuple(trace))
    return TaskResult(task_id=task.task_id, status="completed", artifacts=artifacts, trace=tuple(trace))


def _run_step(step: Step) -> StepTrace:
    try:
        artifacts = _dispatch_step(step)
        finalized = _apply_expects(artifacts, step.expects)
        return StepTrace(step_id=step.step_id, kind=step.kind, status="completed", artifacts=finalized)
    except Exception as exc:  # pragma: no cover - exercised via deterministic failure paths
        error = str(exc) or exc.__class__.__name__
        if not isinstance(exc, StepExecutionError):
            error = f"{step.kind} step failed: {error}"
        return StepTrace(
            step_id=step.step_id,
            kind=step.kind,
            status="failed",
            artifacts=_apply_expects({}, step.expects),
            error=error,
        )


def _dispatch_step(step: Step) -> Dict[str, object]:
    if step.kind == "noop":
        return _run_noop(step)
    if step.kind == "shell":
        return _run_shell(step)
    if step.kind == "python":
        return _run_python(step)
    if step.kind == "mesh":
        return _run_mesh(step)
    raise StepExecutionError(step, f"unsupported step kind: {step.kind}")


def _run_noop(step: Step) -> Dict[str, object]:
    payload = _require_payload(step, NoopPayload)
    if payload.should_fail:
        raise StepExecutionError(step, "noop requested failure")
    return {"note": payload.note} if payload.note else {}


def _run_shell(step: Step) -> Dict[str, object]:
    payload = _require_payload(step, ShellPayload)
    if payload.should_fail:
        raise StepExecutionError(step, "shell requested failure")
    return {"command": payload.command, "cwd": payload.cwd or ""}


def _run_python(step: Step) -> Dict[str, object]:
    payload = _require_payload(step, PythonPayload)
    if payload.callable is None:
        return {"callable": payload.name, "status": "skipped"}
    result = payload.callable()
    return dict(result)


def _run_mesh(step: Step) -> Dict[str, object]:
    payload = _require_payload(step, MeshPayload)
    if payload.should_fail:
        raise StepExecutionError(step, "mesh requested failure")
    return {"job": payload.job, "parameters": dict(payload.parameters)}


def _apply_expects(artifacts: Mapping[str, object], expects: Sequence[str]) -> Dict[str, object]:
    finalized = dict(artifacts)
    for expected in expects:
        if expected not in finalized:
            finalized[expected] = None
    return finalized


def _require_payload(step: Step, payload_type: type[StepPayload]) -> StepPayload:
    if not isinstance(step.payload, payload_type):
        raise StepExecutionError(step, f"{step.kind} payload must be {payload_type.__name__}")
    return step.payload


def _log_step(task_id: str, trace: StepTrace) -> None:
    entry = {
        "task_id": task_id,
        "step_id": trace.step_id,
        "kind": trace.kind,
        "status": trace.status,
        "artifacts": trace.artifacts,
    }
    if trace.error:
        entry["error"] = trace.error
    append_json(Path(LOG_PATH), entry)
