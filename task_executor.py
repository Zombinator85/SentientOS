from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Mapping, Sequence

from control_plane.enums import ReasonCode, RequestType
from control_plane.records import AuthorizationError, AuthorizationRecord

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
    admission_token: "AdmissionToken"
    authorization: AuthorizationRecord


class StepExecutionError(Exception):
    def __init__(self, step: Step, message: str):
        super().__init__(message)
        self.step = step


@dataclass(frozen=True)
class AdmissionToken:
    task_id: str
    provenance: "AuthorityProvenance"
    issued_by: str = "task_admission"


LOG_PATH = get_log_path("task_executor.jsonl", "TASK_EXECUTOR_LOG")


@dataclass(frozen=True)
class AuthorityProvenance:
    authority_source: str
    authority_scope: str
    authority_context_id: str
    authority_reason: str


def execute_task(
    task: Task,
    *,
    authorization: AuthorizationRecord | None = None,
    admission_token: AdmissionToken | None = None,
) -> TaskResult:
    _require_admission_token(admission_token, task)
    _require_authorization(authorization)
    assert admission_token is not None
    assert authorization is not None
    artifacts: Dict[str, Mapping[str, object]] = {}
    trace: list[StepTrace] = []
    for step in task.steps:
        step_trace = _run_step(step)
        trace.append(step_trace)
        artifacts[f"step_{step.step_id}"] = step_trace.artifacts
        _log_step(task.task_id, step_trace)
        if step_trace.status == "failed":
            return TaskResult(
                task_id=task.task_id,
                status="failed",
                artifacts=artifacts,
                trace=tuple(trace),
                admission_token=admission_token,
                authorization=authorization,
            )
    return TaskResult(
        task_id=task.task_id,
        status="completed",
        artifacts=artifacts,
        trace=tuple(trace),
        admission_token=admission_token,
        authorization=authorization,
    )


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


def _require_admission_token(token: AdmissionToken | None, task: Task) -> None:
    if token is None:
        raise AuthorizationError(ReasonCode.MISSING_AUTHORIZATION.value)
    if token.task_id != task.task_id:
        raise AuthorizationError("admission token task mismatch")
    if token.issued_by != "task_admission":
        raise AuthorizationError("admission token issuer invalid")
    if not isinstance(token.provenance, AuthorityProvenance):
        raise AuthorizationError("admission token provenance missing")
    _validate_provenance(token.provenance)


def _require_authorization(authorization: AuthorizationRecord | None) -> None:
    if authorization is None:
        raise AuthorizationError(ReasonCode.MISSING_AUTHORIZATION.value)
    authorization.require(RequestType.TASK_EXECUTION)


def _validate_provenance(provenance: AuthorityProvenance) -> None:
    for field_name, value in asdict(provenance).items():
        if not isinstance(value, str) or not value.strip():
            raise AuthorizationError(f"invalid authority provenance: {field_name}")


def canonicalise_provenance(provenance: AuthorityProvenance) -> dict[str, str]:
    _validate_provenance(provenance)
    return {
        "authority_source": provenance.authority_source,
        "authority_scope": provenance.authority_scope,
        "authority_context_id": provenance.authority_context_id,
        "authority_reason": provenance.authority_reason,
    }


def canonicalise_admission_token(token: AdmissionToken) -> dict[str, object]:
    _require_admission_token(token, Task(task_id=token.task_id, objective="", steps=()))
    return {
        "task_id": token.task_id,
        "issued_by": token.issued_by,
        "provenance": canonicalise_provenance(token.provenance),
    }


def _canonical_step_payload(step: Step) -> dict[str, object]:
    payload = step.payload
    if isinstance(payload, NoopPayload):
        return {"note": payload.note, "should_fail": payload.should_fail}
    if isinstance(payload, ShellPayload):
        return {"command": payload.command, "cwd": payload.cwd, "should_fail": payload.should_fail}
    if isinstance(payload, PythonPayload):
        return {"callable": payload.name, "has_callable": payload.callable is not None}
    if isinstance(payload, MeshPayload):
        return {"job": payload.job, "parameters": dict(payload.parameters), "should_fail": payload.should_fail}
    raise StepExecutionError(step, f"unsupported payload for canonicalization: {type(payload).__name__}")


def canonicalise_task(task: Task) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "objective": task.objective,
        "constraints": list(task.constraints),
        "steps": [
            {
                "step_id": step.step_id,
                "kind": step.kind,
                "expects": list(step.expects),
                "payload": _canonical_step_payload(step),
            }
            for step in task.steps
        ],
    }


def canonicalise_step_trace(trace: StepTrace) -> dict[str, object]:
    canonical_artifacts = {key: trace.artifacts[key] for key in sorted(trace.artifacts)}
    payload: dict[str, object] = {
        "step_id": trace.step_id,
        "kind": trace.kind,
        "status": trace.status,
        "artifacts": canonical_artifacts,
    }
    if trace.error:
        payload["error"] = trace.error
    return payload


def canonicalise_task_result(result: TaskResult) -> dict[str, object]:
    canonical_artifacts = {key: result.artifacts[key] for key in sorted(result.artifacts)}
    return {
        "task_id": result.task_id,
        "status": result.status,
        "artifacts": canonical_artifacts,
        "trace": [canonicalise_step_trace(t) for t in result.trace],
    }


def canonicalise_authorization(authorization: AuthorizationRecord) -> dict[str, object]:
    # Timestamp and metadata are non-authoritative and excluded for digest stability.
    return {
        "request_type": authorization.request_type.value,
        "requester_id": authorization.requester_id,
        "intent_hash": authorization.intent_hash,
        "context_hash": authorization.context_hash,
        "policy_version": authorization.policy_version,
        "decision": authorization.decision.value,
        "reason": authorization.reason.value,
    }


def canonicalise_task_execution_snapshot(
    *,
    task: Task,
    result: TaskResult,
    admission_token: AdmissionToken,
    authorization: AuthorizationRecord,
) -> dict[str, object]:
    if admission_token.task_id != task.task_id or result.task_id != task.task_id:
        raise SnapshotDivergenceError("task id mismatch between snapshot components")
    canonical_task = canonicalise_task(task)
    canonical_result = canonicalise_task_result(result)
    canonical_token = canonicalise_admission_token(admission_token)
    canonical_authorization = canonicalise_authorization(authorization)
    return {
        "task": canonical_task,
        "result": canonical_result,
        "admission_token": canonical_token,
        "authorization": canonical_authorization,
    }


def task_execution_snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    serialised = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def build_task_execution_record(
    *,
    task: Task,
    result: TaskResult,
    admission_token: AdmissionToken,
    authorization: AuthorizationRecord,
) -> dict[str, object]:
    canonical = canonicalise_task_execution_snapshot(
        task=task, result=result, admission_token=admission_token, authorization=authorization
    )
    digest = task_execution_snapshot_digest(canonical)
    return {"snapshot": canonical, "digest": digest}


def _extract_task_snapshot_payload(
    payload: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any], str | None]:
    if payload is None or not isinstance(payload, Mapping):
        raise SnapshotDivergenceError("task snapshot payload must be a mapping")
    if "snapshot" in payload and isinstance(payload.get("snapshot"), Mapping):
        snapshot_payload = payload["snapshot"]
        digest = payload.get("digest")
    else:
        digest = payload.get("digest")
        snapshot_payload = {key: value for key, value in payload.items() if key != "digest"}
    digest_str = str(digest) if digest else None
    return snapshot_payload, digest_str


def load_task_execution_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    snapshot_payload, stored_digest = _extract_task_snapshot_payload(payload)
    canonical = canonicalise_task_execution_snapshot_from_payload(snapshot_payload)
    if not stored_digest:
        raise SnapshotDivergenceError("task snapshot missing digest")
    computed = task_execution_snapshot_digest(canonical)
    if stored_digest != computed:
        raise SnapshotDivergenceError("task snapshot digest mismatch")
    return canonical


def canonicalise_task_execution_snapshot_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if payload is None or not isinstance(payload, Mapping):
        raise SnapshotDivergenceError("task snapshot must be a mapping")
    task_payload = payload.get("task")
    result_payload = payload.get("result")
    token_payload = payload.get("admission_token")
    auth_payload = payload.get("authorization")
    if not isinstance(task_payload, Mapping):
        raise SnapshotDivergenceError("task snapshot missing task")
    if not isinstance(result_payload, Mapping):
        raise SnapshotDivergenceError("task snapshot missing result")
    if not isinstance(token_payload, Mapping):
        raise SnapshotDivergenceError("task snapshot missing admission token")
    if not isinstance(auth_payload, Mapping):
        raise SnapshotDivergenceError("task snapshot missing authorization")

    canonical_task = {
        "task_id": str(task_payload.get("task_id", "")),
        "objective": str(task_payload.get("objective", "")),
        "constraints": list(task_payload.get("constraints", []) or []),
        "steps": [
            {
                "step_id": int(step.get("step_id")),
                "kind": step.get("kind"),
                "expects": list(step.get("expects", []) or []),
                "payload": dict(step.get("payload", {}) or {}),
            }
            for step in task_payload.get("steps", []) or []
        ],
    }
    canonical_result = {
        "task_id": str(result_payload.get("task_id", "")),
        "status": result_payload.get("status"),
        "artifacts": {str(k): v for k, v in sorted((result_payload.get("artifacts") or {}).items())},
        "trace": [
            {
                "step_id": t.get("step_id"),
                "kind": t.get("kind"),
                "status": t.get("status"),
                "artifacts": {str(k): v for k, v in sorted((t.get("artifacts") or {}).items())},
                **({"error": t["error"]} if t.get("error") else {}),
            }
            for t in result_payload.get("trace", []) or []
        ],
    }
    canonical_token = {
        "task_id": str(token_payload.get("task_id", "")),
        "issued_by": str(token_payload.get("issued_by", "")),
        "provenance": {
            "authority_source": str(token_payload.get("provenance", {}).get("authority_source", "")),
            "authority_scope": str(token_payload.get("provenance", {}).get("authority_scope", "")),
            "authority_context_id": str(token_payload.get("provenance", {}).get("authority_context_id", "")),
            "authority_reason": str(token_payload.get("provenance", {}).get("authority_reason", "")),
        },
    }
    canonical_auth = {
        "request_type": str(auth_payload.get("request_type", "")),
        "requester_id": str(auth_payload.get("requester_id", "")),
        "intent_hash": str(auth_payload.get("intent_hash", "")),
        "context_hash": str(auth_payload.get("context_hash", "")),
        "policy_version": str(auth_payload.get("policy_version", "")),
        "decision": str(auth_payload.get("decision", "")),
        "reason": str(auth_payload.get("reason", "")),
    }
    canonical = {
        "task": canonical_task,
        "result": canonical_result,
        "admission_token": canonical_token,
        "authorization": canonical_auth,
    }
    _validate_canonical_snapshot(canonical)
    return canonical


def _validate_canonical_snapshot(snapshot: Mapping[str, Any]) -> None:
    token = snapshot["admission_token"]
    prov = token.get("provenance", {})
    for field_name in ("authority_source", "authority_scope", "authority_context_id", "authority_reason"):
        if not str(prov.get(field_name, "")).strip():
            raise SnapshotDivergenceError("task snapshot provenance incomplete")
    if snapshot["task"]["task_id"] != token["task_id"] or snapshot["result"]["task_id"] != token["task_id"]:
        raise SnapshotDivergenceError("task snapshot task id mismatch")


class SnapshotDivergenceError(RuntimeError):
    """Raised when a persisted task execution snapshot cannot be trusted."""
