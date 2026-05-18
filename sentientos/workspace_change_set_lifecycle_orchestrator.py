"""Bounded lifecycle orchestration for workspace change-set wings.

This module coordinates existing admission, preflight/planning, bounded
execution, verification, and lifecycle-closure APIs. It does not add a new file
effect primitive, executor, verifier, closure system, cleanup path, scheduler,
autonomy loop, or external-tool path. Target mutation, when requested by mode,
is delegated only to the existing workspace change-set execution wing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.workspace_change_set_admission import (
    ADMISSION_PAYLOAD_BODY_KEYS,
    WorkspaceChangeSetAdmissionPolicy,
    run_workspace_change_set_admission_wing,
    summarize_workspace_change_set_admission_decision,
)
from sentientos.workspace_change_set_execution import (
    WorkspaceChangeSetExecutionPolicy,
    run_workspace_change_set_execution_wing,
    summarize_workspace_change_set_execution_closure_report,
    summarize_workspace_change_set_execution_receipt,
    summarize_workspace_change_set_execution_result,
    summarize_workspace_change_set_rollback_execution_result,
)
from sentientos.workspace_change_set_execution_verification import (
    summarize_workspace_change_set_execution_verification_result,
    verify_workspace_change_set_execution,
)
from sentientos.workspace_change_set_lifecycle_closure import (
    build_workspace_change_set_lifecycle_closure_manifest,
    summarize_workspace_change_set_lifecycle_closure_manifest,
)
from sentientos.workspace_change_set_preflight import (
    DEFAULT_CREATED_AT,
    CHANGE_OPERATIONS,
    WorkspaceChangeSetPolicy,
    build_workspace_change_target_declaration,
    run_workspace_change_set_preflight_wing,
    summarize_workspace_change_set_preflight_report,
    summarize_workspace_change_set_transaction_plan,
)

LIFECYCLE_MODES = frozenset({
    "admit_only",
    "admit_and_preflight",
    "admit_preflight_execute",
    "admit_preflight_execute_verify",
    "admit_preflight_execute_verify_close",
    "dry_run_full_lifecycle",
})

STAGE_ORDER = ("admission", "preflight", "execution", "verification", "closure")
MODE_STAGES: Mapping[str, tuple[str, ...]] = {
    "admit_only": ("admission",),
    "admit_and_preflight": ("admission", "preflight"),
    "admit_preflight_execute": ("admission", "preflight", "execution"),
    "admit_preflight_execute_verify": ("admission", "preflight", "execution", "verification"),
    "admit_preflight_execute_verify_close": ("admission", "preflight", "execution", "verification", "closure"),
    "dry_run_full_lifecycle": ("admission", "preflight"),
}
STOP_REASONS = frozenset({
    "admission_blocked",
    "admission_contradicted",
    "admission_insufficient_metadata",
    "preflight_blocked",
    "transaction_plan_not_ready",
    "execution_blocked",
    "execution_failed",
    "verification_failed",
    "closure_contradicted",
    "insufficient_evidence_for_requested_stage",
    "lifecycle_completed_for_requested_mode",
})
NON_AUTHORITY_BOUNDARIES = (
    "coordinates_existing_wings_only",
    "no_new_file_effect_primitive",
    "no_direct_target_file_reads",
    "no_target_digest_recompute_in_orchestrator",
    "no_cleanup_delete_recursion_or_wildcards",
    "no_external_tool_or_provider_paths",
    "execution_only_via_existing_change_set_execution_wing",
    "verification_only_via_existing_verification_wing",
    "closure_only_via_existing_lifecycle_closure_wing",
)
SUCCESSFUL_EXECUTION_STATUSES = frozenset({
    "workspace_change_set_execution_performed",
    "workspace_change_set_execution_performed_with_warnings",
})
PARTIAL_EXECUTION_STATUSES = frozenset({"workspace_change_set_execution_partially_performed"})
PASSED_PREFLIGHT_STATUSES = frozenset({
    "workspace_change_set_preflight_passed",
    "workspace_change_set_preflight_passed_with_warnings",
})
READY_TRANSACTION_STATUSES = frozenset({
    "workspace_change_set_transaction_plan_ready",
    "workspace_change_set_transaction_plan_ready_with_warnings",
})
CLEAN_VERIFICATION_STATUSES = frozenset({"verified_clean", "verified_rolled_back", "verified_with_partial_state"})


@dataclass(frozen=True)
class WorkspaceChangeSetLifecycleOrchestrationPolicy:
    max_targets: int = 8
    max_payload_bytes_per_target: int = 65536
    allow_create: bool = True
    allow_update: bool = True
    allow_replace: bool = True
    require_parent_exists: bool = True
    rollback_on_failure: bool | None = None
    rollback_after_execute: bool = False
    execution_mode: str = "change_set_execute_full_guarded"
    write_execution_ledger: bool = True
    fail_on_partial_execution_for_verify: bool = False
    metadata_only_admission: bool = True
    explicit_lifecycle_orchestration_only: bool = True
    no_new_authority: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetLifecycleOrchestrationRequest:
    request_id: str
    mode: str
    workspace_root: str | None
    proposal_digest: str
    proposed_target_count: int
    stages_requested: tuple[str, ...]
    admission_artifact_output_path: str | None = None
    preflight_artifact_output_path: str | None = None
    execution_artifact_output_path: str | None = None
    verification_artifact_output_path: str | None = None
    closure_artifact_output_path: str | None = None
    orchestration_artifact_output_path: str | None = None
    dry_run: bool = False
    rollback_on_failure: bool | None = None
    created_at: str = DEFAULT_CREATED_AT
    non_authority_boundaries: tuple[str, ...] = NON_AUTHORITY_BOUNDARIES
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetLifecycleStageSummary:
    stage: str
    requested: bool
    attempted: bool
    skipped: bool
    status: str
    digest: str | None = None
    artifact_path: str | None = None
    artifact_digest: str | None = None
    counts: Mapping[str, int] | None = None
    finding_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetLifecycleOrchestrationResult:
    orchestration_id: str
    request_id: str
    requested_mode: str
    stages_requested: tuple[str, ...]
    stages_attempted: tuple[str, ...]
    stages_skipped: tuple[str, ...]
    stage_summaries: tuple[WorkspaceChangeSetLifecycleStageSummary, ...]
    stop_reason: str
    admission_status: str | None
    preflight_status: str | None
    transaction_plan_status: str | None
    transaction_plan_ready: bool
    execution_status: str | None
    verification_status: str | None
    final_lifecycle_status: str | None
    partial_state_visible: bool
    artifact_records: tuple[Mapping[str, str], ...]
    non_authority_boundaries: tuple[str, ...] = NON_AUTHORITY_BOUNDARIES
    dry_run: bool = False
    target_write_performed_by_orchestrator: bool = False
    target_file_read_performed_by_orchestrator: bool = False
    target_digest_recomputed_by_orchestrator: bool = False
    cleanup_performed: bool = False
    scheduler_invoked: bool = False
    external_tool_invoked: bool = False
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkspaceChangeSetLifecycleOrchestrationWing(NamedTuple):
    request: WorkspaceChangeSetLifecycleOrchestrationRequest
    result: WorkspaceChangeSetLifecycleOrchestrationResult
    admission_wing: Any | None = None
    preflight_wing: Mapping[str, Any] | None = None
    execution_wing: Any | None = None
    verification_wing: Any | None = None
    closure_wing: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "result": self.result.to_dict(),
            "admission": self.admission_wing.to_dict() if hasattr(self.admission_wing, "to_dict") else self.admission_wing,
            "preflight": self.preflight_wing,
            "execution": self.execution_wing._asdict() if hasattr(self.execution_wing, "_asdict") else self.execution_wing,
            "verification": self.verification_wing._asdict() if hasattr(self.verification_wing, "_asdict") else self.verification_wing,
            "closure": self.closure_wing._asdict() if hasattr(self.closure_wing, "_asdict") else self.closure_wing,
        }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "_asdict"):
        return {key: _jsonable(item) for key, item in value._asdict().items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()[:24]


def _write_json_artifact(path_text: str | Path | None, payload: Any) -> tuple[str | None, str | None]:
    if path_text is None:
        return None, None
    path = Path(path_text).expanduser()
    text = json.dumps(_jsonable(payload), indent=2, sort_keys=True, ensure_ascii=True, default=str) + "\n"
    path.write_text(text, encoding="utf-8")
    return str(path), "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _targets_payload(proposal: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    raw = proposal.get("targets", proposal.get("proposed_targets", ()))
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return tuple(item for item in raw if isinstance(item, Mapping))
    return ()


def _admission_metadata(proposal: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = dict(proposal)
    targets = []
    for target in _targets_payload(proposal):
        entry = {str(key): value for key, value in target.items() if str(key) not in ADMISSION_PAYLOAD_BODY_KEYS}
        targets.append(entry)
    sanitized["targets"] = targets
    sanitized.pop("proposed_targets", None)
    return sanitized


def _preflight_targets(proposal: Mapping[str, Any], *, created_at: str) -> tuple[Any, ...]:
    targets = []
    for raw in _targets_payload(proposal):
        operation = str(raw.get("operation", "create_file"))
        if operation not in CHANGE_OPERATIONS:
            operation = "create_file"
        payload = raw.get("payload_text", raw.get("payload", raw.get("content", "")))
        targets.append(build_workspace_change_target_declaration(
            target_id=str(raw.get("target_id")) if raw.get("target_id") else None,
            relative_target_path=str(raw.get("relative_target_path", raw.get("path", ""))),
            operation=operation,
            payload_text=str(payload),
            payload_media_type=str(raw.get("payload_media_type", "text/plain; charset=utf-8")),
            allow_replace=bool(raw.get("allow_replace", True)),
            allow_create=bool(raw.get("allow_create", True)),
            created_at=created_at,
        ))
    return tuple(targets)


def build_workspace_change_set_lifecycle_orchestration_request(
    proposal: Mapping[str, Any],
    *,
    mode: str,
    workspace_root: str | Path | None = None,
    admission_artifact_output_path: str | Path | None = None,
    preflight_artifact_output_path: str | Path | None = None,
    execution_artifact_output_path: str | Path | None = None,
    verification_artifact_output_path: str | Path | None = None,
    closure_artifact_output_path: str | Path | None = None,
    orchestration_artifact_output_path: str | Path | None = None,
    rollback_on_failure: bool | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetLifecycleOrchestrationRequest:
    if mode not in LIFECYCLE_MODES:
        raise ValueError(f"unsupported lifecycle mode: {mode}")
    body = {
        "mode": mode,
        "workspace_root": str(workspace_root) if workspace_root is not None else None,
        "proposal_digest": _digest("workspace-change-set-lifecycle-proposal-", _admission_metadata(proposal)),
        "created_at": created_at,
    }
    record = WorkspaceChangeSetLifecycleOrchestrationRequest(
        request_id="workspace-change-set-lifecycle-orchestration-" + hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()[:16],
        mode=mode,
        workspace_root=str(workspace_root) if workspace_root is not None else None,
        proposal_digest=body["proposal_digest"],
        proposed_target_count=len(_targets_payload(proposal)),
        stages_requested=MODE_STAGES[mode],
        admission_artifact_output_path=str(admission_artifact_output_path) if admission_artifact_output_path else None,
        preflight_artifact_output_path=str(preflight_artifact_output_path) if preflight_artifact_output_path else None,
        execution_artifact_output_path=str(execution_artifact_output_path) if execution_artifact_output_path else None,
        verification_artifact_output_path=str(verification_artifact_output_path) if verification_artifact_output_path else None,
        closure_artifact_output_path=str(closure_artifact_output_path) if closure_artifact_output_path else None,
        orchestration_artifact_output_path=str(orchestration_artifact_output_path) if orchestration_artifact_output_path else None,
        dry_run=mode == "dry_run_full_lifecycle",
        rollback_on_failure=rollback_on_failure,
        created_at=created_at,
    )
    return replace(record, digest=_digest("workspace-change-set-lifecycle-orchestration-request-", record.to_dict()))


def _stage(stage: str, requested: tuple[str, ...], attempted: Sequence[str], status: str, *, digest: str | None = None, artifact_path: str | None = None, artifact_digest: str | None = None, counts: Mapping[str, int] | None = None, finding_codes: Sequence[str] = ()) -> WorkspaceChangeSetLifecycleStageSummary:
    return WorkspaceChangeSetLifecycleStageSummary(
        stage=stage,
        requested=stage in requested,
        attempted=stage in attempted,
        skipped=stage in requested and stage not in attempted,
        status=status,
        digest=digest,
        artifact_path=artifact_path,
        artifact_digest=artifact_digest,
        counts=counts,
        finding_codes=tuple(str(item) for item in finding_codes),
    )


def run_workspace_change_set_lifecycle_orchestration(
    proposal: Mapping[str, Any],
    *,
    mode: str,
    workspace_root: str | Path | None = None,
    policy: WorkspaceChangeSetLifecycleOrchestrationPolicy | None = None,
    admission_artifact_output_path: str | Path | None = None,
    preflight_artifact_output_path: str | Path | None = None,
    execution_artifact_output_path: str | Path | None = None,
    verification_artifact_output_path: str | Path | None = None,
    closure_artifact_output_path: str | Path | None = None,
    orchestration_artifact_output_path: str | Path | None = None,
    rollback_on_failure: bool | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetLifecycleOrchestrationWing:
    policy = policy or WorkspaceChangeSetLifecycleOrchestrationPolicy()
    if rollback_on_failure is None:
        rollback_on_failure = policy.rollback_on_failure
    request = build_workspace_change_set_lifecycle_orchestration_request(
        proposal,
        mode=mode,
        workspace_root=workspace_root,
        admission_artifact_output_path=admission_artifact_output_path,
        preflight_artifact_output_path=preflight_artifact_output_path,
        execution_artifact_output_path=execution_artifact_output_path,
        verification_artifact_output_path=verification_artifact_output_path,
        closure_artifact_output_path=closure_artifact_output_path,
        orchestration_artifact_output_path=orchestration_artifact_output_path,
        rollback_on_failure=rollback_on_failure,
        created_at=created_at,
    )
    requested = request.stages_requested
    attempted: list[str] = []
    stage_summaries: list[WorkspaceChangeSetLifecycleStageSummary] = []
    artifact_records: list[Mapping[str, str]] = []
    stop_reason = "lifecycle_completed_for_requested_mode"

    admission_wing = run_workspace_change_set_admission_wing(
        _admission_metadata(proposal),
        policy=WorkspaceChangeSetAdmissionPolicy(
            max_targets=policy.max_targets,
            max_payload_bytes_per_target=policy.max_payload_bytes_per_target,
            allow_create=policy.allow_create,
            allow_update=policy.allow_update,
            allow_replace=policy.allow_replace,
            metadata_only=policy.metadata_only_admission,
        ),
        artifact_output_path=admission_artifact_output_path,
        created_at=created_at,
    )
    attempted.append("admission")
    if admission_wing.artifact_path:
        artifact_records.append({"stage": "admission", "path": admission_wing.artifact_path, "digest": admission_wing.decision.digest})
    admission_summary = summarize_workspace_change_set_admission_decision(admission_wing.decision)
    stage_summaries.append(_stage("admission", requested, attempted, admission_wing.decision.admission_status, digest=admission_wing.decision.digest, artifact_path=admission_wing.artifact_path, artifact_digest=admission_wing.decision.digest, counts={"proposed_target_count": admission_wing.decision.proposed_target_count}, finding_codes=admission_wing.decision.blocker_codes + admission_wing.decision.warning_codes))

    preflight_wing: Mapping[str, Any] | None = None
    execution_wing: Any | None = None
    verification_wing: Any | None = None
    closure_wing: Any | None = None
    preflight_status: str | None = None
    transaction_plan_status: str | None = None
    execution_status: str | None = None
    verification_status: str | None = None
    final_lifecycle_status: str | None = None
    transaction_ready = False
    partial_state_visible = False

    if not admission_wing.decision.preflight_may_be_attempted_next:
        status = admission_wing.decision.admission_status
        stop_reason = "admission_contradicted" if status == "admission_contradicted" else "admission_insufficient_metadata" if status == "admission_insufficient_metadata" else "admission_blocked"
    elif "preflight" in requested:
        if workspace_root is None:
            stop_reason = "insufficient_evidence_for_requested_stage"
            stage_summaries.append(_stage("preflight", requested, attempted, "workspace_change_set_preflight_not_attempted", finding_codes=("workspace_root_required",)))
        else:
            preflight_policy = WorkspaceChangeSetPolicy(
                max_targets=policy.max_targets,
                max_payload_bytes_per_target=policy.max_payload_bytes_per_target,
                require_parent_exists=policy.require_parent_exists,
                allow_replace=policy.allow_replace,
                allow_create=policy.allow_create,
            )
            preflight_wing = run_workspace_change_set_preflight_wing(workspace_root=workspace_root, targets=_preflight_targets(proposal, created_at=created_at), policy=preflight_policy, created_at=created_at)
            attempted.append("preflight")
            preflight_status = str(preflight_wing["preflight_report"]["report_status"])
            transaction_plan_status = str(preflight_wing["transaction_plan"]["transaction_plan_status"])
            transaction_ready = transaction_plan_status in READY_TRANSACTION_STATUSES
            preflight_artifact = {
                "metadata_only": True,
                "stage": "preflight",
                "manifest_id": preflight_wing["manifest"].get("manifest_id"),
                "manifest_digest": preflight_wing["manifest"].get("digest"),
                "preflight_report_id": preflight_wing["preflight_report"].get("report_id"),
                "preflight_report_digest": preflight_wing["preflight_report"].get("digest"),
                "rollback_plan_id": preflight_wing["rollback_plan"].get("plan_id"),
                "rollback_plan_digest": preflight_wing["rollback_plan"].get("digest"),
                "transaction_plan_id": preflight_wing["transaction_plan"].get("plan_id"),
                "transaction_plan_digest": preflight_wing["transaction_plan"].get("digest"),
                "preflight_summary": preflight_wing["summary"],
                "target_payloads_included": False,
                "target_file_contents_included": False,
            }
            p_path, p_digest = _write_json_artifact(preflight_artifact_output_path, preflight_artifact)
            if p_path and p_digest:
                artifact_records.append({"stage": "preflight", "path": p_path, "digest": p_digest})
            stage_summaries.append(_stage("preflight", requested, attempted, preflight_status, digest=str(preflight_wing["preflight_report"].get("digest")), artifact_path=p_path, artifact_digest=p_digest, counts={"target_count": int(preflight_wing["manifest"].get("target_count", 0))}, finding_codes=tuple(preflight_wing["preflight_report"].get("risk_codes", ())) + tuple(preflight_wing["preflight_report"].get("warning_codes", ()))))
            if preflight_status not in PASSED_PREFLIGHT_STATUSES:
                stop_reason = "preflight_blocked"
            elif not transaction_ready:
                stop_reason = "transaction_plan_not_ready"
            elif mode == "dry_run_full_lifecycle":
                stop_reason = "lifecycle_completed_for_requested_mode"

    if stop_reason == "lifecycle_completed_for_requested_mode" and "execution" in requested:
        if preflight_wing is None or not transaction_ready:
            stop_reason = "insufficient_evidence_for_requested_stage"
            stage_summaries.append(_stage("execution", requested, attempted, "workspace_change_set_execution_not_attempted", finding_codes=("preflight_transaction_plan_required",)))
        else:
            from sentientos.workspace_change_set_execution_verification import dataclass_from_dict
            from sentientos.workspace_change_set_preflight import WorkspaceChangeSetManifest, WorkspaceChangeSetPreflightReport, WorkspaceChangeSetRollbackPlan, WorkspaceChangeSetTransactionPlan
            manifest = dataclass_from_dict(WorkspaceChangeSetManifest, preflight_wing["manifest"])
            report = dataclass_from_dict(WorkspaceChangeSetPreflightReport, preflight_wing["preflight_report"])
            rollback_plan = dataclass_from_dict(WorkspaceChangeSetRollbackPlan, preflight_wing["rollback_plan"])
            transaction_plan = dataclass_from_dict(WorkspaceChangeSetTransactionPlan, preflight_wing["transaction_plan"])
            execution_wing = run_workspace_change_set_execution_wing(
                manifest=manifest,
                preflight_report=report,
                rollback_plan=rollback_plan,
                transaction_plan=transaction_plan,
                execution_mode=policy.execution_mode,
                rollback_on_failure=rollback_on_failure,
                rollback_after_execute=policy.rollback_after_execute,
                write_ledger=policy.write_execution_ledger,
                policy=WorkspaceChangeSetExecutionPolicy(max_targets=policy.max_targets, rollback_on_failure_default=policy.rollback_on_failure if policy.rollback_on_failure is not None else True),
                created_at=created_at,
            )
            attempted.append("execution")
            execution_status = execution_wing.execution_result.execution_status
            partial_state_visible = bool(execution_wing.execution_result.partial_state_visible)
            e_path, e_digest = _write_json_artifact(execution_artifact_output_path, {"execution": execution_wing})
            if e_path and e_digest:
                artifact_records.append({"stage": "execution", "path": e_path, "digest": e_digest})
            stage_summaries.append(_stage("execution", requested, attempted, execution_status, digest=execution_wing.execution_result.digest, artifact_path=e_path, artifact_digest=e_digest, counts={"applied_target_count": len(execution_wing.execution_result.applied_target_ids), "failed_target_count": len(execution_wing.execution_result.failed_target_ids), "skipped_target_count": len(execution_wing.execution_result.skipped_target_ids)}, finding_codes=execution_wing.execution_result.risk_codes + execution_wing.execution_result.warning_codes))
            if execution_status == "workspace_change_set_execution_blocked":
                stop_reason = "execution_blocked"
            elif execution_status not in SUCCESSFUL_EXECUTION_STATUSES and (execution_status not in PARTIAL_EXECUTION_STATUSES or policy.fail_on_partial_execution_for_verify or "verification" not in requested):
                stop_reason = "execution_failed"

    if stop_reason == "lifecycle_completed_for_requested_mode" and "verification" in requested:
        if preflight_wing is None or execution_wing is None or not getattr(execution_wing, "execution_receipt", None):
            stop_reason = "insufficient_evidence_for_requested_stage"
            stage_summaries.append(_stage("verification", requested, attempted, "verification_not_attempted", finding_codes=("execution_evidence_required",)))
        else:
            from sentientos.workspace_change_set_execution_verification import dataclass_from_dict
            from sentientos.workspace_change_set_preflight import WorkspaceChangeSetManifest, WorkspaceChangeSetPreflightReport, WorkspaceChangeSetRollbackPlan, WorkspaceChangeSetTransactionPlan
            manifest = dataclass_from_dict(WorkspaceChangeSetManifest, preflight_wing["manifest"])
            report = dataclass_from_dict(WorkspaceChangeSetPreflightReport, preflight_wing["preflight_report"])
            rollback_plan = dataclass_from_dict(WorkspaceChangeSetRollbackPlan, preflight_wing["rollback_plan"])
            transaction_plan = dataclass_from_dict(WorkspaceChangeSetTransactionPlan, preflight_wing["transaction_plan"])
            verification_wing = verify_workspace_change_set_execution(
                manifest=manifest,
                preflight_report=report,
                rollback_plan=rollback_plan,
                transaction_plan=transaction_plan,
                execution_request=execution_wing.request,
                execution_result=execution_wing.execution_result,
                execution_receipt=execution_wing.execution_receipt,
                rollback_result=execution_wing.rollback_result,
                rollback_receipt=execution_wing.rollback_receipt,
                ledger=execution_wing.ledger,
                closure_report=execution_wing.closure_report,
                audit_output_path=str(verification_artifact_output_path) if verification_artifact_output_path else None,
                created_at=created_at,
            )
            attempted.append("verification")
            verification_status = verification_wing.verification_result.verification_status
            partial_state_visible = partial_state_visible or bool(verification_wing.verification_result.partial_state_visible)
            if verification_wing.verification_result.audit_artifact_path:
                artifact_records.append({"stage": "verification", "path": verification_wing.verification_result.audit_artifact_path, "digest": verification_wing.verification_result.audit_artifact_digest or ""})
            stage_summaries.append(_stage("verification", requested, attempted, verification_status, digest=verification_wing.verification_result.digest, artifact_path=verification_wing.verification_result.audit_artifact_path, artifact_digest=verification_wing.verification_result.audit_artifact_digest, counts={"target_count": len(verification_wing.verification_result.target_records)}, finding_codes=verification_wing.verification_result.finding_codes))
            if verification_status not in CLEAN_VERIFICATION_STATUSES:
                stop_reason = "verification_failed" if verification_status == "verification_failed" else "insufficient_evidence_for_requested_stage"

    if stop_reason == "lifecycle_completed_for_requested_mode" and "closure" in requested:
        if preflight_wing is None or execution_wing is None or verification_wing is None:
            stop_reason = "insufficient_evidence_for_requested_stage"
            stage_summaries.append(_stage("closure", requested, attempted, "lifecycle_closure_not_attempted", finding_codes=("verification_evidence_required",)))
        else:
            from sentientos.workspace_change_set_execution_verification import dataclass_from_dict
            from sentientos.workspace_change_set_preflight import WorkspaceChangeSetManifest, WorkspaceChangeSetPreflightReport, WorkspaceChangeSetRollbackPlan, WorkspaceChangeSetTransactionPlan
            manifest = dataclass_from_dict(WorkspaceChangeSetManifest, preflight_wing["manifest"])
            report = dataclass_from_dict(WorkspaceChangeSetPreflightReport, preflight_wing["preflight_report"])
            rollback_plan = dataclass_from_dict(WorkspaceChangeSetRollbackPlan, preflight_wing["rollback_plan"])
            transaction_plan = dataclass_from_dict(WorkspaceChangeSetTransactionPlan, preflight_wing["transaction_plan"])
            closure_wing = build_workspace_change_set_lifecycle_closure_manifest(
                manifest=manifest,
                preflight_report=report,
                rollback_plan=rollback_plan,
                transaction_plan=transaction_plan,
                execution_request=execution_wing.request,
                execution_result=execution_wing.execution_result,
                execution_receipt=execution_wing.execution_receipt,
                rollback_result=execution_wing.rollback_result,
                rollback_receipt=execution_wing.rollback_receipt,
                ledger=execution_wing.ledger,
                closure_report=execution_wing.closure_report,
                verification_request=verification_wing.request,
                verification_result=verification_wing.verification_result,
                artifact_output_path=str(closure_artifact_output_path) if closure_artifact_output_path else None,
                created_at=created_at,
            )
            attempted.append("closure")
            final_lifecycle_status = closure_wing.closure_manifest.lifecycle_closure_status
            if closure_wing.closure_result.artifact_path:
                artifact_records.append({"stage": "closure", "path": closure_wing.closure_result.artifact_path, "digest": closure_wing.closure_result.artifact_digest or ""})
            stage_summaries.append(_stage("closure", requested, attempted, final_lifecycle_status, digest=closure_wing.closure_manifest.digest, artifact_path=closure_wing.closure_result.artifact_path, artifact_digest=closure_wing.closure_result.artifact_digest, counts={"open_target_count": closure_wing.closure_manifest.evidence_summary.open_target_count}, finding_codes=closure_wing.closure_manifest.finding_codes))
            if final_lifecycle_status == "lifecycle_contradicted":
                stop_reason = "closure_contradicted"

    for stage in requested:
        if stage not in attempted and not any(summary.stage == stage for summary in stage_summaries):
            stage_summaries.append(_stage(stage, requested, attempted, "skipped"))

    stages_skipped = tuple(stage for stage in requested if stage not in attempted)
    result = WorkspaceChangeSetLifecycleOrchestrationResult(
        orchestration_id="workspace-change-set-lifecycle-orchestration-result-" + request.digest[-16:],
        request_id=request.request_id,
        requested_mode=mode,
        stages_requested=requested,
        stages_attempted=tuple(attempted),
        stages_skipped=stages_skipped,
        stage_summaries=tuple(stage_summaries),
        stop_reason=stop_reason,
        admission_status=admission_summary["admission_status"],
        preflight_status=preflight_status,
        transaction_plan_status=transaction_plan_status,
        transaction_plan_ready=transaction_ready,
        execution_status=execution_status,
        verification_status=verification_status,
        final_lifecycle_status=final_lifecycle_status,
        partial_state_visible=partial_state_visible,
        artifact_records=tuple(artifact_records),
        dry_run=mode == "dry_run_full_lifecycle",
    )
    result = replace(result, digest=_digest("workspace-change-set-lifecycle-orchestration-result-", result.to_dict()))
    o_path, o_digest = _write_json_artifact(orchestration_artifact_output_path, {"request": request, "result": result})
    if o_path and o_digest:
        artifact_records.append({"stage": "orchestration", "path": o_path, "digest": o_digest})
        result = replace(result, artifact_records=tuple(artifact_records), digest="")
        result = replace(result, digest=_digest("workspace-change-set-lifecycle-orchestration-result-", result.to_dict()))
    return WorkspaceChangeSetLifecycleOrchestrationWing(request, result, admission_wing, preflight_wing, execution_wing, verification_wing, closure_wing)


def summarize_workspace_change_set_lifecycle_orchestration_result(result: WorkspaceChangeSetLifecycleOrchestrationResult) -> dict[str, Any]:
    return {
        "orchestration_id": result.orchestration_id,
        "requested_mode": result.requested_mode,
        "stages_requested": result.stages_requested,
        "stages_attempted": result.stages_attempted,
        "stages_skipped": result.stages_skipped,
        "stage_statuses": tuple({"stage": stage.stage, "status": stage.status} for stage in result.stage_summaries),
        "stop_reason": result.stop_reason,
        "admission_status": result.admission_status,
        "preflight_status": result.preflight_status,
        "transaction_plan_status": result.transaction_plan_status,
        "transaction_plan_ready": result.transaction_plan_ready,
        "execution_status": result.execution_status,
        "verification_status": result.verification_status,
        "final_lifecycle_status": result.final_lifecycle_status,
        "partial_state_visible": result.partial_state_visible,
        "artifact_records": result.artifact_records,
        "non_authority_boundaries": result.non_authority_boundaries,
        "dry_run": result.dry_run,
        "target_write_performed_by_orchestrator": False,
        "target_file_read_performed_by_orchestrator": False,
        "target_digest_recomputed_by_orchestrator": False,
        "cleanup_performed": False,
        "external_tool_invoked": False,
        "digest": result.digest,
    }


__all__ = [
    "LIFECYCLE_MODES",
    "STOP_REASONS",
    "WorkspaceChangeSetLifecycleOrchestrationPolicy",
    "WorkspaceChangeSetLifecycleOrchestrationRequest",
    "WorkspaceChangeSetLifecycleStageSummary",
    "WorkspaceChangeSetLifecycleOrchestrationResult",
    "WorkspaceChangeSetLifecycleOrchestrationWing",
    "build_workspace_change_set_lifecycle_orchestration_request",
    "run_workspace_change_set_lifecycle_orchestration",
    "summarize_workspace_change_set_lifecycle_orchestration_result",
]
