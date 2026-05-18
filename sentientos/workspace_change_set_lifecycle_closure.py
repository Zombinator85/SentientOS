"""Metadata-only lifecycle closure manifests for workspace change-set evidence.

This wing consumes supplied preflight, execution, optional rollback/ledger/closure,
and verification evidence. It does not read workspace targets, recompute target
filesystem digests, execute, rollback, cleanup, schedule, recurse directories,
expand wildcards, call subprocess/shell/network/provider/prompt paths, or invoke
verification replay helpers. Verification proves what happened; this module seals
what the supplied lifecycle evidence means.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.workspace_change_set_execution import (
    BLOCKED_ACTION_LABELS,
    CLOSURE_STATUSES,
    ROLLBACK_EXECUTION_STATUSES,
    WorkspaceChangeSetExecutionClosureReport,
    WorkspaceChangeSetExecutionLedger,
    WorkspaceChangeSetExecutionReceipt,
    WorkspaceChangeSetExecutionRequest,
    WorkspaceChangeSetExecutionResult,
    WorkspaceChangeSetRollbackExecutionResult,
    WorkspaceChangeSetRollbackReceipt,
    deterministic_digest,
)
from sentientos.workspace_change_set_execution_verification import (
    VERIFICATION_STATUSES,
    WorkspaceChangeSetExecutionVerificationRequest,
    WorkspaceChangeSetExecutionVerificationResult,
    dataclass_from_dict,
)
from sentientos.workspace_change_set_preflight import (
    WorkspaceChangeSetManifest,
    WorkspaceChangeSetPreflightReport,
    WorkspaceChangeSetRollbackPlan,
    WorkspaceChangeSetTransactionPlan,
)

LIFECYCLE_CLOSURE_STATUSES = frozenset({
    "lifecycle_closed_clean",
    "lifecycle_closed_with_partial_state",
    "lifecycle_closed_after_rollback",
    "lifecycle_open",
    "lifecycle_blocked",
    "lifecycle_contradicted",
    "lifecycle_insufficient_evidence",
})

FORBIDDEN_LIFECYCLE_CLOSURE_ACTIONS = tuple(sorted(set(BLOCKED_ACTION_LABELS + (
    "workspace_change_set_execution",
    "workspace_change_set_rollback_execution",
    "workspace_change_set_execution_verification_replay",
    "workspace_file_effect_wing",
    "workspace_file_rollback_wing",
    "cleanup",
    "target_file_read",
    "target_digest_recompute",
    "directory_recursion",
    "wildcard_expansion",
    "scheduler",
))))

_REQUIRED_EVIDENCE = (
    "manifest",
    "preflight_report",
    "rollback_plan",
    "transaction_plan",
    "execution_request",
    "execution_result",
    "execution_receipt",
    "verification_result",
)


@dataclass(frozen=True)
class WorkspaceChangeSetLifecycleEvidenceSummary:
    manifest_id: str | None
    manifest_digest: str | None
    preflight_report_id: str | None
    preflight_report_digest: str | None
    rollback_plan_id: str | None
    rollback_plan_digest: str | None
    transaction_plan_id: str | None
    transaction_plan_digest: str | None
    execution_request_id: str | None
    execution_request_digest: str | None
    execution_result_id: str | None
    execution_result_digest: str | None
    execution_receipt_id: str | None
    execution_receipt_digest: str | None
    rollback_result_id: str | None
    rollback_result_digest: str | None
    rollback_receipt_id: str | None
    rollback_receipt_digest: str | None
    ledger_id: str | None
    ledger_digest: str | None
    closure_report_id: str | None
    closure_report_digest: str | None
    verification_request_id: str | None
    verification_request_digest: str | None
    verification_id: str | None
    verification_digest: str | None
    manifest_status: str | None
    preflight_status: str | None
    transaction_plan_status: str | None
    execution_request_status: str | None
    execution_status: str | None
    rollback_status: str | None
    receipt_status: str | None
    ledger_lifecycle_status: str | None
    closure_report_status: str | None
    verification_status: str | None
    declared_target_ids: tuple[str, ...]
    applied_target_ids: tuple[str, ...]
    failed_target_ids: tuple[str, ...]
    skipped_target_ids: tuple[str, ...]
    rolled_back_target_ids: tuple[str, ...]
    open_target_ids: tuple[str, ...]
    declared_target_count: int
    applied_target_count: int
    failed_target_count: int
    skipped_target_count: int
    rolled_back_target_count: int
    open_target_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetLifecycleClosureRequest:
    request_id: str
    source_manifest_id: str | None
    source_execution_result_id: str | None
    source_verification_id: str | None
    artifact_output_path: str | None = None
    closure_manifest_only: bool = True
    metadata_only: bool = True
    evidence_json_only: bool = True
    explicit_artifact_write_only: bool = True
    does_not_read_target_files: bool = True
    does_not_recompute_target_digests: bool = True
    does_not_execute: bool = True
    does_not_rollback: bool = True
    does_not_verify_replay: bool = True
    does_not_cleanup: bool = True
    does_not_schedule: bool = True
    future_authority_blocked_or_deferred: bool = True
    blocked_actions: tuple[str, ...] = FORBIDDEN_LIFECYCLE_CLOSURE_ACTIONS
    created_at: str = "1970-01-01T00:00:00+00:00"
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetLifecycleClosureManifest:
    closure_manifest_id: str
    request_id: str
    lifecycle_closure_status: str
    evidence_summary: WorkspaceChangeSetLifecycleEvidenceSummary
    receipt_consistency_posture: str
    ledger_consistency_posture: str
    closure_report_consistency_posture: str
    verification_consistency_posture: str
    contradiction_codes: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    unresolved_risk_codes: tuple[str, ...]
    finding_codes: tuple[str, ...]
    future_authority: str = "blocked_or_deferred"
    metadata_only: bool = True
    closure_manifest_only: bool = True
    non_authority_record: bool = True
    reads_supplied_evidence_only: bool = True
    target_file_read_performed: bool = False
    target_digest_recomputed_from_filesystem: bool = False
    execution_invoked: bool = False
    rollback_invoked: bool = False
    verification_replay_invoked: bool = False
    cleanup_performed: bool = False
    scheduler_invoked: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    artifact_path: str | None = None
    artifact_digest: str | None = None
    created_at: str = "1970-01-01T00:00:00+00:00"
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass(frozen=True)
class WorkspaceChangeSetLifecycleClosureResult:
    request_id: str
    closure_manifest_id: str
    lifecycle_closure_status: str
    closure_manifest_digest: str
    artifact_path: str | None
    artifact_digest: str | None
    contradiction_codes: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    unresolved_risk_codes: tuple[str, ...]
    metadata_only: bool = True
    no_execution_performed: bool = True
    no_rollback_performed: bool = True
    no_verification_replay_performed: bool = True
    no_target_file_read_performed: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkspaceChangeSetLifecycleClosureWingResult(NamedTuple):
    request: WorkspaceChangeSetLifecycleClosureRequest
    closure_manifest: WorkspaceChangeSetLifecycleClosureManifest
    closure_result: WorkspaceChangeSetLifecycleClosureResult


def _tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _digest(prefix: str, payload: Mapping[str, Any]) -> str:
    return deterministic_digest(prefix, payload)


def _record_digest(record: Any) -> str | None:
    return getattr(record, "digest", None) if record is not None else None


def _has_blocked_status(*statuses: str | None) -> bool:
    return any(status is not None and "blocked" in status for status in statuses)


def _status_invalid(status: str | None, allowed: frozenset[str]) -> bool:
    return bool(status and status not in allowed)


def build_workspace_change_set_lifecycle_closure_request(
    *,
    manifest: WorkspaceChangeSetManifest | None = None,
    execution_result: WorkspaceChangeSetExecutionResult | None = None,
    verification_result: WorkspaceChangeSetExecutionVerificationResult | None = None,
    artifact_output_path: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> WorkspaceChangeSetLifecycleClosureRequest:
    source_manifest_id = manifest.manifest_id if manifest else None
    source_execution_result_id = execution_result.result_id if execution_result else None
    source_verification_id = verification_result.verification_id if verification_result else None
    request = WorkspaceChangeSetLifecycleClosureRequest(
        request_id="workspace-change-set-lifecycle-closure-" + _digest("workspace-change-set-lifecycle-closure-request-id-", {
            "source_manifest_id": source_manifest_id,
            "source_execution_result_id": source_execution_result_id,
            "source_verification_id": source_verification_id,
            "artifact_output_path": artifact_output_path,
            "created_at": created_at,
        })[-16:],
        source_manifest_id=source_manifest_id,
        source_execution_result_id=source_execution_result_id,
        source_verification_id=source_verification_id,
        artifact_output_path=artifact_output_path,
        created_at=created_at,
    )
    return replace(request, digest=_digest("workspace-change-set-lifecycle-closure-request-", request.to_dict()))


def _summary(
    *,
    manifest: WorkspaceChangeSetManifest | None,
    preflight_report: WorkspaceChangeSetPreflightReport | None,
    rollback_plan: WorkspaceChangeSetRollbackPlan | None,
    transaction_plan: WorkspaceChangeSetTransactionPlan | None,
    execution_request: WorkspaceChangeSetExecutionRequest | None,
    execution_result: WorkspaceChangeSetExecutionResult | None,
    execution_receipt: WorkspaceChangeSetExecutionReceipt | None,
    rollback_result: WorkspaceChangeSetRollbackExecutionResult | None,
    rollback_receipt: WorkspaceChangeSetRollbackReceipt | None,
    ledger: WorkspaceChangeSetExecutionLedger | None,
    closure_report: WorkspaceChangeSetExecutionClosureReport | None,
    verification_request: WorkspaceChangeSetExecutionVerificationRequest | None,
    verification_result: WorkspaceChangeSetExecutionVerificationResult | None,
) -> WorkspaceChangeSetLifecycleEvidenceSummary:
    declared = tuple(target.target_id for target in manifest.targets) if manifest else ()
    applied = _tuple(getattr(closure_report, "applied_target_ids", None) or getattr(execution_result, "applied_target_ids", None))
    failed = _tuple(getattr(closure_report, "failed_target_ids", None) or getattr(execution_result, "failed_target_ids", None))
    skipped = _tuple(getattr(closure_report, "skipped_target_ids", None) or getattr(execution_result, "skipped_target_ids", None))
    rolled_back = _tuple(getattr(closure_report, "rolled_back_target_ids", None) or getattr(rollback_result, "rollback_target_ids", None))
    closure_open = _tuple(getattr(closure_report, "open_target_ids", None))
    closure_status = getattr(closure_report, "closure_status", None)
    if closure_status == "workspace_change_set_execution_closed_after_execute":
        open_ids = tuple(sorted(set(declared) - set(applied)))
    elif closure_status == "workspace_change_set_execution_closed_after_rollback":
        open_ids = tuple(sorted(set(declared) - set(rolled_back)))
    else:
        covered = set(applied) | set(failed) | set(skipped) | set(rolled_back) | set(closure_open)
        open_ids = tuple(sorted((set(declared) - covered) | set(closure_open)))
    return WorkspaceChangeSetLifecycleEvidenceSummary(
        manifest_id=getattr(manifest, "manifest_id", None), manifest_digest=_record_digest(manifest),
        preflight_report_id=getattr(preflight_report, "report_id", None), preflight_report_digest=_record_digest(preflight_report),
        rollback_plan_id=getattr(rollback_plan, "plan_id", None), rollback_plan_digest=_record_digest(rollback_plan),
        transaction_plan_id=getattr(transaction_plan, "plan_id", None), transaction_plan_digest=_record_digest(transaction_plan),
        execution_request_id=getattr(execution_request, "request_id", None), execution_request_digest=_record_digest(execution_request),
        execution_result_id=getattr(execution_result, "result_id", None), execution_result_digest=_record_digest(execution_result),
        execution_receipt_id=getattr(execution_receipt, "receipt_id", None), execution_receipt_digest=_record_digest(execution_receipt),
        rollback_result_id=getattr(rollback_result, "rollback_result_id", None), rollback_result_digest=_record_digest(rollback_result),
        rollback_receipt_id=getattr(rollback_receipt, "receipt_id", None), rollback_receipt_digest=_record_digest(rollback_receipt),
        ledger_id=getattr(ledger, "ledger_id", None), ledger_digest=_record_digest(ledger),
        closure_report_id=getattr(closure_report, "report_id", None), closure_report_digest=_record_digest(closure_report),
        verification_request_id=getattr(verification_request, "request_id", None), verification_request_digest=_record_digest(verification_request),
        verification_id=getattr(verification_result, "verification_id", None), verification_digest=_record_digest(verification_result),
        manifest_status=getattr(manifest, "manifest_status", None), preflight_status=getattr(preflight_report, "report_status", None),
        transaction_plan_status=getattr(transaction_plan, "transaction_plan_status", None), execution_request_status=getattr(execution_request, "request_status", None),
        execution_status=getattr(execution_result, "execution_status", None), rollback_status=getattr(rollback_result, "rollback_status", None),
        receipt_status=getattr(execution_receipt, "receipt_status", None), ledger_lifecycle_status=getattr(ledger, "lifecycle_status", None),
        closure_report_status=getattr(closure_report, "closure_status", None), verification_status=getattr(verification_result, "verification_status", None),
        declared_target_ids=declared, applied_target_ids=applied, failed_target_ids=failed, skipped_target_ids=skipped, rolled_back_target_ids=rolled_back, open_target_ids=open_ids,
        declared_target_count=len(declared), applied_target_count=len(applied), failed_target_count=len(failed), skipped_target_count=len(skipped), rolled_back_target_count=len(rolled_back), open_target_count=len(open_ids),
    )


def _findings(summary: WorkspaceChangeSetLifecycleEvidenceSummary, *, preflight_report: Any, rollback_plan: Any, transaction_plan: Any, execution_request: Any, execution_result: Any, execution_receipt: Any, rollback_result: Any, rollback_receipt: Any, ledger: Any, closure_report: Any, verification_request: Any, verification_result: Any) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    contradictions: list[str] = []
    blockers: list[str] = []
    risks: list[str] = []
    if preflight_report and summary.manifest_id != preflight_report.manifest_id:
        contradictions.append("manifest_preflight_id_mismatch")
    if rollback_plan:
        if summary.manifest_id != rollback_plan.manifest_id:
            contradictions.append("manifest_rollback_plan_id_mismatch")
        if summary.preflight_report_id != rollback_plan.preflight_report_id:
            contradictions.append("preflight_rollback_plan_id_mismatch")
    if transaction_plan:
        if summary.manifest_id != transaction_plan.manifest_id:
            contradictions.append("manifest_transaction_plan_id_mismatch")
        if summary.preflight_report_id != transaction_plan.preflight_report_id:
            contradictions.append("preflight_transaction_plan_id_mismatch")
        if summary.rollback_plan_id != transaction_plan.rollback_plan_id:
            contradictions.append("rollback_transaction_plan_id_mismatch")
    if execution_request:
        if summary.manifest_id != execution_request.source_manifest_id:
            contradictions.append("execution_request_manifest_id_mismatch")
        if summary.preflight_report_id != execution_request.source_preflight_report_id:
            contradictions.append("execution_request_preflight_id_mismatch")
        if summary.rollback_plan_id != execution_request.source_rollback_plan_id:
            contradictions.append("execution_request_rollback_plan_id_mismatch")
        if summary.transaction_plan_id != execution_request.source_transaction_plan_id:
            contradictions.append("execution_request_transaction_plan_id_mismatch")
    if execution_result and summary.execution_request_id != execution_result.request_id:
        contradictions.append("execution_result_request_id_mismatch")
    if execution_receipt:
        if summary.execution_request_id != execution_receipt.request_id:
            contradictions.append("execution_receipt_request_id_mismatch")
        if summary.execution_result_id != execution_receipt.result_id:
            contradictions.append("execution_receipt_result_id_mismatch")
    if rollback_result and summary.execution_result_id != rollback_result.source_execution_result_id:
        contradictions.append("rollback_result_execution_result_id_mismatch")
    if rollback_receipt:
        if summary.execution_receipt_id != rollback_receipt.source_execution_receipt_id:
            contradictions.append("rollback_receipt_execution_receipt_id_mismatch")
        if summary.rollback_result_id != rollback_receipt.rollback_result_id:
            contradictions.append("rollback_receipt_rollback_result_id_mismatch")
    if ledger:
        if summary.execution_request_id != ledger.request_id:
            contradictions.append("ledger_request_id_mismatch")
        if summary.execution_receipt_id != ledger.execution_receipt_id:
            contradictions.append("ledger_execution_receipt_id_mismatch")
        if ledger.rollback_receipt_id != summary.rollback_receipt_id:
            contradictions.append("ledger_rollback_receipt_id_mismatch")
    if closure_report:
        if closure_report.ledger_id != summary.ledger_id:
            contradictions.append("closure_report_ledger_id_mismatch")
        if closure_report.execution_receipt_id != summary.execution_receipt_id:
            contradictions.append("closure_report_execution_receipt_id_mismatch")
        if closure_report.rollback_receipt_id != summary.rollback_receipt_id:
            contradictions.append("closure_report_rollback_receipt_id_mismatch")
    if verification_request:
        if verification_request.source_manifest_id != summary.manifest_id:
            contradictions.append("verification_request_manifest_id_mismatch")
        if verification_request.source_execution_request_id != summary.execution_request_id:
            contradictions.append("verification_request_execution_request_id_mismatch")
        if verification_request.source_execution_result_id != summary.execution_result_id:
            contradictions.append("verification_request_execution_result_id_mismatch")
        if verification_request.source_execution_receipt_id != summary.execution_receipt_id:
            contradictions.append("verification_request_execution_receipt_id_mismatch")
    if verification_result:
        if verification_request and verification_result.request_id != verification_request.request_id:
            contradictions.append("verification_result_request_id_mismatch")
        if _status_invalid(verification_result.verification_status, VERIFICATION_STATUSES):
            contradictions.append("verification_status_unknown")
        contradictions.extend(code for code in verification_result.finding_codes if "contradiction" in code or "mismatch" in code)
    else:
        blockers.append("verification_result_missing")
    if closure_report and _status_invalid(closure_report.closure_status, CLOSURE_STATUSES):
        contradictions.append("closure_status_unknown")
    if rollback_result and _status_invalid(rollback_result.rollback_status, ROLLBACK_EXECUTION_STATUSES):
        contradictions.append("rollback_status_unknown")
    statuses = (summary.manifest_status, summary.preflight_status, summary.transaction_plan_status, summary.execution_request_status, summary.execution_status, summary.rollback_status, summary.receipt_status, summary.ledger_lifecycle_status, summary.closure_report_status, summary.verification_status)
    if _has_blocked_status(*statuses):
        blockers.append("blocked_status_present")
    for record in (getattr(preflight_report, "risk_codes", ()), getattr(rollback_plan, "risk_codes", ()), getattr(transaction_plan, "risk_codes", ()), getattr(execution_request, "risk_codes", ()), getattr(execution_result, "risk_codes", ()), getattr(execution_receipt, "risk_codes", ()), getattr(rollback_result, "risk_codes", ()), getattr(rollback_receipt, "risk_codes", ()), getattr(ledger, "risk_codes", ()), getattr(closure_report, "risk_codes", ())):
        risks.extend(_tuple(record))
    unknown_ids = set(summary.applied_target_ids + summary.failed_target_ids + summary.skipped_target_ids + summary.rolled_back_target_ids + summary.open_target_ids) - set(summary.declared_target_ids)
    if unknown_ids:
        contradictions.append("unknown_target_ids:" + ",".join(sorted(unknown_ids)))
    return tuple(sorted(set(contradictions))), tuple(sorted(set(blockers))), tuple(sorted(set(risks)))


def _classify(summary: WorkspaceChangeSetLifecycleEvidenceSummary, contradictions: tuple[str, ...], blockers: tuple[str, ...]) -> str:
    if contradictions:
        return "lifecycle_contradicted"
    if any(not (code == "verification_result_missing" or code.startswith("missing_evidence:")) for code in blockers) or summary.verification_status == "verification_blocked":
        return "lifecycle_blocked"
    if summary.verification_status in (None, "insufficient_evidence") or any(code.startswith("missing_evidence:") for code in blockers):
        return "lifecycle_insufficient_evidence"
    if summary.verification_status == "verification_failed":
        return "lifecycle_contradicted"
    if summary.verification_status == "verified_rolled_back":
        return "lifecycle_closed_after_rollback"
    if summary.verification_status == "verified_with_partial_state":
        return "lifecycle_closed_with_partial_state"
    if summary.verification_status == "verified_clean" and summary.failed_target_count == 0 and summary.skipped_target_count == 0 and summary.open_target_count == 0:
        return "lifecycle_closed_clean"
    if summary.open_target_count or summary.failed_target_count or summary.skipped_target_count:
        return "lifecycle_open"
    return "lifecycle_insufficient_evidence"


def _posture(codes: tuple[str, ...], prefix: str) -> str:
    return "consistent" if not any(code.startswith(prefix) for code in codes) else "contradicted"


def build_workspace_change_set_lifecycle_closure_manifest(
    *,
    manifest: WorkspaceChangeSetManifest | None = None,
    preflight_report: WorkspaceChangeSetPreflightReport | None = None,
    rollback_plan: WorkspaceChangeSetRollbackPlan | None = None,
    transaction_plan: WorkspaceChangeSetTransactionPlan | None = None,
    execution_request: WorkspaceChangeSetExecutionRequest | None = None,
    execution_result: WorkspaceChangeSetExecutionResult | None = None,
    execution_receipt: WorkspaceChangeSetExecutionReceipt | None = None,
    rollback_result: WorkspaceChangeSetRollbackExecutionResult | None = None,
    rollback_receipt: WorkspaceChangeSetRollbackReceipt | None = None,
    ledger: WorkspaceChangeSetExecutionLedger | None = None,
    closure_report: WorkspaceChangeSetExecutionClosureReport | None = None,
    verification_request: WorkspaceChangeSetExecutionVerificationRequest | None = None,
    verification_result: WorkspaceChangeSetExecutionVerificationResult | None = None,
    artifact_output_path: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> WorkspaceChangeSetLifecycleClosureWingResult:
    request = build_workspace_change_set_lifecycle_closure_request(manifest=manifest, execution_result=execution_result, verification_result=verification_result, artifact_output_path=artifact_output_path, created_at=created_at)
    evidence_by_name = {
        "manifest": manifest,
        "preflight_report": preflight_report,
        "rollback_plan": rollback_plan,
        "transaction_plan": transaction_plan,
        "execution_request": execution_request,
        "execution_result": execution_result,
        "execution_receipt": execution_receipt,
        "verification_result": verification_result,
    }
    missing = tuple(name for name in _REQUIRED_EVIDENCE if evidence_by_name.get(name) is None)
    summary = _summary(manifest=manifest, preflight_report=preflight_report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, execution_request=execution_request, execution_result=execution_result, execution_receipt=execution_receipt, rollback_result=rollback_result, rollback_receipt=rollback_receipt, ledger=ledger, closure_report=closure_report, verification_request=verification_request, verification_result=verification_result)
    contradictions, blockers, risks = _findings(summary, preflight_report=preflight_report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, execution_request=execution_request, execution_result=execution_result, execution_receipt=execution_receipt, rollback_result=rollback_result, rollback_receipt=rollback_receipt, ledger=ledger, closure_report=closure_report, verification_request=verification_request, verification_result=verification_result)
    if missing:
        blockers = tuple(sorted(set(blockers + tuple("missing_evidence:" + item for item in missing))))
    status = _classify(summary, contradictions, blockers)
    finding_codes = tuple(sorted(set(contradictions + blockers + risks)))
    manifest_record = WorkspaceChangeSetLifecycleClosureManifest(
        closure_manifest_id="workspace-change-set-lifecycle-closure-manifest-" + request.digest[-16:],
        request_id=request.request_id,
        lifecycle_closure_status=status,
        evidence_summary=summary,
        receipt_consistency_posture=_posture(contradictions, "execution_receipt"),
        ledger_consistency_posture=_posture(contradictions, "ledger"),
        closure_report_consistency_posture=_posture(contradictions, "closure_report"),
        verification_consistency_posture=_posture(contradictions, "verification"),
        contradiction_codes=contradictions,
        blocker_codes=blockers,
        unresolved_risk_codes=risks,
        finding_codes=finding_codes,
        artifact_path=artifact_output_path,
        created_at=created_at,
    )
    manifest_record = replace(manifest_record, digest=_digest("workspace-change-set-lifecycle-closure-manifest-", manifest_record.to_dict()))
    artifact_digest: str | None = None
    if artifact_output_path:
        payload = json.dumps(manifest_record.to_dict(), indent=2, sort_keys=True)
        Path(artifact_output_path).write_text(payload, encoding="utf-8")
        artifact_digest = "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
    result = WorkspaceChangeSetLifecycleClosureResult(
        request_id=request.request_id,
        closure_manifest_id=manifest_record.closure_manifest_id,
        lifecycle_closure_status=status,
        closure_manifest_digest=manifest_record.digest,
        artifact_path=artifact_output_path,
        artifact_digest=artifact_digest,
        contradiction_codes=contradictions,
        blocker_codes=blockers,
        unresolved_risk_codes=risks,
    )
    result = replace(result, digest=_digest("workspace-change-set-lifecycle-closure-result-", result.to_dict()))
    return WorkspaceChangeSetLifecycleClosureWingResult(request, manifest_record, result)


def summarize_workspace_change_set_lifecycle_closure_manifest(manifest: WorkspaceChangeSetLifecycleClosureManifest) -> dict[str, Any]:
    return {
        "closure_manifest_id": manifest.closure_manifest_id,
        "lifecycle_closure_status": manifest.lifecycle_closure_status,
        "declared_target_count": manifest.evidence_summary.declared_target_count,
        "applied_target_count": manifest.evidence_summary.applied_target_count,
        "failed_target_count": manifest.evidence_summary.failed_target_count,
        "skipped_target_count": manifest.evidence_summary.skipped_target_count,
        "rolled_back_target_count": manifest.evidence_summary.rolled_back_target_count,
        "open_target_count": manifest.evidence_summary.open_target_count,
        "verification_status": manifest.evidence_summary.verification_status,
        "contradiction_codes": manifest.contradiction_codes,
        "blocker_codes": manifest.blocker_codes,
        "unresolved_risk_codes": manifest.unresolved_risk_codes,
        "metadata_only": True,
        "target_file_read_performed": False,
        "execution_invoked": False,
        "rollback_invoked": False,
        "verification_replay_invoked": False,
        "cleanup_performed": False,
    }


def lifecycle_closure_evidence_from_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    if "preflight" in payload and isinstance(payload["preflight"], Mapping):
        preflight = payload["preflight"]
        payload = {**payload, "manifest": preflight.get("manifest"), "preflight_report": preflight.get("preflight_report"), "rollback_plan": preflight.get("rollback_plan"), "transaction_plan": preflight.get("transaction_plan")}
    return {
        "manifest": dataclass_from_dict(WorkspaceChangeSetManifest, payload["manifest"]) if payload.get("manifest") else None,
        "preflight_report": dataclass_from_dict(WorkspaceChangeSetPreflightReport, payload["preflight_report"]) if payload.get("preflight_report") else None,
        "rollback_plan": dataclass_from_dict(WorkspaceChangeSetRollbackPlan, payload["rollback_plan"]) if payload.get("rollback_plan") else None,
        "transaction_plan": dataclass_from_dict(WorkspaceChangeSetTransactionPlan, payload["transaction_plan"]) if payload.get("transaction_plan") else None,
        "execution_request": dataclass_from_dict(WorkspaceChangeSetExecutionRequest, payload.get("execution_request", payload.get("request", {}))) if payload.get("execution_request") or payload.get("request") else None,
        "execution_result": dataclass_from_dict(WorkspaceChangeSetExecutionResult, payload["execution_result"]) if payload.get("execution_result") else None,
        "execution_receipt": dataclass_from_dict(WorkspaceChangeSetExecutionReceipt, payload["execution_receipt"]) if payload.get("execution_receipt") else None,
        "rollback_result": dataclass_from_dict(WorkspaceChangeSetRollbackExecutionResult, payload["rollback_result"]) if payload.get("rollback_result") else None,
        "rollback_receipt": dataclass_from_dict(WorkspaceChangeSetRollbackReceipt, payload["rollback_receipt"]) if payload.get("rollback_receipt") else None,
        "ledger": dataclass_from_dict(WorkspaceChangeSetExecutionLedger, payload["ledger"]) if payload.get("ledger") else None,
        "closure_report": dataclass_from_dict(WorkspaceChangeSetExecutionClosureReport, payload["closure_report"]) if payload.get("closure_report") else None,
        "verification_request": dataclass_from_dict(WorkspaceChangeSetExecutionVerificationRequest, payload.get("verification_request", payload.get("verification", {}).get("request", {}))) if payload.get("verification_request") or (isinstance(payload.get("verification"), Mapping) and payload["verification"].get("request")) else None,
        "verification_result": dataclass_from_dict(WorkspaceChangeSetExecutionVerificationResult, payload.get("verification_result", payload.get("verification", {}).get("verification_result", {}))) if payload.get("verification_result") or (isinstance(payload.get("verification"), Mapping) and payload["verification"].get("verification_result")) else None,
    }


def load_lifecycle_closure_evidence(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return lifecycle_closure_evidence_from_mapping(payload)
