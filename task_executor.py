from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Mapping, MutableMapping, Sequence

from control_plane.enums import ReasonCode, RequestType
from control_plane.records import AuthorizationError, AuthorizationRecord
from sentientos.gradient_contract import GradientInvariantViolation, enforce_no_gradient_fields

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
    request_fingerprint: "RequestFingerprint"
    canonical_request: Mapping[str, object]


class StepExecutionError(Exception):
    def __init__(self, step: Step, message: str):
        super().__init__(message)
        self.step = step


class RequestCanonicalizationError(RuntimeError):
    """Raised when a task request cannot be normalized into canonical form."""


class RequestFingerprintMismatchError(RuntimeError):
    """Raised when the request fingerprint at execution time diverges from admission."""


@dataclass(frozen=True)
class RequestFingerprint:
    value: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass(frozen=True)
class AdmissionToken:
    task_id: str
    provenance: "AuthorityProvenance"
    request_fingerprint: RequestFingerprint
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
    declared_inputs: Mapping[str, object] | None = None,
) -> TaskResult:
    _require_admission_token(admission_token, task)
    _require_authorization(authorization)
    assert admission_token is not None
    assert authorization is not None
    canonical_request = canonicalise_task_request(
        task=task,
        authorization=authorization,
        provenance=admission_token.provenance,
        declared_inputs=declared_inputs,
    )
    computed_fingerprint = request_fingerprint_from_canonical(canonical_request)
    if admission_token.request_fingerprint.value != computed_fingerprint.value:
        raise RequestFingerprintMismatchError(
            "request fingerprint mismatch between admission token and execution request"
        )
    artifacts: Dict[str, Mapping[str, object]] = {}
    trace: list[StepTrace] = []
    for step in task.steps:
        step_trace = _run_step(step)
        trace.append(step_trace)
        artifacts[f"step_{step.step_id}"] = step_trace.artifacts
        _log_step(task.task_id, step_trace)
        if step_trace.status == "failed":
            _log_task_result(task.task_id, "failed", step_trace.error)
            return TaskResult(
                task_id=task.task_id,
                status="failed",
                artifacts=artifacts,
                trace=tuple(trace),
                admission_token=admission_token,
                authorization=authorization,
                request_fingerprint=computed_fingerprint,
                canonical_request=canonical_request,
            )
    _log_task_result(task.task_id, "completed", None)
    return TaskResult(
        task_id=task.task_id,
        status="completed",
        artifacts=artifacts,
        trace=tuple(trace),
        admission_token=admission_token,
        authorization=authorization,
        request_fingerprint=computed_fingerprint,
        canonical_request=canonical_request,
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


def _log_task_result(task_id: str, status: TaskStatus, error: str | None) -> None:
    entry = {
        "task_id": task_id,
        "event": "task_result",
        "status": status,
    }
    if error:
        entry["error"] = error
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
    fingerprint = token.request_fingerprint.value if isinstance(token.request_fingerprint, RequestFingerprint) else ""
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise AuthorizationError("admission token fingerprint missing")
    try:
        int(fingerprint, 16)
    except ValueError as exc:  # pragma: no cover - defensive validation
        raise AuthorizationError("admission token fingerprint missing") from exc
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
        "request_fingerprint": token.request_fingerprint.value,
    }


def _canonical_step_payload(step: Step) -> dict[str, object]:
    payload = step.payload
    if isinstance(payload, NoopPayload):
        return {"note": _normalise_text(payload.note), "should_fail": payload.should_fail}
    if isinstance(payload, ShellPayload):
        return {"command": payload.command, "cwd": payload.cwd, "should_fail": payload.should_fail}
    if isinstance(payload, PythonPayload):
        return {"callable": _normalise_text(payload.name), "has_callable": payload.callable is not None}
    if isinstance(payload, MeshPayload):
        return {
            "job": _normalise_text(payload.job),
            "parameters": _canonicalise_mapping(payload.parameters),
            "should_fail": payload.should_fail,
        }
    raise StepExecutionError(step, f"unsupported payload for canonicalization: {type(payload).__name__}")


def canonicalise_task(task: Task) -> dict[str, object]:
    return {
        "task_id": task.task_id.strip(),
        "objective": _normalise_text(task.objective),
        "constraints": sorted(_normalise_text(c) for c in task.constraints),
        "steps": [
            {
                "step_id": step.step_id,
                "kind": step.kind,
                "expects": sorted(_normalise_text(e) for e in step.expects),
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
        "request_fingerprint": result.request_fingerprint.value,
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
    declared_inputs: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if admission_token.task_id != task.task_id or result.task_id != task.task_id:
        raise SnapshotDivergenceError("task id mismatch between snapshot components")
    canonical_request = canonicalise_task_request(
        task=task,
        authorization=authorization,
        provenance=admission_token.provenance,
        declared_inputs=declared_inputs or result.canonical_request.get("declared_inputs"),
    )
    fingerprint = request_fingerprint_from_canonical(canonical_request)
    if fingerprint.value != admission_token.request_fingerprint.value or fingerprint.value != result.request_fingerprint.value:
        raise SnapshotDivergenceError("task snapshot request fingerprint mismatch")
    canonical_task = canonical_request["task"]
    canonical_result = canonicalise_task_result(result)
    canonical_token = canonicalise_admission_token(admission_token)
    canonical_authorization = canonical_request["authorization"]
    return {
        "request": canonical_request,
        "request_fingerprint": fingerprint.value,
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
    if result.status != "completed":
        raise SnapshotDivergenceError("task execution did not complete; refusing snapshot")
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
    request_payload = payload.get("request")
    task_payload = payload.get("task")
    result_payload = payload.get("result")
    token_payload = payload.get("admission_token")
    auth_payload = payload.get("authorization")
    fingerprint_payload = payload.get("request_fingerprint")
    if not isinstance(request_payload, Mapping):
        raise SnapshotDivergenceError("task snapshot missing request")
    if not isinstance(task_payload, Mapping):
        raise SnapshotDivergenceError("task snapshot missing task")
    if not isinstance(result_payload, Mapping):
        raise SnapshotDivergenceError("task snapshot missing result")
    if not isinstance(token_payload, Mapping):
        raise SnapshotDivergenceError("task snapshot missing admission token")
    if not isinstance(auth_payload, Mapping):
        raise SnapshotDivergenceError("task snapshot missing authorization")

    canonical_task = _canonicalise_task_payload(task_payload)
    canonical_result = _canonicalise_result_payload(result_payload)
    canonical_token = _canonicalise_token_payload(token_payload)
    canonical_auth = _canonicalise_authorization_payload(auth_payload)
    canonical_request = canonicalise_task_request_from_payload(request_payload)
    if canonical_request.get("task") != canonical_task:
        raise SnapshotDivergenceError("task snapshot request task does not match task payload")
    if canonical_request.get("authorization") != canonical_auth:
        raise SnapshotDivergenceError("task snapshot request authorization mismatch")
    if canonical_request.get("provenance") != canonical_token.get("provenance"):
        raise SnapshotDivergenceError("task snapshot request provenance mismatch")
    request_fingerprint = request_fingerprint_from_canonical(canonical_request).value
    if fingerprint_payload is not None and str(fingerprint_payload) != request_fingerprint:
        raise SnapshotDivergenceError("task snapshot request_fingerprint mismatch")
    token_fp = canonical_token.get("request_fingerprint")
    result_fp = canonical_result.get("request_fingerprint")
    if not token_fp:
        raise SnapshotDivergenceError("task snapshot missing token fingerprint")
    if not result_fp:
        raise SnapshotDivergenceError("task snapshot missing result fingerprint")
    if token_fp and token_fp != request_fingerprint:
        raise SnapshotDivergenceError("task snapshot token fingerprint mismatch")
    if result_fp and result_fp != request_fingerprint:
        raise SnapshotDivergenceError("task snapshot result fingerprint mismatch")
    canonical = {
        "request": canonical_request,
        "request_fingerprint": request_fingerprint,
        "task": canonical_task,
        "result": canonical_result,
        "admission_token": canonical_token,
        "authorization": canonical_auth,
    }
    _validate_canonical_snapshot(canonical)
    return canonical


def _validate_canonical_snapshot(snapshot: Mapping[str, Any]) -> None:
    token = snapshot["admission_token"]
    request = snapshot.get("request", {})
    prov = token.get("provenance", {})
    for field_name in ("authority_source", "authority_scope", "authority_context_id", "authority_reason"):
        if not str(prov.get(field_name, "")).strip():
            raise SnapshotDivergenceError("task snapshot provenance incomplete")
    if snapshot["task"]["task_id"] != token["task_id"] or snapshot["result"]["task_id"] != token["task_id"]:
        raise SnapshotDivergenceError("task snapshot task id mismatch")
    request_task_id = request.get("task", {}).get("task_id") if isinstance(request, Mapping) else None
    if request_task_id is not None and request_task_id != token["task_id"]:
        raise SnapshotDivergenceError("task snapshot request task id mismatch")
    token_fp = token.get("request_fingerprint")
    result_fp = snapshot["result"].get("request_fingerprint")
    request_fp = snapshot.get("request_fingerprint")
    if not token_fp or not request_fp or not result_fp:
        raise SnapshotDivergenceError("task snapshot missing request fingerprint")
    if request_fp and token_fp and request_fp != token_fp:
        raise SnapshotDivergenceError("task snapshot request fingerprint mismatch with token")
    if request_fp and result_fp and request_fp != result_fp:
        raise SnapshotDivergenceError("task snapshot request fingerprint mismatch with result")


class SnapshotDivergenceError(RuntimeError):
    """Raised when a persisted task execution snapshot cannot be trusted."""


def _normalise_text(value: str | None) -> str:
    return value.rstrip() if isinstance(value, str) else ""


def _canonicalise_sequence(values: Sequence[Any], *, strip_strings: bool) -> list[object]:
    return [_ensure_json_safe(value, strip_strings=strip_strings) for value in values]


def _canonicalise_mapping(mapping: Mapping[str, object] | None, *, strip_strings: bool = False) -> dict[str, object]:
    normalized: MutableMapping[str, object] = {}
    for key, value in sorted((mapping or {}).items(), key=lambda item: str(item[0])):
        normalized[str(key)] = _ensure_json_safe(value, strip_strings=strip_strings)
    return dict(normalized)


def _ensure_json_safe(value: object, *, strip_strings: bool) -> object:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value.rstrip() if strip_strings else value
    if isinstance(value, Mapping):
        return _canonicalise_mapping(value, strip_strings=strip_strings)
    if isinstance(value, (list, tuple)):
        return _canonicalise_sequence(value, strip_strings=strip_strings)
    raise RequestCanonicalizationError(f"request contains non-serializable type: {type(value).__name__}")


def canonicalise_declared_inputs(declared_inputs: Mapping[str, object] | None) -> dict[str, object]:
    return _canonicalise_mapping(declared_inputs or {}, strip_strings=True)


def canonicalise_task_request(
    *,
    task: Task,
    authorization: AuthorizationRecord,
    provenance: AuthorityProvenance,
    declared_inputs: Mapping[str, object] | None = None,
) -> dict[str, object]:
    try:
        canonical_request = {
            "task": canonicalise_task(task),
            "authorization": canonicalise_authorization(authorization),
            "provenance": canonicalise_provenance(provenance),
            "declared_inputs": canonicalise_declared_inputs(declared_inputs),
        }
        enforce_no_gradient_fields(canonical_request, context="task_request")
        _assert_serializable(canonical_request)
        return canonical_request
    except GradientInvariantViolation as exc:
        raise RequestCanonicalizationError(str(exc)) from exc


def canonicalise_task_request_from_payload(payload: Mapping[str, Any]) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise SnapshotDivergenceError("task request must be a mapping")
    task_payload = payload.get("task")
    auth_payload = payload.get("authorization")
    prov_payload = payload.get("provenance")
    declared_inputs_payload = payload.get("declared_inputs")
    if not isinstance(task_payload, Mapping):
        raise SnapshotDivergenceError("task request missing task payload")
    if not isinstance(auth_payload, Mapping):
        raise SnapshotDivergenceError("task request missing authorization payload")
    if not isinstance(prov_payload, Mapping):
        raise SnapshotDivergenceError("task request missing provenance payload")
    try:
        canonical_request = {
            "task": _canonicalise_task_payload(task_payload),
            "authorization": _canonicalise_authorization_payload(auth_payload),
            "provenance": _canonicalise_provenance_payload(prov_payload),
            "declared_inputs": canonicalise_declared_inputs(declared_inputs_payload if declared_inputs_payload else {}),
        }
        enforce_no_gradient_fields(canonical_request, context="task_request.snapshot")
        _assert_serializable(canonical_request)
        return canonical_request
    except GradientInvariantViolation as exc:
        raise SnapshotDivergenceError(str(exc)) from exc
    except RequestCanonicalizationError as exc:
        raise SnapshotDivergenceError(str(exc)) from exc


def request_fingerprint_from_canonical(canonical_request: Mapping[str, object]) -> RequestFingerprint:
    _assert_serializable(canonical_request)
    serialised = json.dumps(canonical_request, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(serialised.encode("utf-8")).hexdigest()
    return RequestFingerprint(digest)


def _assert_serializable(payload: object) -> None:
    try:
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except TypeError as exc:
        raise RequestCanonicalizationError(f"request is not JSON serializable: {exc}") from exc


def _canonicalise_task_payload(task_payload: Mapping[str, Any]) -> dict[str, object]:
    canonical_task = {
        "task_id": str(task_payload.get("task_id", "")).strip(),
        "objective": _normalise_text(task_payload.get("objective", "")),
        "constraints": sorted(_normalise_text(c) for c in (task_payload.get("constraints", []) or [])),
        "steps": [
            {
                "step_id": int(step.get("step_id")),
                "kind": step.get("kind"),
                "expects": sorted(_normalise_text(e) for e in (step.get("expects", []) or [])),
                "payload": _canonicalise_mapping(step.get("payload", {}) or {}),
            }
            for step in task_payload.get("steps", []) or []
        ],
    }
    return canonical_task


def _canonicalise_result_payload(result_payload: Mapping[str, Any]) -> dict[str, object]:
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
        "request_fingerprint": str(result_payload.get("request_fingerprint", "")),
    }
    return canonical_result


def _canonicalise_token_payload(token_payload: Mapping[str, Any]) -> dict[str, object]:
    return {
        "task_id": str(token_payload.get("task_id", "")),
        "issued_by": str(token_payload.get("issued_by", "")),
        "provenance": _canonicalise_provenance_payload(token_payload.get("provenance", {}) or {}),
        "request_fingerprint": str(token_payload.get("request_fingerprint", "")),
    }


def _canonicalise_provenance_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    return {
        "authority_source": str(payload.get("authority_source", "")),
        "authority_scope": str(payload.get("authority_scope", "")),
        "authority_context_id": str(payload.get("authority_context_id", "")),
        "authority_reason": str(payload.get("authority_reason", "")),
    }


def _canonicalise_authorization_payload(auth_payload: Mapping[str, Any]) -> dict[str, object]:
    canonical_auth = {
        "request_type": str(auth_payload.get("request_type", "")),
        "requester_id": str(auth_payload.get("requester_id", "")),
        "intent_hash": str(auth_payload.get("intent_hash", "")),
        "context_hash": str(auth_payload.get("context_hash", "")),
        "policy_version": str(auth_payload.get("policy_version", "")),
        "decision": str(auth_payload.get("decision", "")),
        "reason": str(auth_payload.get("reason", "")),
    }
    return canonical_auth
