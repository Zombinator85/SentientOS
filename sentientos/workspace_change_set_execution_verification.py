"""Read-only verification and replay audit for workspace change-set executions.

This wing consumes existing change-set manifest/preflight/transaction/execution
and optional rollback/ledger/closure evidence. It recomputes digests only for the
explicit manifest targets and never invokes execution, rollback, cleanup,
subprocess, shell, network, provider, prompt, service, power, fan/PWM, thermal,
plugin, generated-code, federation, or external-tool paths.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence, TypeVar, get_args, get_origin, cast, get_type_hints

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
    WorkspaceChangeTargetExecutionResult,
    deterministic_digest,
    validate_workspace_change_set_execution_closure_report,
    validate_workspace_change_set_execution_ledger,
    validate_workspace_change_set_execution_receipt,
    validate_workspace_change_set_execution_request,
    validate_workspace_change_set_execution_result,
    validate_workspace_change_set_rollback_execution_result,
    validate_workspace_change_set_rollback_receipt,
    validate_workspace_change_target_execution_result,
)
from sentientos.workspace_change_set_preflight import (
    WorkspaceChangeSetManifest,
    WorkspaceChangeSetPreflightReport,
    WorkspaceChangeSetRollbackPlan,
    WorkspaceChangeSetTransactionPlan,
    WorkspaceChangeTargetDeclaration,
    file_digest,
)

VERIFICATION_STATUSES = frozenset({
    "verified_clean",
    "verified_with_partial_state",
    "verified_rolled_back",
    "verification_failed",
    "verification_blocked",
    "insufficient_evidence",
})
TARGET_VERIFICATION_STATUSES = frozenset({
    "target_verified_postcondition",
    "target_verified_rollback_preimage",
    "target_verified_rollback_absence",
    "target_verified_failed_visible",
    "target_verified_skipped_visible",
    "target_verification_failed",
    "target_verification_blocked",
    "target_insufficient_evidence",
})
FORBIDDEN_VERIFIER_ACTIONS = tuple(sorted(set(BLOCKED_ACTION_LABELS + (
    "workspace_change_set_execution",
    "workspace_change_set_rollback_execution",
    "workspace_file_effect_wing",
    "workspace_file_rollback_wing",
    "cleanup",
    "target_payload_execution",
    "directory_recursion",
    "wildcard_expansion",
))))


@dataclass(frozen=True)
class WorkspaceChangeSetExecutionVerificationRequest:
    request_id: str
    source_manifest_id: str
    source_execution_request_id: str
    source_execution_result_id: str
    source_execution_receipt_id: str
    workspace_root: str
    declared_target_ids: tuple[str, ...]
    planned_target_order: tuple[str, ...]
    rollback_target_order: tuple[str, ...]
    audit_output_path: str | None = None
    verification_only: bool = True
    read_only_except_optional_audit_artifact: bool = True
    explicit_targets_only: bool = True
    does_not_execute: bool = True
    does_not_rollback: bool = True
    does_not_cleanup: bool = True
    blocked_actions: tuple[str, ...] = FORBIDDEN_VERIFIER_ACTIONS
    created_at: str = "1970-01-01T00:00:00+00:00"
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeTargetVerificationRecord:
    target_id: str
    relative_target_path: str
    target_verification_status: str
    expected_digest: str | None
    observed_digest: str | None
    expected_absent: bool
    observed_exists: bool
    execution_status: str | None
    rollback_status: str | None
    basis: tuple[str, ...]
    finding_codes: tuple[str, ...]
    read_only: bool = True
    target_write_performed: bool = False
    rollback_performed: bool = False
    cleanup_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetExecutionVerificationResult:
    verification_id: str
    request_id: str
    verification_status: str
    basis: tuple[str, ...]
    target_records: tuple[WorkspaceChangeTargetVerificationRecord, ...]
    receipt_consistency: tuple[str, ...]
    ledger_consistency: tuple[str, ...]
    closure_consistency: tuple[str, ...]
    postcondition_digest_agreement: bool
    rollback_digest_agreement: bool | None
    partial_state_visible: bool
    unknown_target_ids: tuple[str, ...]
    finding_codes: tuple[str, ...]
    audit_artifact_path: str | None
    audit_artifact_digest: str | None
    verification_only: bool = True
    read_only_except_optional_audit_artifact: bool = True
    explicit_targets_only: bool = True
    execution_invoked: bool = False
    rollback_invoked: bool = False
    cleanup_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkspaceChangeSetExecutionVerificationWingResult(NamedTuple):
    request: WorkspaceChangeSetExecutionVerificationRequest
    verification_result: WorkspaceChangeSetExecutionVerificationResult


def _digest(prefix: str, payload: Mapping[str, Any]) -> str:
    return deterministic_digest(prefix, payload)


def build_workspace_change_set_execution_verification_request(
    *,
    manifest: WorkspaceChangeSetManifest,
    execution_request: WorkspaceChangeSetExecutionRequest,
    execution_result: WorkspaceChangeSetExecutionResult,
    execution_receipt: WorkspaceChangeSetExecutionReceipt,
    transaction_plan: WorkspaceChangeSetTransactionPlan,
    rollback_result: WorkspaceChangeSetRollbackExecutionResult | None = None,
    audit_output_path: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> WorkspaceChangeSetExecutionVerificationRequest:
    rollback_order = tuple(rollback_result.rollback_target_order if rollback_result else ())
    record = WorkspaceChangeSetExecutionVerificationRequest(
        request_id=f"workspace-change-set-execution-verification-request-{execution_result.result_id}",
        source_manifest_id=manifest.manifest_id,
        source_execution_request_id=execution_request.request_id,
        source_execution_result_id=execution_result.result_id,
        source_execution_receipt_id=execution_receipt.receipt_id,
        workspace_root=manifest.workspace_root,
        declared_target_ids=tuple(target.target_id for target in manifest.targets),
        planned_target_order=tuple(transaction_plan.planned_target_order),
        rollback_target_order=rollback_order,
        audit_output_path=audit_output_path,
        created_at=created_at,
    )
    return replace(record, digest=_digest("workspace-change-set-execution-verification-request-", record.to_dict()))


def _normalize_relative(path_text: str) -> str:
    parts = [part for part in str(path_text).replace("\\", "/").split("/") if part not in {"", "."}]
    return "/".join(parts)


def _target_path(root: Path, relative: str) -> Path:
    return root / _normalize_relative(relative)


def _rollback_entries_by_id(plan: WorkspaceChangeSetRollbackPlan) -> dict[str, Mapping[str, Any]]:
    return {str(entry.get("target_id")): entry for entry in plan.target_rollback_entries if isinstance(entry, Mapping) and entry.get("target_id")}


def _status_by_rollback_target(rollback_result: WorkspaceChangeSetRollbackExecutionResult | None) -> dict[str, str]:
    if not rollback_result:
        return {}
    statuses: dict[str, str] = {}
    for entry in rollback_result.rollback_status_by_target:
        if isinstance(entry, Mapping) and entry.get("target_id"):
            statuses[str(entry["target_id"])] = str(entry.get("rollback_status", ""))
    return statuses


def _collect_target_ids(*values: Any) -> set[str]:
    ids: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            ids.add(value)
        elif isinstance(value, Mapping):
            for key in ("target_id",):
                if value.get(key):
                    ids.add(str(value[key]))
        elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            ids.update(_collect_target_ids(*value))
        elif hasattr(value, "target_id"):
            ids.add(str(value.target_id))
    return ids


def _validate_digest(record: Any, prefix: str) -> tuple[bool, str]:
    payload = record.to_dict() if hasattr(record, "to_dict") else asdict(record)
    expected = _digest(prefix, payload)
    observed = str(payload.get("digest", ""))
    return observed == expected, observed


def _append_validation(findings: list[str], label: str, validation: Any) -> None:
    if not getattr(validation, "ok", False):
        findings.extend(f"{label}:{item}" for item in getattr(validation, "findings", ()))


def _safe_audit_output(path_text: str, declared_paths: set[Path]) -> tuple[bool, str]:
    path = Path(path_text).expanduser()
    if not path_text or path_text.strip() == "":
        return False, "audit_output_path_required"
    if path.exists() and path.is_dir():
        return False, "audit_output_path_is_directory"
    if path.is_symlink():
        return False, "audit_output_path_is_symlink"
    if not path.parent.exists():
        return False, "audit_output_parent_missing"
    resolved = path.resolve(strict=False)
    if any(resolved == declared.resolve(strict=False) for declared in declared_paths):
        return False, "audit_output_matches_declared_target"
    return True, ""


def _write_audit_artifact(result: WorkspaceChangeSetExecutionVerificationResult, request: WorkspaceChangeSetExecutionVerificationRequest, declared_paths: set[Path]) -> tuple[str | None, str | None, tuple[str, ...]]:
    if not request.audit_output_path:
        return None, None, ()
    ok, reason = _safe_audit_output(request.audit_output_path, declared_paths)
    if not ok:
        return None, None, (reason,)
    payload = {
        "metadata_only": True,
        "workspace_change_set_execution_verification_only": True,
        "read_only_except_this_explicit_artifact": True,
        "request": request.to_dict(),
        "verification_result": result.to_dict(),
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    Path(request.audit_output_path).write_text(text, encoding="utf-8")
    return request.audit_output_path, "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(), ()


def _target_record(
    *,
    root: Path,
    target: WorkspaceChangeTargetDeclaration,
    rollback_entry: Mapping[str, Any] | None,
    execution_record: WorkspaceChangeTargetExecutionResult | None,
    applied: set[str],
    failed: set[str],
    skipped: set[str],
    rolled_back: set[str],
    rollback_status_by_target: Mapping[str, str],
) -> WorkspaceChangeTargetVerificationRecord:
    findings: list[str] = []
    basis: list[str] = ["manifest_declared_target"]
    path = _target_path(root, target.relative_target_path)
    observed_exists = path.exists()
    observed_digest: str | None = None
    if observed_exists and path.is_file() and not path.is_symlink():
        observed_digest, _size = file_digest(path)
        basis.append("declared_target_digest_recomputed")
    elif observed_exists:
        findings.append("declared_target_not_plain_file")

    tid = target.target_id
    execution_status = execution_record.target_execution_status if execution_record else None
    rollback_status = rollback_status_by_target.get(tid)
    expected_digest: str | None = None
    expected_absent = False

    if execution_record is None:
        findings.append("missing_per_target_execution_record")
        status = "target_insufficient_evidence"
    elif tid in rolled_back:
        basis.append("rollback_evidence_visible")
        existed_before = bool(rollback_entry.get("existed_before")) if rollback_entry else False
        existing_digest = str(rollback_entry.get("existing_digest")) if rollback_entry and rollback_entry.get("existing_digest") else None
        if existed_before:
            expected_digest = existing_digest
            if not expected_digest:
                findings.append("missing_rollback_preimage_digest")
            elif observed_digest != expected_digest:
                findings.append("rollback_preimage_digest_mismatch")
        else:
            expected_absent = True
            if observed_exists:
                findings.append("rollback_expected_absent_target_exists")
        status = "target_verified_rollback_preimage" if existed_before else "target_verified_rollback_absence"
    elif tid in applied:
        basis.append("postcondition_evidence_visible")
        expected_digest = str(rollback_entry.get("expected_post_write_digest")) if rollback_entry and rollback_entry.get("expected_post_write_digest") else target.digest
        if not observed_exists:
            findings.append("applied_target_missing")
        elif observed_digest != expected_digest:
            findings.append("postcondition_digest_mismatch")
        status = "target_verified_postcondition"
    elif tid in failed:
        basis.append("failed_target_visible")
        status = "target_verified_failed_visible"
    elif tid in skipped:
        basis.append("skipped_target_visible")
        status = "target_verified_skipped_visible"
    else:
        findings.append("target_not_classified_by_execution_evidence")
        status = "target_insufficient_evidence"

    if findings and status not in {"target_insufficient_evidence", "target_verification_blocked"}:
        status = "target_verification_failed"
    return WorkspaceChangeTargetVerificationRecord(
        target_id=tid,
        relative_target_path=target.relative_target_path,
        target_verification_status=status,
        expected_digest=expected_digest,
        observed_digest=observed_digest,
        expected_absent=expected_absent,
        observed_exists=observed_exists,
        execution_status=execution_status,
        rollback_status=rollback_status,
        basis=tuple(basis),
        finding_codes=tuple(sorted(set(findings))),
    )


def verify_workspace_change_set_execution(
    *,
    manifest: WorkspaceChangeSetManifest,
    preflight_report: WorkspaceChangeSetPreflightReport,
    rollback_plan: WorkspaceChangeSetRollbackPlan,
    transaction_plan: WorkspaceChangeSetTransactionPlan,
    execution_request: WorkspaceChangeSetExecutionRequest,
    execution_result: WorkspaceChangeSetExecutionResult,
    execution_receipt: WorkspaceChangeSetExecutionReceipt,
    rollback_result: WorkspaceChangeSetRollbackExecutionResult | None = None,
    rollback_receipt: WorkspaceChangeSetRollbackReceipt | None = None,
    ledger: WorkspaceChangeSetExecutionLedger | None = None,
    closure_report: WorkspaceChangeSetExecutionClosureReport | None = None,
    audit_output_path: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> WorkspaceChangeSetExecutionVerificationWingResult:
    request = build_workspace_change_set_execution_verification_request(
        manifest=manifest,
        execution_request=execution_request,
        execution_result=execution_result,
        execution_receipt=execution_receipt,
        transaction_plan=transaction_plan,
        rollback_result=rollback_result,
        audit_output_path=audit_output_path,
        created_at=created_at,
    )
    findings: list[str] = []
    basis: list[str] = ["metadata_evidence_supplied", "read_only_declared_target_digest_replay"]
    receipt_consistency: list[str] = []
    ledger_consistency: list[str] = []
    closure_consistency: list[str] = []

    declared_ids = tuple(target.target_id for target in manifest.targets)
    declared_set = set(declared_ids)
    root = Path(manifest.workspace_root).expanduser()
    target_by_id = {target.target_id: target for target in manifest.targets}
    execution_by_id = {record.target_id: record for record in execution_result.target_results}
    rollback_entries = _rollback_entries_by_id(rollback_plan)
    rollback_status_by_target = _status_by_rollback_target(rollback_result)

    if preflight_report.manifest_id != manifest.manifest_id:
        findings.append("preflight_manifest_mismatch")
    if rollback_plan.manifest_id != manifest.manifest_id or rollback_plan.preflight_report_id != preflight_report.report_id:
        findings.append("rollback_plan_source_mismatch")
    if transaction_plan.manifest_id != manifest.manifest_id or transaction_plan.rollback_plan_id != rollback_plan.plan_id:
        findings.append("transaction_plan_source_mismatch")
    if execution_request.source_manifest_id != manifest.manifest_id or execution_request.source_transaction_plan_id != transaction_plan.plan_id:
        findings.append("execution_request_source_mismatch")
    if execution_result.request_id != execution_request.request_id or execution_receipt.request_id != execution_request.request_id or execution_receipt.result_id != execution_result.result_id:
        findings.append("execution_receipt_result_request_mismatch")

    if tuple(execution_request.target_order) != tuple(transaction_plan.planned_target_order):
        findings.append("planned_target_order_not_preserved")
    if tuple(transaction_plan.planned_target_order) != declared_ids:
        findings.append("planned_target_order_differs_from_manifest_order")

    for label, record, prefix in (
        ("execution_request", execution_request, "workspace-change-set-execution-request-"),
        ("execution_result", execution_result, "workspace-change-set-execution-result-"),
        ("execution_receipt", execution_receipt, "workspace-change-set-execution-receipt-"),
    ):
        ok, _observed = _validate_digest(record, prefix)
        if not ok:
            findings.append(f"{label}_digest_mismatch")
    for target_execution_record in execution_result.target_results:
        ok, _observed = _validate_digest(target_execution_record, "workspace-change-target-execution-result-")
        if not ok:
            findings.append(f"target_execution_digest_mismatch:{target_execution_record.target_id}")

    _append_validation(findings, "execution_request", validate_workspace_change_set_execution_request(execution_request))
    _append_validation(findings, "execution_result", validate_workspace_change_set_execution_result(execution_result))
    _append_validation(findings, "execution_receipt", validate_workspace_change_set_execution_receipt(execution_receipt))
    for target_execution_record in execution_result.target_results:
        _append_validation(findings, f"target:{target_execution_record.target_id}", validate_workspace_change_target_execution_result(target_execution_record))

    receipt_expected = {
        "applied": tuple(execution_result.applied_target_ids),
        "failed": tuple(execution_result.failed_target_ids),
        "skipped": tuple(execution_result.skipped_target_ids),
        "produced_record_ids": tuple(execution_result.produced_record_ids),
        "produced_record_digests": tuple(execution_result.produced_record_digests),
        "produced_paths": tuple(execution_result.produced_paths),
    }
    receipt_observed = {
        "applied": tuple(execution_receipt.applied_target_ids),
        "failed": tuple(execution_receipt.failed_target_ids),
        "skipped": tuple(execution_receipt.skipped_target_ids),
        "produced_record_ids": tuple(execution_receipt.produced_record_ids),
        "produced_record_digests": tuple(execution_receipt.produced_record_digests),
        "produced_paths": tuple(execution_receipt.produced_paths),
    }
    if receipt_expected == receipt_observed:
        receipt_consistency.append("execution_receipt_matches_result_lists")
    else:
        findings.append("execution_receipt_lists_mismatch")

    if len(execution_result.produced_record_ids) != len(execution_result.produced_record_digests):
        findings.append("produced_record_id_digest_count_mismatch")
    if any(not item for item in execution_result.produced_record_ids + execution_result.produced_record_digests):
        findings.append("missing_produced_record_id_or_digest")

    applied = set(execution_result.applied_target_ids)
    failed = set(execution_result.failed_target_ids)
    skipped = set(execution_result.skipped_target_ids)
    rolled_back = set(rollback_result.rollback_target_ids if rollback_result else ())

    evidence_ids = set(execution_by_id) | applied | failed | skipped | set(rollback_entries) | rolled_back | set(rollback_status_by_target)
    if ledger:
        evidence_ids |= _collect_target_ids(ledger.target_event_entries)
    if closure_report:
        evidence_ids |= set(closure_report.applied_target_ids + closure_report.rolled_back_target_ids + closure_report.open_target_ids + closure_report.failed_target_ids + closure_report.skipped_target_ids)
    unknown_ids = tuple(sorted(evidence_ids - declared_set))
    if unknown_ids:
        findings.append("unknown_target_evidence")
    missing_execution_records = tuple(target_id for target_id in declared_ids if target_id not in execution_by_id)
    if missing_execution_records:
        findings.append("missing_declared_target_execution_record")

    if rollback_result:
        _append_validation(findings, "rollback_result", validate_workspace_change_set_rollback_execution_result(rollback_result))
        ok, _observed = _validate_digest(rollback_result, "workspace-change-set-rollback-result-")
        if not ok:
            findings.append("rollback_result_digest_mismatch")
        if rollback_result.rollback_performed and tuple(rollback_result.rollback_target_order) != tuple(reversed(execution_result.applied_target_ids)):
            findings.append("rollback_order_not_reverse_applied_order")
        if rollback_receipt:
            _append_validation(findings, "rollback_receipt", validate_workspace_change_set_rollback_receipt(rollback_receipt))
            ok, _observed = _validate_digest(rollback_receipt, "workspace-change-set-rollback-receipt-")
            if not ok:
                findings.append("rollback_receipt_digest_mismatch")
            if tuple(rollback_receipt.rollback_target_order) != tuple(rollback_result.rollback_target_order):
                findings.append("rollback_receipt_order_mismatch")
        elif rollback_result.rollback_performed:
            findings.append("missing_rollback_receipt")
    elif rollback_receipt:
        findings.append("rollback_receipt_without_rollback_result")

    target_records = tuple(
        _target_record(
            root=root,
            target=target,
            rollback_entry=rollback_entries.get(target.target_id),
            execution_record=execution_by_id.get(target.target_id),
            applied=applied,
            failed=failed,
            skipped=skipped,
            rolled_back=rolled_back,
            rollback_status_by_target=rollback_status_by_target,
        )
        for target in manifest.targets
    )
    for target_record in target_records:
        findings.extend(f"{target_record.target_id}:{code}" for code in target_record.finding_codes)

    if ledger:
        _append_validation(findings, "ledger", validate_workspace_change_set_execution_ledger(ledger))
        ok, _observed = _validate_digest(ledger, "workspace-change-set-execution-ledger-")
        if not ok:
            findings.append("ledger_digest_mismatch")
        if ledger.request_id != execution_request.request_id or ledger.execution_receipt_id != execution_receipt.receipt_id:
            findings.append("ledger_source_mismatch")
        if ledger.execution_status != execution_result.execution_status:
            findings.append("ledger_execution_status_stale")
        expected_rb_status = rollback_result.rollback_status if rollback_result and rollback_result.rollback_status != "workspace_change_set_rollback_not_requested" else None
        if ledger.rollback_status != expected_rb_status:
            findings.append("ledger_rollback_status_stale")
        ledger_order = tuple(str(entry.get("target_id")) for entry in ledger.target_event_entries if isinstance(entry, Mapping) and entry.get("target_id"))
        if ledger_order == tuple(record.target_id for record in execution_result.target_results):
            ledger_consistency.append("ledger_target_order_matches_execution_result")
        else:
            findings.append("ledger_target_order_mismatch")
    else:
        ledger_consistency.append("ledger_not_supplied")

    if closure_report:
        _append_validation(findings, "closure_report", validate_workspace_change_set_execution_closure_report(closure_report))
        ok, _observed = _validate_digest(closure_report, "workspace-change-set-execution-closure-")
        if not ok:
            findings.append("closure_report_digest_mismatch")
        if closure_report.execution_receipt_id != execution_receipt.receipt_id:
            findings.append("closure_report_receipt_mismatch")
        expected_open = tuple(target_id for target_id in execution_result.applied_target_ids if target_id not in rolled_back)
        if tuple(closure_report.open_target_ids) != expected_open:
            findings.append("closure_open_targets_contradict_evidence")
        if tuple(closure_report.failed_target_ids) != tuple(execution_result.failed_target_ids) or tuple(closure_report.skipped_target_ids) != tuple(execution_result.skipped_target_ids):
            findings.append("closure_failed_skipped_targets_contradict_evidence")
        if closure_report.closure_status not in CLOSURE_STATUSES:
            findings.append("closure_status_unknown")
        closure_consistency.append("closure_report_checked")
    else:
        closure_consistency.append("closure_report_not_supplied")

    post_ok = all(record.target_verification_status != "target_verification_failed" for record in target_records if record.target_id in applied - rolled_back)
    rollback_ok: bool | None = None
    if rollback_result and rollback_result.rollback_performed:
        rollback_ok = all(record.target_verification_status in {"target_verified_rollback_preimage", "target_verified_rollback_absence"} for record in target_records if record.target_id in rolled_back)

    insufficient = any(record.target_verification_status == "target_insufficient_evidence" for record in target_records) or any(code.startswith("missing_") and "target_missing" not in code for code in findings)
    blocked = execution_request.request_status == "workspace_change_set_execution_blocked" or execution_result.execution_status == "workspace_change_set_execution_blocked"
    failed_verification = bool(findings) and not (insufficient or blocked)
    partial_visible = bool(execution_result.partial_state_visible or failed or skipped or (closure_report and closure_report.open_issue_codes))

    if blocked:
        status = "verification_blocked"
    elif insufficient:
        status = "insufficient_evidence"
    elif failed_verification:
        status = "verification_failed"
    elif rollback_result and rollback_result.rollback_performed and not (set(execution_result.applied_target_ids) - rolled_back):
        status = "verified_rolled_back"
    elif partial_visible:
        status = "verified_with_partial_state"
    else:
        status = "verified_clean"

    result = WorkspaceChangeSetExecutionVerificationResult(
        verification_id=f"workspace-change-set-execution-verification-{execution_result.result_id}",
        request_id=request.request_id,
        verification_status=status,
        basis=tuple(sorted(set(basis))),
        target_records=target_records,
        receipt_consistency=tuple(receipt_consistency),
        ledger_consistency=tuple(ledger_consistency),
        closure_consistency=tuple(closure_consistency),
        postcondition_digest_agreement=post_ok,
        rollback_digest_agreement=rollback_ok,
        partial_state_visible=partial_visible,
        unknown_target_ids=unknown_ids,
        finding_codes=tuple(sorted(set(findings))),
        audit_artifact_path=None,
        audit_artifact_digest=None,
    )
    result = replace(result, digest=_digest("workspace-change-set-execution-verification-result-", result.to_dict()))
    artifact_path, artifact_digest, artifact_findings = _write_audit_artifact(result, request, {_target_path(root, target.relative_target_path) for target in manifest.targets})
    if artifact_findings:
        findings.extend(artifact_findings)
        result = replace(result, verification_status="verification_failed", finding_codes=tuple(sorted(set(findings))))
    if artifact_path:
        result = replace(result, audit_artifact_path=artifact_path, audit_artifact_digest=artifact_digest)
    result = replace(result, digest="")
    result = replace(result, digest=_digest("workspace-change-set-execution-verification-result-", result.to_dict()))
    return WorkspaceChangeSetExecutionVerificationWingResult(request, result)


def summarize_workspace_change_set_execution_verification_result(result: WorkspaceChangeSetExecutionVerificationResult) -> dict[str, Any]:
    return {
        "verification_id": result.verification_id,
        "verification_status": result.verification_status,
        "target_count": len(result.target_records),
        "postcondition_digest_agreement": result.postcondition_digest_agreement,
        "rollback_digest_agreement": result.rollback_digest_agreement,
        "partial_state_visible": result.partial_state_visible,
        "unknown_target_ids": result.unknown_target_ids,
        "finding_codes": result.finding_codes,
        "verification_only": True,
        "read_only_except_optional_audit_artifact": True,
        "execution_invoked": False,
        "rollback_invoked": False,
        "cleanup_performed": False,
    }


T = TypeVar("T")


def _coerce_value(annotation: Any, value: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is tuple and args:
        inner = args[0]
        return tuple(_coerce_value(inner, item) for item in (value or ()))
    if origin is list and args:
        inner = args[0]
        return [_coerce_value(inner, item) for item in (value or ())]
    if origin is dict:
        return dict(value or {})
    if isinstance(annotation, type) and is_dataclass(annotation) and isinstance(value, Mapping):
        return dataclass_from_dict(annotation, value)
    return value


def dataclass_from_dict(cls: type[T], payload: Mapping[str, Any]) -> T:
    kwargs: dict[str, Any] = {}
    type_hints = get_type_hints(cls)
    for field in fields(cast(Any, cls)):
        if field.name in payload:
            kwargs[field.name] = _coerce_value(type_hints.get(field.name, field.type), payload[field.name])
    return cls(**kwargs)


def verification_evidence_from_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "manifest": dataclass_from_dict(WorkspaceChangeSetManifest, payload["manifest"]),
        "preflight_report": dataclass_from_dict(WorkspaceChangeSetPreflightReport, payload["preflight_report"]),
        "rollback_plan": dataclass_from_dict(WorkspaceChangeSetRollbackPlan, payload["rollback_plan"]),
        "transaction_plan": dataclass_from_dict(WorkspaceChangeSetTransactionPlan, payload["transaction_plan"]),
        "execution_request": dataclass_from_dict(WorkspaceChangeSetExecutionRequest, payload.get("execution_request", payload.get("request", {}))),
        "execution_result": dataclass_from_dict(WorkspaceChangeSetExecutionResult, payload["execution_result"]),
        "execution_receipt": dataclass_from_dict(WorkspaceChangeSetExecutionReceipt, payload["execution_receipt"]),
        "rollback_result": dataclass_from_dict(WorkspaceChangeSetRollbackExecutionResult, payload["rollback_result"]) if payload.get("rollback_result") else None,
        "rollback_receipt": dataclass_from_dict(WorkspaceChangeSetRollbackReceipt, payload["rollback_receipt"]) if payload.get("rollback_receipt") else None,
        "ledger": dataclass_from_dict(WorkspaceChangeSetExecutionLedger, payload["ledger"]) if payload.get("ledger") else None,
        "closure_report": dataclass_from_dict(WorkspaceChangeSetExecutionClosureReport, payload["closure_report"]) if payload.get("closure_report") else None,
    }


def load_verification_evidence(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if "preflight" in payload and isinstance(payload["preflight"], Mapping):
        preflight = payload["preflight"]
        payload = {**payload, "manifest": preflight.get("manifest"), "preflight_report": preflight.get("preflight_report"), "rollback_plan": preflight.get("rollback_plan"), "transaction_plan": preflight.get("transaction_plan")}
    return verification_evidence_from_mapping(payload)
