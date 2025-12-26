from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
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
EprAuthorityImpact = Literal["none", "local", "global"]
EprReversibility = Literal["guaranteed", "bounded", "none"]
EprRollbackProof = Literal["snapshot", "diff", "commit", "none"]
EprExternalEffects = Literal["yes", "no"]
EprActionStatus = Literal["completed", "blocked", "failed"]
PrerequisiteStatus = Literal["satisfied", "epr-fixable", "authority-required", "impossible", "unknown"]
ExhaustionType = Literal["closure_exhausted", "epr_exhausted"]


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
    allow_epr: bool = False
    epr_actions: Sequence["EprAction"] = field(default_factory=tuple)


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    status: TaskStatus
    artifacts: Dict[str, Mapping[str, object]]
    trace: Sequence[StepTrace]
    epr_report: "EprReport"
    admission_token: "AdmissionToken"
    authorization: AuthorizationRecord
    request_fingerprint: "RequestFingerprint"
    canonical_request: Mapping[str, object]


@dataclass(frozen=True)
class EprAction:
    action_id: str
    parent_task_id: str
    trigger_step_id: int
    authority_impact: EprAuthorityImpact
    reversibility: EprReversibility
    rollback_proof: EprRollbackProof
    external_effects: EprExternalEffects
    handler: Callable[[], Mapping[str, object]] | None = None
    description: str | None = None
    kind: Literal["EPR"] = "EPR"
    changes_governance: bool = False
    changes_admission: bool = False
    changes_authorization: bool = False
    changes_policy: bool = False
    changes_permissions: bool = False
    privilege_escalation: bool = False
    task_goal_reinterpretation: bool = False
    background_execution: bool = False
    unknown_prerequisite: "UnknownPrerequisite | None" = None


@dataclass(frozen=True)
class EprActionTrace:
    action_id: str
    status: EprActionStatus
    rollback_proof: EprRollbackProof
    authority_impact: EprAuthorityImpact
    reversibility: EprReversibility
    external_effects: EprExternalEffects
    error: str | None = None


@dataclass(frozen=True)
class EprReport:
    actions: Sequence[EprActionTrace] = field(default_factory=tuple)
    rollback_proofs: Sequence[EprRollbackProof] = field(default_factory=tuple)
    net_authority_delta: int = 0
    artifacts_persisted: bool = False


@dataclass(frozen=True)
class PrerequisiteAssessment:
    action_id: str
    status: PrerequisiteStatus
    reason: str | None = None


@dataclass(frozen=True)
class UnknownPrerequisite:
    condition: str
    reason: str
    unblock_query: str | None = None
    response: str | None = None
    resolved_status: PrerequisiteStatus | None = None


@dataclass(frozen=True)
class ClosureReport:
    prerequisites: Sequence[PrerequisiteAssessment] = field(default_factory=tuple)
    epr_report: EprReport = field(default_factory=EprReport)


@dataclass(frozen=True)
class ClosureLimits:
    max_closure_iterations: int = 3
    max_epr_actions_per_task: int = 5
    max_nested_prerequisite_depth: int = 3
    max_unknown_resolution_cycles: int = 2


@dataclass(frozen=True)
class ExhaustionReport:
    exhaustion_type: ExhaustionType
    attempts: Mapping[str, int]
    attempted_actions: Sequence[str]
    cycle_evidence: Sequence[str]
    final_state: Sequence[PrerequisiteAssessment]
    reason: str
    operator_question: str | None = None


class StepExecutionError(Exception):
    def __init__(self, step: Step, message: str):
        super().__init__(message)
        self.step = step


class RequestCanonicalizationError(RuntimeError):
    """Raised when a task request cannot be normalized into canonical form."""


class RequestFingerprintMismatchError(RuntimeError):
    """Raised when the request fingerprint at execution time diverges from admission."""


class EprViolationError(RuntimeError):
    """Raised when an EPR action violates non-negotiable invariants."""


class EprApprovalRequired(RuntimeError):
    """Raised when an EPR action requires explicit operator approval."""

    def __init__(self, message: str, actions: Sequence["EprAction"] = ()):
        super().__init__(message)
        self.actions = tuple(actions)


class EprGateBlocked(RuntimeError):
    """Raised when EPR is required but not permitted."""


class TaskClosureError(RuntimeError):
    """Raised when task closure cannot complete."""

    def __init__(self, message: str, assessments: Sequence["PrerequisiteAssessment"] = ()):
        super().__init__(message)
        self.assessments = tuple(assessments)


class UnknownPrerequisiteError(TaskClosureError):
    """Raised when task closure halts on unknown prerequisites."""

    def __init__(
        self,
        message: str,
        assessments: Sequence["PrerequisiteAssessment"] = (),
        unblock_query: str | None = None,
    ):
        super().__init__(message, assessments)
        self.unblock_query = unblock_query


class TaskExhausted(RuntimeError):
    """Raised when task closure or EPR hits deterministic exhaustion limits."""

    def __init__(self, report: ExhaustionReport):
        super().__init__(report.reason)
        self.report = report


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


ApprovalGrants = Mapping[str, bool] | None


def execute_task(
    task: Task,
    *,
    authorization: AuthorizationRecord | None = None,
    admission_token: AdmissionToken | None = None,
    declared_inputs: Mapping[str, object] | None = None,
    approval_grants: ApprovalGrants = None,
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
    closure = _close_task(task, approval_grants=approval_grants)
    epr_report = closure.epr_report
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
                epr_report=epr_report,
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
        epr_report=epr_report,
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


def _load_closure_limits() -> ClosureLimits:
    return ClosureLimits(
        max_closure_iterations=_read_int_env("SENTIENTOS_MAX_CLOSURE_ITERATIONS", 3),
        max_epr_actions_per_task=_read_int_env("SENTIENTOS_MAX_EPR_ACTIONS_PER_TASK", 5),
        max_nested_prerequisite_depth=_read_int_env("SENTIENTOS_MAX_NESTED_PREREQUISITE_DEPTH", 3),
        max_unknown_resolution_cycles=_read_int_env("SENTIENTOS_MAX_UNKNOWN_RESOLUTION_CYCLES", 2),
    )


def load_closure_limits() -> ClosureLimits:
    limits = _load_closure_limits()
    _validate_limits(limits)
    return limits


def _read_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise TaskClosureError(f"invalid integer for {name}: {value}") from exc
    return parsed


def _validate_limits(limits: ClosureLimits) -> None:
    for label, value in asdict(limits).items():
        if not isinstance(value, int) or value < 0:
            raise TaskClosureError(f"closure limit {label} must be a non-negative integer")


def _enforce_depth_limits(task: Task, limits: ClosureLimits) -> None:
    depth = _estimate_prerequisite_depth(task)
    if depth > limits.max_nested_prerequisite_depth:
        _raise_exhaustion(
            task,
            exhaustion_type="closure_exhausted",
            attempts={"closure_iterations": 0, "epr_actions": 0, "unknown_cycles": 0},
            attempted_actions=(),
            cycle_evidence=["prerequisite_depth_limit_exceeded"],
            final_state=(),
            reason=f"Prerequisite depth {depth} exceeds limit {limits.max_nested_prerequisite_depth}",
        )
    if len(task.epr_actions) > limits.max_epr_actions_per_task:
        _raise_exhaustion(
            task,
            exhaustion_type="epr_exhausted",
            attempts={"closure_iterations": 0, "epr_actions": 0, "unknown_cycles": 0},
            attempted_actions=(),
            cycle_evidence=["epr_action_count_exceeded"],
            final_state=(),
            reason=(
                "EPR action count exceeds limit "
                f"{limits.max_epr_actions_per_task}"
            ),
        )


def _estimate_prerequisite_depth(task: Task) -> int:
    depth = 0
    for action in task.epr_actions:
        depth = max(depth, 1 + (1 if action.unknown_prerequisite else 0))
    return depth


def _prerequisite_state_signature(
    assessments: Sequence[PrerequisiteAssessment],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (assessment.action_id, assessment.status, assessment.reason or "")
        for assessment in sorted(assessments, key=lambda a: a.action_id)
    )


def _epr_outcome_signature(
    traces: Sequence[EprActionTrace],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (trace.action_id, trace.status, trace.error or "")
        for trace in sorted(traces, key=lambda t: t.action_id)
    )


def _epr_closure_changed(result: Mapping[str, object] | None) -> bool:
    if result is None:
        return True
    if "closure_changed" in result:
        return bool(result["closure_changed"])
    if "resolved_status" in result:
        return result["resolved_status"] == "satisfied"
    return True


def _raise_exhaustion(
    task: Task,
    *,
    exhaustion_type: ExhaustionType,
    attempts: Mapping[str, int],
    attempted_actions: Sequence[str],
    cycle_evidence: Sequence[str],
    final_state: Sequence[PrerequisiteAssessment],
    reason: str,
    operator_question: str | None = None,
) -> None:
    report = ExhaustionReport(
        exhaustion_type=exhaustion_type,
        attempts=dict(attempts),
        attempted_actions=tuple(attempted_actions),
        cycle_evidence=tuple(cycle_evidence),
        final_state=tuple(final_state),
        reason=reason,
        operator_question=operator_question,
    )
    _log_exhaustion(task.task_id, report)
    raise TaskExhausted(report)


def _log_exhaustion(task_id: str, report: ExhaustionReport) -> None:
    entry = {
        "task_id": task_id,
        "event": "exhaustion",
        "exhaustion_type": report.exhaustion_type,
        "attempts": dict(report.attempts),
        "attempted_actions": list(report.attempted_actions),
        "cycle_evidence": list(report.cycle_evidence),
        "final_state": [
            {
                "action_id": assessment.action_id,
                "status": assessment.status,
                "reason": assessment.reason,
            }
            for assessment in report.final_state
        ],
        "reason": report.reason,
    }
    if report.operator_question:
        entry["operator_question"] = report.operator_question
    append_json(Path(LOG_PATH), entry)


def _execute_epr_actions(
    *,
    task: Task,
    actions: Sequence[EprAction],
    report: EprReport,
    approval_grants: ApprovalGrants = None,
) -> tuple[EprReport, Dict[str, bool]]:
    traces: list[EprActionTrace] = list(report.actions)
    rollback_proofs: list[EprRollbackProof] = list(report.rollback_proofs)
    outcomes: Dict[str, bool] = {}
    for action in actions:
        _validate_epr_action(task, action)
        try:
            _authorize_epr_action(action, approval_grants=approval_grants)
            handler_result = action.handler() if action.handler is not None else None
            outcomes[action.action_id] = _epr_closure_changed(handler_result)
            trace = EprActionTrace(
                action_id=action.action_id,
                status="completed",
                rollback_proof=action.rollback_proof,
                authority_impact=action.authority_impact,
                reversibility=action.reversibility,
                external_effects=action.external_effects,
            )
        except EprApprovalRequired as exc:
            trace = EprActionTrace(
                action_id=action.action_id,
                status="blocked",
                rollback_proof=action.rollback_proof,
                authority_impact=action.authority_impact,
                reversibility=action.reversibility,
                external_effects=action.external_effects,
                error=str(exc),
            )
            _log_epr_action(task.task_id, action, trace)
            traces.append(trace)
            rollback_proofs.append(action.rollback_proof)
            raise
        except EprViolationError as exc:
            trace = EprActionTrace(
                action_id=action.action_id,
                status="failed",
                rollback_proof=action.rollback_proof,
                authority_impact=action.authority_impact,
                reversibility=action.reversibility,
                external_effects=action.external_effects,
                error=str(exc),
            )
            _log_epr_action(task.task_id, action, trace)
            traces.append(trace)
            rollback_proofs.append(action.rollback_proof)
            raise
        except Exception as exc:  # pragma: no cover - defensive guardrail
            trace = EprActionTrace(
                action_id=action.action_id,
                status="failed",
                rollback_proof=action.rollback_proof,
                authority_impact=action.authority_impact,
                reversibility=action.reversibility,
                external_effects=action.external_effects,
                error=str(exc) or exc.__class__.__name__,
            )
            _log_epr_action(task.task_id, action, trace)
            traces.append(trace)
            rollback_proofs.append(action.rollback_proof)
            raise EprViolationError("EPR action failed during execution") from exc
        _log_epr_action(task.task_id, action, trace)
        traces.append(trace)
        rollback_proofs.append(action.rollback_proof)
    return EprReport(
        actions=tuple(traces),
        rollback_proofs=tuple(rollback_proofs),
        net_authority_delta=0,
        artifacts_persisted=False,
    ), outcomes


def _close_task(task: Task, *, approval_grants: ApprovalGrants = None) -> ClosureReport:
    limits = _load_closure_limits()
    _validate_limits(limits)
    _enforce_depth_limits(task, limits)
    if limits.max_closure_iterations == 0:
        _raise_exhaustion(
            task,
            exhaustion_type="closure_exhausted",
            attempts={"closure_iterations": 0, "epr_actions": 0, "unknown_cycles": 0},
            attempted_actions=(),
            cycle_evidence=["closure_iteration_limit_zero"],
            final_state=(),
            reason="Closure iteration limit is zero",
        )
    attempts = {"closure_iterations": 0, "epr_actions": 0, "unknown_cycles": 0}
    assessments: list[PrerequisiteAssessment] = []
    epr_report = EprReport()
    executed_actions: set[str] = set()
    resolved_actions: Dict[str, PrerequisiteStatus] = {}
    seen_states: set[tuple[tuple[str, str, str], ...]] = set()
    seen_epr_outcomes: set[tuple[tuple[str, str, str], ...]] = set()
    cycle_evidence: list[str] = []
    last_state: tuple[tuple[str, str, str], ...] | None = None
    last_iteration_ran_epr = False
    for _ in range(limits.max_closure_iterations):
        attempts["closure_iterations"] += 1
        assessments = []
        fixable_actions: list[EprAction] = []
        authority_required: list[EprAction] = []
        impossible: list[PrerequisiteAssessment] = []
        unknowns: list[tuple[EprAction, PrerequisiteAssessment, str]] = []
        for action in task.epr_actions:
            if action.action_id in resolved_actions:
                assessment = PrerequisiteAssessment(
                    action_id=action.action_id,
                    status=resolved_actions[action.action_id],
                    reason="resolved by EPR action",
                )
            else:
                assessment = _assess_prerequisite(task, action, approval_grants=approval_grants)
            assessments.append(assessment)
            if assessment.status == "unknown":
                query = _build_unblock_query(action, assessment)
                _log_unknown_prerequisite(task.task_id, action, assessment, query)
                unknowns.append((action, assessment, query))
            elif assessment.status == "epr-fixable":
                fixable_actions.append(action)
            elif assessment.status == "authority-required":
                authority_required.append(action)
            elif assessment.status == "impossible":
                impossible.append(assessment)
        state_signature = _prerequisite_state_signature(assessments)
        if last_state is not None and state_signature == last_state and last_iteration_ran_epr:
            cycle_evidence.append("repair_actions_no_progress")
            _raise_exhaustion(
                task,
                exhaustion_type="epr_exhausted",
                attempts=attempts,
                attempted_actions=sorted(executed_actions),
                cycle_evidence=cycle_evidence,
                final_state=assessments,
                reason="EPR actions did not change closure state",
            )
        if state_signature in seen_states:
            cycle_evidence.append("repeated_prerequisite_state")
            _raise_exhaustion(
                task,
                exhaustion_type="closure_exhausted",
                attempts=attempts,
                attempted_actions=sorted(executed_actions),
                cycle_evidence=cycle_evidence,
                final_state=assessments,
                reason="Prerequisite states repeated without convergence",
            )
        seen_states.add(state_signature)
        if unknowns:
            attempts["unknown_cycles"] += 1
            if attempts["unknown_cycles"] > limits.max_unknown_resolution_cycles:
                cycle_evidence.append("unknown_prerequisite_cycles_exceeded")
                _raise_exhaustion(
                    task,
                    exhaustion_type="closure_exhausted",
                    attempts=attempts,
                    attempted_actions=sorted(executed_actions),
                    cycle_evidence=cycle_evidence,
                    final_state=assessments,
                    reason="Unknown prerequisites exceeded allowed resolution cycles",
                )
            primary_query = unknowns[0][2]
            detail = ", ".join(
                f"{action.action_id}:{assessment.reason or 'unknown'}"
                for action, assessment, _ in unknowns
            )
            raise UnknownPrerequisiteError(
                f"Task closure halted on unknown prerequisites: {detail}",
                assessments,
                unblock_query=primary_query,
            )
        if impossible:
            reasons = ", ".join(
                f"{assessment.action_id}:{assessment.reason or 'impossible'}" for assessment in impossible
            )
            raise TaskClosureError(f"Task closure failed: {reasons}", assessments)
        if fixable_actions:
            new_actions = [action for action in fixable_actions if action.action_id not in executed_actions]
            if not new_actions:
                cycle_evidence.append("repeated_epr_actions")
                _raise_exhaustion(
                    task,
                    exhaustion_type="epr_exhausted",
                    attempts=attempts,
                    attempted_actions=sorted(executed_actions),
                    cycle_evidence=cycle_evidence,
                    final_state=assessments,
                    reason="EPR actions repeated without net progress",
                )
            if attempts["epr_actions"] + len(new_actions) > limits.max_epr_actions_per_task:
                cycle_evidence.append("epr_action_limit_exceeded")
                _raise_exhaustion(
                    task,
                    exhaustion_type="epr_exhausted",
                    attempts=attempts,
                    attempted_actions=sorted(executed_actions),
                    cycle_evidence=cycle_evidence,
                    final_state=assessments,
                    reason="EPR action limit exceeded before closure could converge",
                )
            before = len(epr_report.actions)
            epr_report, outcomes = _execute_epr_actions(
                task=task, actions=new_actions, report=epr_report, approval_grants=approval_grants
            )
            attempts["epr_actions"] += len(new_actions)
            executed_actions.update(action.action_id for action in new_actions)
            for action_id, changed in outcomes.items():
                if changed:
                    resolved_actions[action_id] = "satisfied"
            new_traces = epr_report.actions[before:]
            outcome_signature = _epr_outcome_signature(new_traces)
            if outcome_signature in seen_epr_outcomes:
                cycle_evidence.append("repeated_epr_outcomes")
                _raise_exhaustion(
                    task,
                    exhaustion_type="epr_exhausted",
                    attempts=attempts,
                    attempted_actions=sorted(executed_actions),
                    cycle_evidence=cycle_evidence,
                    final_state=assessments,
                    reason="EPR actions cycled without changing outcomes",
                )
            seen_epr_outcomes.add(outcome_signature)
            last_state = state_signature
            last_iteration_ran_epr = True
            continue
        if authority_required:
            action_ids = ", ".join(action.action_id for action in authority_required)
            raise EprApprovalRequired(f"EPR approval required for: {action_ids}", authority_required)
        return ClosureReport(prerequisites=tuple(assessments), epr_report=epr_report)
    cycle_evidence.append("closure_iteration_limit_exceeded")
    _raise_exhaustion(
        task,
        exhaustion_type="closure_exhausted",
        attempts=attempts,
        attempted_actions=sorted(executed_actions),
        cycle_evidence=cycle_evidence,
        final_state=assessments,
        reason="Closure iteration limit exceeded without convergence",
    )
    raise TaskClosureError("closure exhaustion unreachable")  # pragma: no cover - defensive


def _assess_prerequisite(
    task: Task,
    action: EprAction,
    *,
    approval_grants: ApprovalGrants = None,
) -> PrerequisiteAssessment:
    if action.unknown_prerequisite is not None:
        _validate_unknown_prerequisite(action.unknown_prerequisite)
        return _assess_unknown_prerequisite(action.action_id, action.unknown_prerequisite)
    try:
        _validate_epr_action(task, action)
    except EprViolationError as exc:
        return PrerequisiteAssessment(action_id=action.action_id, status="impossible", reason=str(exc))
    if not task.allow_epr:
        return PrerequisiteAssessment(
            action_id=action.action_id,
            status="impossible",
            reason="EPR not permitted for task",
        )
    try:
        _authorize_epr_action(action, approval_grants=approval_grants)
    except EprApprovalRequired as exc:
        return PrerequisiteAssessment(action_id=action.action_id, status="authority-required", reason=str(exc))
    except EprViolationError as exc:
        return PrerequisiteAssessment(action_id=action.action_id, status="impossible", reason=str(exc))
    return PrerequisiteAssessment(action_id=action.action_id, status="epr-fixable")


def _validate_epr_action(task: Task, action: EprAction) -> None:
    if action.unknown_prerequisite is not None:
        _validate_unknown_prerequisite(action.unknown_prerequisite)
    if action.kind != "EPR":
        raise EprViolationError("EPR action kind must be EPR")
    if action.parent_task_id != task.task_id:
        raise EprViolationError("EPR parent_task_id mismatch")
    if action.authority_impact not in {"none", "local", "global"}:
        raise EprViolationError("EPR authority_impact invalid")
    if action.reversibility not in {"guaranteed", "bounded", "none"}:
        raise EprViolationError("EPR reversibility invalid")
    if action.rollback_proof not in {"snapshot", "diff", "commit", "none"}:
        raise EprViolationError("EPR rollback_proof invalid")
    if action.external_effects not in {"yes", "no"}:
        raise EprViolationError("EPR external_effects invalid")
    if action.external_effects == "yes":
        raise EprViolationError("EPR external effects are prohibited")
    if action.trigger_step_id <= 0:
        raise EprViolationError("EPR trigger_step_id invalid")
    prohibited = {
        "governance changes": action.changes_governance,
        "admission changes": action.changes_admission,
        "authorization changes": action.changes_authorization,
        "policy changes": action.changes_policy,
        "permission edits": action.changes_permissions,
        "privilege escalation": action.privilege_escalation,
        "task goal reinterpretation": action.task_goal_reinterpretation,
        "background execution": action.background_execution,
    }
    for label, flagged in prohibited.items():
        if flagged:
            raise EprViolationError(f"EPR attempted prohibited action: {label}")


def _authorize_epr_action(action: EprAction, *, approval_grants: ApprovalGrants = None) -> None:
    if _approval_granted(action, approval_grants):
        return
    if action.authority_impact == "none" and action.reversibility == "guaranteed":
        return
    if action.authority_impact == "none" and action.reversibility == "bounded":
        if action.rollback_proof != "none":
            return
        raise EprViolationError("EPR rollback proof required for bounded reversibility")
    raise EprApprovalRequired("EPR action requires explicit operator approval")


def _assess_unknown_prerequisite(
    action_id: str,
    unknown: UnknownPrerequisite,
) -> PrerequisiteAssessment:
    if unknown.resolved_status is None:
        return PrerequisiteAssessment(action_id=action_id, status="unknown", reason=unknown.reason)
    if unknown.resolved_status == "unknown":
        return PrerequisiteAssessment(action_id=action_id, status="unknown", reason=unknown.reason)
    response_reason = unknown.response or unknown.reason
    return PrerequisiteAssessment(action_id=action_id, status=unknown.resolved_status, reason=response_reason)


def _validate_unknown_prerequisite(unknown: UnknownPrerequisite) -> None:
    if not unknown.condition.strip():
        raise EprViolationError("unknown prerequisite missing condition")
    if not unknown.reason.strip():
        raise EprViolationError("unknown prerequisite missing reason")
    if unknown.resolved_status == "unknown":
        raise EprViolationError("unknown prerequisite resolved_status cannot be unknown")


def _approval_key(action: EprAction) -> str:
    return f"{action.parent_task_id}:{action.action_id}"


def _approval_granted(action: EprAction, approval_grants: ApprovalGrants) -> bool:
    if not approval_grants:
        return False
    if approval_grants.get(_approval_key(action)):
        return True
    return bool(approval_grants.get(action.action_id))


def assess_task_prerequisites(
    task: Task, *, approval_grants: ApprovalGrants = None
) -> tuple[tuple[EprAction, PrerequisiteAssessment], ...]:
    assessments: list[tuple[EprAction, PrerequisiteAssessment]] = []
    for action in task.epr_actions:
        assessment = _assess_prerequisite(task, action, approval_grants=approval_grants)
        assessments.append((action, assessment))
    return tuple(assessments)


def _build_unblock_query(action: EprAction, assessment: PrerequisiteAssessment) -> str:
    unknown = action.unknown_prerequisite
    if unknown is None:
        return "Unknown prerequisite requires operator clarification."
    if unknown.unblock_query:
        return unknown.unblock_query
    reason = assessment.reason or "cannot be inferred deterministically"
    return (
        f"Prerequisite '{unknown.condition}' cannot be classified because {reason}. "
        "Please provide the minimal confirmation or override needed to continue."
    )


def _log_unknown_prerequisite(
    task_id: str,
    action: EprAction,
    assessment: PrerequisiteAssessment,
    unblock_query: str,
) -> None:
    unknown = action.unknown_prerequisite
    entry = {
        "task_id": task_id,
        "event": "unknown_prerequisite",
        "action_id": action.action_id,
        "condition": unknown.condition if unknown else "unspecified",
        "reason": assessment.reason or "unknown",
        "unblock_query": unblock_query,
        "status": assessment.status,
    }
    if unknown and unknown.response is not None:
        entry["operator_response"] = unknown.response
    append_json(Path(LOG_PATH), entry)


def _log_epr_action(task_id: str, action: EprAction, trace: EprActionTrace) -> None:
    entry = {
        "task_id": task_id,
        "event": "epr_action",
        "kind": action.kind,
        "action_id": action.action_id,
        "parent_task_id": action.parent_task_id,
        "trigger_step_id": action.trigger_step_id,
        "authority_impact": action.authority_impact,
        "reversibility": action.reversibility,
        "rollback_proof": action.rollback_proof,
        "external_effects": action.external_effects,
        "status": trace.status,
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


def _canonical_epr_action(action: EprAction) -> dict[str, object]:
    return {
        "action_id": _normalise_text(action.action_id),
        "parent_task_id": _normalise_text(action.parent_task_id),
        "trigger_step_id": action.trigger_step_id,
        "authority_impact": action.authority_impact,
        "reversibility": action.reversibility,
        "rollback_proof": action.rollback_proof,
        "external_effects": action.external_effects,
        "kind": action.kind,
        "description": _normalise_text(action.description),
        "changes_governance": action.changes_governance,
        "changes_admission": action.changes_admission,
        "changes_authorization": action.changes_authorization,
        "changes_policy": action.changes_policy,
        "changes_permissions": action.changes_permissions,
        "privilege_escalation": action.privilege_escalation,
        "task_goal_reinterpretation": action.task_goal_reinterpretation,
        "background_execution": action.background_execution,
        "unknown_prerequisite": _canonical_unknown_prerequisite(action.unknown_prerequisite),
    }


def _canonical_unknown_prerequisite(unknown: UnknownPrerequisite | None) -> dict[str, object] | None:
    if unknown is None:
        return None
    return {
        "condition": _normalise_text(unknown.condition),
        "reason": _normalise_text(unknown.reason),
        "unblock_query": _normalise_text(unknown.unblock_query),
        "response": _normalise_text(unknown.response),
        "resolved_status": unknown.resolved_status or "",
    }


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
        "allow_epr": task.allow_epr,
        "epr_actions": [_canonical_epr_action(action) for action in task.epr_actions],
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
        "epr_report": _canonicalise_epr_report(result.epr_report),
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


def _canonicalise_epr_report(report: EprReport) -> dict[str, object]:
    return {
        "actions": [
            {
                "action_id": _normalise_text(action.action_id),
                "status": action.status,
                "rollback_proof": action.rollback_proof,
                "authority_impact": action.authority_impact,
                "reversibility": action.reversibility,
                "external_effects": action.external_effects,
                **({"error": action.error} if action.error else {}),
            }
            for action in report.actions
        ],
        "rollback_proofs": list(report.rollback_proofs),
        "net_authority_delta": report.net_authority_delta,
        "artifacts_persisted": report.artifacts_persisted,
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
        "allow_epr": bool(task_payload.get("allow_epr", False)),
        "epr_actions": [
            _canonicalise_mapping(action or {})
            for action in (task_payload.get("epr_actions", []) or [])
            if isinstance(action, Mapping)
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
        "epr_report": _canonicalise_epr_report_payload(result_payload.get("epr_report")),
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


def _canonicalise_epr_report_payload(payload: Mapping[str, Any] | None) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        return {
            "actions": [],
            "rollback_proofs": [],
            "net_authority_delta": 0,
            "artifacts_persisted": False,
        }
    actions_payload = payload.get("actions", []) or []
    actions: list[dict[str, object]] = []
    for action in actions_payload:
        if not isinstance(action, Mapping):
            continue
        actions.append(
            {
                "action_id": _normalise_text(action.get("action_id", "")),
                "status": str(action.get("status", "")),
                "rollback_proof": str(action.get("rollback_proof", "")),
                "authority_impact": str(action.get("authority_impact", "")),
                "reversibility": str(action.get("reversibility", "")),
                "external_effects": str(action.get("external_effects", "")),
                **({"error": action["error"]} if action.get("error") else {}),
            }
        )
    rollback_proofs = [str(value) for value in (payload.get("rollback_proofs", []) or [])]
    return {
        "actions": actions,
        "rollback_proofs": rollback_proofs,
        "net_authority_delta": int(payload.get("net_authority_delta", 0) or 0),
        "artifacts_persisted": bool(payload.get("artifacts_persisted", False)),
    }
