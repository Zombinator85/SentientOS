"""Bounded workspace change-set transaction execution.

This wing consumes a passed Workspace Change Set preflight/transaction plan and
executes only the explicit relative targets declared in that manifest. Each
write is delegated to :mod:`sentientos.workspace_file_effect`, preserving the
existing single-target workspace guardrails and exact-target rollback machinery.

It is not general filesystem access, not cleanup, not recursive or wildcard
operation, and it never invokes subprocesses, shells, network/provider/prompt
machinery, services, power, hardware, fan/PWM, thermal, plugins, generated code,
or federation transports.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.workspace_change_set_preflight import (
    DEFAULT_CREATED_AT,
    WorkspaceChangeSetManifest,
    WorkspaceChangeSetPreflightReport,
    WorkspaceChangeSetRollbackPlan,
    WorkspaceChangeSetTransactionPlan,
    WorkspaceChangeTargetDeclaration,
)
from sentientos.workspace_file_effect import (
    WorkspaceFileEffectWingResult,
    WorkspaceFileRollbackPlan,
    WorkspaceFileRollbackWingResult,
    bytes_digest,
    run_workspace_file_effect_wing,
    run_workspace_file_rollback_wing,
)

EXECUTION_MODES = frozenset({
    "change_set_execute_only",
    "change_set_execute_with_ledger",
    "change_set_execute_with_rollback_after",
    "change_set_execute_rollback_with_ledger",
    "change_set_execute_with_rollback_on_failure",
    "change_set_execute_full_guarded",
})
REQUEST_STATUSES = frozenset({
    "workspace_change_set_execution_requested",
    "workspace_change_set_execution_blocked",
    "workspace_change_set_execution_incomplete",
    "workspace_change_set_execution_contradicted",
})
TARGET_EXECUTION_STATUSES = frozenset({
    "workspace_change_target_execution_created",
    "workspace_change_target_execution_updated",
    "workspace_change_target_execution_blocked",
    "workspace_change_target_execution_failed",
    "workspace_change_target_execution_skipped_after_failure",
    "workspace_change_target_execution_contradicted",
})
CHANGE_SET_EXECUTION_STATUSES = frozenset({
    "workspace_change_set_execution_performed",
    "workspace_change_set_execution_performed_with_warnings",
    "workspace_change_set_execution_partially_performed",
    "workspace_change_set_execution_blocked",
    "workspace_change_set_execution_failed",
    "workspace_change_set_execution_incomplete",
    "workspace_change_set_execution_contradicted",
})
ROLLBACK_EXECUTION_STATUSES = frozenset({
    "workspace_change_set_rollback_performed",
    "workspace_change_set_rollback_performed_with_warnings",
    "workspace_change_set_rollback_partially_performed",
    "workspace_change_set_rollback_not_requested",
    "workspace_change_set_rollback_blocked",
    "workspace_change_set_rollback_failed",
    "workspace_change_set_rollback_incomplete",
    "workspace_change_set_rollback_contradicted",
})
RECEIPT_STATUSES = frozenset({
    "workspace_change_set_execution_receipt_recorded",
    "workspace_change_set_execution_receipt_recorded_with_warnings",
    "workspace_change_set_execution_receipt_blocked",
    "workspace_change_set_execution_receipt_failed",
    "workspace_change_set_execution_receipt_incomplete",
    "workspace_change_set_execution_receipt_contradicted",
})
CLOSURE_STATUSES = frozenset({
    "workspace_change_set_execution_closed_after_execute",
    "workspace_change_set_execution_closed_after_rollback",
    "workspace_change_set_execution_open",
    "workspace_change_set_execution_partially_open",
    "workspace_change_set_execution_rollback_pending",
    "workspace_change_set_execution_rollback_incomplete",
    "workspace_change_set_execution_failed",
    "workspace_change_set_execution_contradicted",
})
PASSED_PREFLIGHT_STATUSES = frozenset({
    "workspace_change_set_preflight_passed",
    "workspace_change_set_preflight_passed_with_warnings",
})
READY_TRANSACTION_STATUSES = frozenset({
    "workspace_change_set_transaction_plan_ready",
    "workspace_change_set_transaction_plan_ready_with_warnings",
})
READY_ROLLBACK_PLAN_STATUSES = frozenset({
    "workspace_change_set_rollback_plan_ready",
    "workspace_change_set_rollback_plan_ready_with_warnings",
})
BLOCKED_ACTION_LABELS = (
    "general_filesystem_access",
    "directory_cleanup",
    "recursive_delete",
    "wildcard_delete",
    "unrelated_file_delete",
    "path_traversal",
    "absolute_target_path",
    "target_outside_workspace",
    "symlink_target_write",
    "directory_target_write",
    "fan_pwm_write",
    "thermal_actuation",
    "power_profile_mutation",
    "process_kill",
    "service_restart",
    "package_install",
    "driver_install",
    "provider_invocation",
    "network_egress",
    "prompt_assembly",
    "federation_transport",
    "remote_execution",
    "subprocess_execution",
    "shell_execution",
    "os_backend_invocation",
    "control_plane_admission_execution",
    "hardware_control",
)
FORBIDDEN_TRUE_FIELDS = (
    "general_filesystem_access_requested",
    "general_filesystem_access_performed",
    "cleanup_requested",
    "cleanup_performed",
    "directory_cleanup_performed",
    "general_cleanup_performed",
    "recursive_delete_requested",
    "recursive_delete_performed",
    "wildcard_delete_requested",
    "wildcard_delete_performed",
    "unrelated_file_delete_performed",
    "subprocess_used",
    "shell_used",
    "network_used",
    "network_performed",
    "provider_invocation_performed",
    "prompt_assembly_performed",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "power_profile_mutation_performed",
    "process_kill_performed",
    "service_restart_performed",
    "package_install_performed",
    "driver_install_performed",
    "hardware_control_performed",
    "control_plane_admission_execution_performed",
)
_ALLOWED_MUTATION_TRUE_FIELDS = frozenset({
    "change_set_execution_requested",
    "target_write_performed",
    "host_mutation_performed",
    "local_file_write_performed",
    "change_set_execution_performed",
    "all_targets_applied",
    "partial_state_visible",
    "change_set_execution_receipt_created",
    "rollback_performed",
    "exact_target_rollback_only",
    "change_set_rollback_receipt_created",
    "metadata_only",
    "execution_ledger_only",
    "closure_report_only",
    "performs_no_new_effect",
})


def _tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def deterministic_digest(prefix: str, payload: Mapping[str, Any]) -> str:
    data = dict(payload)
    data["digest"] = ""
    return "sha256:" + hashlib.sha256((prefix + _canonical_json(data)).encode("utf-8")).hexdigest()


def _target_digest(path: Path) -> str | None:
    if not path.exists() or path.is_symlink() or not path.is_file():
        return None
    digest = bytes_digest(path.read_bytes())
    return digest if isinstance(digest, str) else str(digest)


def _normalize_relative(path_text: str) -> str:
    text = path_text.replace("\\", "/")
    pure = PurePosixPath(text)
    parts: list[str] = []
    for part in pure.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            else:
                parts.append("..")
        else:
            parts.append(part)
    return "/".join(parts)


def _inside_workspace(root: Path, target: Path) -> bool:
    try:
        target.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class WorkspaceChangeSetExecutionValidationResult:
    ok: bool
    status: str
    findings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetExecutionPolicy:
    require_passed_preflight: bool = True
    require_transaction_plan: bool = True
    max_targets: int = 8
    execute_in_planned_order: bool = True
    rollback_in_reverse_order: bool = True
    stop_on_first_failure: bool = True
    rollback_on_failure_default: bool = True
    require_digest_still_matches_preflight: bool = True
    require_parent_exists: bool = True
    allow_replace: bool = True
    allow_create: bool = True
    write_ledger_default: bool = False
    mutation_allowed: bool = True
    blocked_actions: tuple[str, ...] = BLOCKED_ACTION_LABELS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetExecutionRequest:
    request_id: str
    source_manifest_id: str
    source_preflight_report_id: str
    source_rollback_plan_id: str
    source_transaction_plan_id: str
    workspace_root: str
    execution_mode: str
    target_order: tuple[str, ...]
    rollback_on_failure: bool
    rollback_after_execute: bool
    write_ledger: bool
    ledger_output_path: str | None
    required_execution_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    request_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    change_set_execution_requested: bool = True
    general_filesystem_access_requested: bool = False
    cleanup_requested: bool = False
    recursive_delete_requested: bool = False
    wildcard_delete_requested: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeTargetExecutionResult:
    result_id: str
    request_id: str
    target_id: str
    relative_target_path: str
    operation: str
    target_execution_status: str
    workspace_effect_receipt_id: str | None
    workspace_effect_receipt_digest: str | None
    workspace_postcondition_check_id: str | None
    workspace_postcondition_check_digest: str | None
    workspace_rollback_plan_id: str | None
    workspace_rollback_plan_digest: str | None
    workspace_production_audit_id: str | None
    workspace_production_audit_digest: str | None
    target_path: str
    before_digest: str | None
    after_digest: str | None
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    target_write_performed: bool = False
    host_mutation_performed: bool = False
    local_file_write_performed: bool = False
    rollback_performed: bool = False
    general_filesystem_access_performed: bool = False
    directory_cleanup_performed: bool = False
    recursive_delete_performed: bool = False
    wildcard_delete_performed: bool = False
    unrelated_file_delete_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    fan_pwm_write_performed: bool = False
    thermal_actuation_performed: bool = False
    power_profile_mutation_performed: bool = False
    process_kill_performed: bool = False
    service_restart_performed: bool = False
    package_install_performed: bool = False
    driver_install_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetExecutionResult:
    result_id: str
    request_id: str
    workspace_root: str
    execution_mode: str
    target_results: tuple[WorkspaceChangeTargetExecutionResult, ...]
    applied_target_ids: tuple[str, ...]
    failed_target_ids: tuple[str, ...]
    skipped_target_ids: tuple[str, ...]
    produced_record_ids: tuple[str, ...]
    produced_record_digests: tuple[str, ...]
    produced_paths: tuple[str, ...]
    execution_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    change_set_execution_performed: bool = False
    all_targets_applied: bool = False
    partial_state_visible: bool = False
    host_mutation_performed: bool = False
    target_write_performed: bool = False
    rollback_performed: bool = False
    general_filesystem_access_performed: bool = False
    cleanup_performed: bool = False
    recursive_delete_performed: bool = False
    wildcard_delete_performed: bool = False
    unrelated_file_delete_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass(frozen=True)
class WorkspaceChangeSetExecutionReceipt:
    receipt_id: str
    request_id: str
    result_id: str
    workspace_root: str
    execution_mode: str
    receipt_status: str
    evidence_summary: tuple[str, ...]
    applied_target_ids: tuple[str, ...]
    failed_target_ids: tuple[str, ...]
    skipped_target_ids: tuple[str, ...]
    produced_record_ids: tuple[str, ...]
    produced_record_digests: tuple[str, ...]
    produced_paths: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    change_set_execution_receipt_created: bool = True
    host_mutation_performed: bool = False
    target_write_performed: bool = False
    general_filesystem_access_performed: bool = False
    cleanup_performed: bool = False
    recursive_delete_performed: bool = False
    wildcard_delete_performed: bool = False
    unrelated_file_delete_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetRollbackExecutionResult:
    rollback_result_id: str
    source_execution_result_id: str
    workspace_root: str
    rollback_target_order: tuple[str, ...]
    rollback_target_ids: tuple[str, ...]
    rollback_status_by_target: tuple[dict[str, str], ...]
    rollback_receipt_ids: tuple[str, ...]
    rollback_receipt_digests: tuple[str, ...]
    rollback_postcondition_check_ids: tuple[str, ...]
    rollback_postcondition_check_digests: tuple[str, ...]
    rollback_audit_ids: tuple[str, ...]
    rollback_audit_digests: tuple[str, ...]
    rollback_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    rollback_performed: bool = False
    host_mutation_performed: bool = False
    exact_target_rollback_only: bool = True
    general_cleanup_performed: bool = False
    recursive_delete_performed: bool = False
    wildcard_delete_performed: bool = False
    unrelated_file_delete_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetRollbackReceipt:
    receipt_id: str
    source_execution_receipt_id: str
    rollback_result_id: str
    workspace_root: str
    rollback_status: str
    evidence_summary: tuple[str, ...]
    rollback_target_order: tuple[str, ...]
    rollback_receipt_ids: tuple[str, ...]
    rollback_receipt_digests: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    change_set_rollback_receipt_created: bool = True
    rollback_performed: bool = False
    exact_target_rollback_only: bool = True
    general_cleanup_performed: bool = False
    recursive_delete_performed: bool = False
    wildcard_delete_performed: bool = False
    unrelated_file_delete_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetExecutionLedger:
    ledger_id: str
    request_id: str
    execution_receipt_id: str
    rollback_receipt_id: str | None
    target_event_entries: tuple[dict[str, Any], ...]
    execution_status: str
    rollback_status: str | None
    lifecycle_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    execution_ledger_only: bool = True
    performs_no_new_effect: bool = True
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceChangeSetExecutionClosureReport:
    report_id: str
    ledger_id: str | None
    execution_receipt_id: str
    rollback_receipt_id: str | None
    closure_status: str
    applied_target_ids: tuple[str, ...]
    rolled_back_target_ids: tuple[str, ...]
    open_target_ids: tuple[str, ...]
    failed_target_ids: tuple[str, ...]
    skipped_target_ids: tuple[str, ...]
    open_issue_codes: tuple[str, ...]
    closure_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    closure_report_only: bool = True
    performs_no_new_effect: bool = True
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkspaceChangeSetExecutionWingResult(NamedTuple):
    request: WorkspaceChangeSetExecutionRequest
    execution_result: WorkspaceChangeSetExecutionResult
    execution_receipt: WorkspaceChangeSetExecutionReceipt
    rollback_result: WorkspaceChangeSetRollbackExecutionResult
    rollback_receipt: WorkspaceChangeSetRollbackReceipt | None
    ledger: WorkspaceChangeSetExecutionLedger | None
    closure_report: WorkspaceChangeSetExecutionClosureReport


def build_default_workspace_change_set_execution_policy() -> WorkspaceChangeSetExecutionPolicy:
    return WorkspaceChangeSetExecutionPolicy()


def build_workspace_change_set_execution_request(
    *,
    manifest: WorkspaceChangeSetManifest,
    preflight_report: WorkspaceChangeSetPreflightReport,
    rollback_plan: WorkspaceChangeSetRollbackPlan,
    transaction_plan: WorkspaceChangeSetTransactionPlan,
    execution_mode: str = "change_set_execute_full_guarded",
    rollback_on_failure: bool | None = None,
    rollback_after_execute: bool = False,
    write_ledger: bool | None = None,
    ledger_output_path: str | None = None,
    policy: WorkspaceChangeSetExecutionPolicy | None = None,
    request_id: str | None = None,
    required_execution_labels: Sequence[str] = ("passed_workspace_change_set_preflight", "ready_workspace_change_set_transaction_plan", "explicit_workspace_root", "explicit_manifest_targets"),
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetExecutionRequest:
    policy = policy or build_default_workspace_change_set_execution_policy()
    findings: list[str] = []
    if execution_mode not in EXECUTION_MODES:
        findings.append("unknown_execution_mode")
    if len(transaction_plan.planned_target_order) > policy.max_targets:
        findings.append("target_count_over_limit")
    if policy.require_passed_preflight and preflight_report.report_status not in PASSED_PREFLIGHT_STATUSES:
        findings.append("preflight_not_passed")
    if policy.require_transaction_plan and transaction_plan.transaction_plan_status not in READY_TRANSACTION_STATUSES:
        findings.append("transaction_plan_not_ready")
    if rollback_plan.rollback_plan_status not in READY_ROLLBACK_PLAN_STATUSES:
        findings.append("rollback_plan_not_ready")
    if manifest.manifest_id != preflight_report.manifest_id or manifest.manifest_id != transaction_plan.manifest_id or manifest.manifest_id != rollback_plan.manifest_id:
        findings.append("source_manifest_mismatch")
    if preflight_report.report_id != transaction_plan.preflight_report_id or preflight_report.report_id != rollback_plan.preflight_report_id:
        findings.append("source_preflight_report_mismatch")
    if rollback_plan.plan_id != transaction_plan.rollback_plan_id:
        findings.append("source_rollback_plan_mismatch")
    if tuple(target.target_id for target in manifest.targets) != tuple(transaction_plan.planned_target_order):
        findings.append("transaction_order_not_manifest_order")
    status = "workspace_change_set_execution_requested"
    if findings:
        status = "workspace_change_set_execution_blocked"
    if any("contradict" in item for item in findings) or preflight_report.report_status.endswith("contradicted") or transaction_plan.transaction_plan_status.endswith("contradicted"):
        status = "workspace_change_set_execution_contradicted"
    mode_requests_ledger = execution_mode in {"change_set_execute_with_ledger", "change_set_execute_rollback_with_ledger", "change_set_execute_full_guarded"}
    mode_requests_rollback_after = execution_mode in {"change_set_execute_with_rollback_after", "change_set_execute_rollback_with_ledger"}
    record = WorkspaceChangeSetExecutionRequest(
        request_id=request_id or "workspace-change-set-execution-request-" + hashlib.sha256(f"{manifest.manifest_id}\0{transaction_plan.plan_id}\0{created_at}".encode("utf-8")).hexdigest()[:16],
        source_manifest_id=manifest.manifest_id,
        source_preflight_report_id=preflight_report.report_id,
        source_rollback_plan_id=rollback_plan.plan_id,
        source_transaction_plan_id=transaction_plan.plan_id,
        workspace_root=str(manifest.workspace_root),
        execution_mode=execution_mode,
        target_order=tuple(transaction_plan.planned_target_order),
        rollback_on_failure=policy.rollback_on_failure_default if rollback_on_failure is None else bool(rollback_on_failure),
        rollback_after_execute=bool(rollback_after_execute or mode_requests_rollback_after),
        write_ledger=policy.write_ledger_default if write_ledger is None else bool(write_ledger or mode_requests_ledger or ledger_output_path),
        ledger_output_path=str(ledger_output_path) if ledger_output_path else None,
        required_execution_labels=_tuple(required_execution_labels),
        blocked_actions=tuple(sorted(set(policy.blocked_actions))),
        request_status=status,
        warning_codes=(),
        risk_codes=tuple(sorted(set(findings + list(manifest.risk_codes) + list(preflight_report.risk_codes) + list(transaction_plan.risk_codes)))),
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=deterministic_digest("workspace-change-set-execution-request-", record.to_dict()))


def _forbidden_true_findings(record: Any) -> list[str]:
    payload = record.to_dict() if hasattr(record, "to_dict") else asdict(record)
    findings: list[str] = []
    for field in FORBIDDEN_TRUE_FIELDS:
        if payload.get(field) is True:
            findings.append(f"contradiction:{field}_true")
    return findings


def validate_workspace_change_set_execution_request(record: WorkspaceChangeSetExecutionRequest) -> WorkspaceChangeSetExecutionValidationResult:
    findings = _forbidden_true_findings(record)
    if record.request_status not in REQUEST_STATUSES:
        findings.append("unknown_request_status")
    if record.execution_mode not in EXECUTION_MODES:
        findings.append("unknown_execution_mode")
    if not record.change_set_execution_requested:
        findings.append("change_set_execution_not_requested")
    status = record.request_status if not findings else "workspace_change_set_execution_contradicted"
    return WorkspaceChangeSetExecutionValidationResult(not findings and record.request_status == "workspace_change_set_execution_requested", status, tuple(sorted(set(findings + list(record.risk_codes if record.request_status != "workspace_change_set_execution_requested" else ())))))


def _blocked_result(request: WorkspaceChangeSetExecutionRequest, findings: Sequence[str], created_at: str) -> WorkspaceChangeSetExecutionResult:
    record = WorkspaceChangeSetExecutionResult(
        result_id=f"workspace-change-set-execution-result-{request.request_id}",
        request_id=request.request_id,
        workspace_root=request.workspace_root,
        execution_mode=request.execution_mode,
        target_results=(),
        applied_target_ids=(),
        failed_target_ids=(),
        skipped_target_ids=tuple(request.target_order),
        produced_record_ids=(),
        produced_record_digests=(),
        produced_paths=(),
        execution_status="workspace_change_set_execution_contradicted" if any("contradict" in item for item in findings) else "workspace_change_set_execution_blocked",
        warning_codes=tuple(findings),
        risk_codes=tuple(sorted(set(findings))),
        created_at=created_at,
        digest="",
        partial_state_visible=False,
    )
    return replace(record, digest=deterministic_digest("workspace-change-set-execution-result-", record.to_dict()))


def _target_result_from_effect(
    *,
    request: WorkspaceChangeSetExecutionRequest,
    target: WorkspaceChangeTargetDeclaration,
    wing: WorkspaceFileEffectWingResult | None,
    status: str,
    before_digest: str | None,
    after_digest: str | None,
    warning_codes: Sequence[str] = (),
    created_at: str,
) -> WorkspaceChangeTargetExecutionResult:
    receipt = wing.receipt if wing else None
    postcondition = wing.postcondition if wing else None
    rollback_plan = wing.rollback_plan if wing else None
    audit = wing.production_audit if wing else None
    succeeded = status in {"workspace_change_target_execution_created", "workspace_change_target_execution_updated"}
    record = WorkspaceChangeTargetExecutionResult(
        result_id=f"workspace-change-target-execution-result-{request.request_id}-{target.target_id}",
        request_id=request.request_id,
        target_id=target.target_id,
        relative_target_path=target.relative_target_path,
        operation=target.operation,
        target_execution_status=status,
        workspace_effect_receipt_id=receipt.receipt_id if receipt else None,
        workspace_effect_receipt_digest=receipt.digest if receipt else None,
        workspace_postcondition_check_id=postcondition.check_id if postcondition else None,
        workspace_postcondition_check_digest=postcondition.digest if postcondition else None,
        workspace_rollback_plan_id=rollback_plan.plan_id if rollback_plan else None,
        workspace_rollback_plan_digest=rollback_plan.digest if rollback_plan else None,
        workspace_production_audit_id=audit.audit_id if audit else None,
        workspace_production_audit_digest=audit.digest if audit else None,
        target_path=receipt.target_path if receipt else str(Path(request.workspace_root) / _normalize_relative(target.relative_target_path)),
        before_digest=before_digest,
        after_digest=after_digest,
        warning_codes=_tuple(warning_codes),
        risk_codes=tuple(sorted(set(_tuple(warning_codes) + target.risk_codes))),
        created_at=created_at,
        digest="",
        target_write_performed=succeeded,
        host_mutation_performed=succeeded,
        local_file_write_performed=succeeded,
    )
    return replace(record, digest=deterministic_digest("workspace-change-target-execution-result-", record.to_dict()))


def _skipped_target_result(request: WorkspaceChangeSetExecutionRequest, target: WorkspaceChangeTargetDeclaration, created_at: str) -> WorkspaceChangeTargetExecutionResult:
    return _target_result_from_effect(
        request=request,
        target=target,
        wing=None,
        status="workspace_change_target_execution_skipped_after_failure",
        before_digest=None,
        after_digest=None,
        warning_codes=("skipped_after_prior_target_failure",),
        created_at=created_at,
    )


def _digest_drift_findings(manifest: WorkspaceChangeSetManifest, rollback_plan: WorkspaceChangeSetRollbackPlan) -> tuple[str, ...]:
    root = Path(manifest.workspace_root).expanduser()
    target_by_id = {target.target_id: target for target in manifest.targets}
    findings: list[str] = []
    for entry in rollback_plan.target_rollback_entries:
        target_id = str(entry.get("target_id", ""))
        target = target_by_id.get(target_id)
        if target is None:
            findings.append(f"target_not_in_manifest:{target_id}")
            continue
        normalized = _normalize_relative(target.relative_target_path)
        path = root / normalized
        if not _inside_workspace(root, path):
            findings.append(f"target_outside_workspace:{target_id}")
            continue
        if path.is_symlink():
            findings.append(f"symlink_target_write:{target_id}")
            continue
        if path.exists() and path.is_dir():
            findings.append(f"directory_target_write:{target_id}")
            continue
        existed_before = bool(entry.get("existed_before"))
        expected_digest = entry.get("existing_digest")
        if existed_before:
            current = _target_digest(path)
            if current != expected_digest:
                findings.append(f"preflight_digest_drift:{target_id}")
        elif path.exists():
            findings.append(f"preflight_absent_target_now_exists:{target_id}")
        if not path.parent.exists():
            findings.append(f"parent_missing_since_preflight:{target_id}")
    return tuple(findings)


def execute_workspace_change_set(
    *,
    request: WorkspaceChangeSetExecutionRequest,
    manifest: WorkspaceChangeSetManifest,
    preflight_report: WorkspaceChangeSetPreflightReport,
    rollback_plan: WorkspaceChangeSetRollbackPlan,
    transaction_plan: WorkspaceChangeSetTransactionPlan,
    policy: WorkspaceChangeSetExecutionPolicy | None = None,
    created_at: str = DEFAULT_CREATED_AT,
    effect_runner: Any = run_workspace_file_effect_wing,
) -> tuple[WorkspaceChangeSetExecutionResult, tuple[WorkspaceFileEffectWingResult, ...]]:
    policy = policy or build_default_workspace_change_set_execution_policy()
    validation = validate_workspace_change_set_execution_request(request)
    findings = list(validation.findings)
    if not validation.ok:
        findings.append("execution_request_not_valid")
    if preflight_report.report_status not in PASSED_PREFLIGHT_STATUSES:
        findings.append("preflight_not_passed")
    if transaction_plan.transaction_plan_status not in READY_TRANSACTION_STATUSES:
        findings.append("transaction_plan_not_ready")
    if policy.require_digest_still_matches_preflight:
        findings.extend(_digest_drift_findings(manifest, rollback_plan))
    if findings:
        return _blocked_result(request, findings, created_at), ()

    root = Path(request.workspace_root).expanduser()
    target_by_id = {target.target_id: target for target in manifest.targets}
    target_results: list[WorkspaceChangeTargetExecutionResult] = []
    applied: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []
    produced_ids: list[str] = []
    produced_digests: list[str] = []
    produced_paths: list[str] = []
    effect_wings: list[WorkspaceFileEffectWingResult] = []
    failure_seen = False
    warning_codes: list[str] = []

    for target_id in request.target_order:
        target = target_by_id.get(target_id)
        if target is None:
            failed.append(target_id)
            warning_codes.append(f"target_not_in_manifest:{target_id}")
            failure_seen = True
            continue
        if failure_seen and policy.stop_on_first_failure:
            skipped.append(target_id)
            target_results.append(_skipped_target_result(request, target, created_at))
            continue
        target_path = root / _normalize_relative(target.relative_target_path)
        before_digest = _target_digest(target_path)
        try:
            wing = effect_runner(
                workspace_root=request.workspace_root,
                relative_target_path=target.relative_target_path,
                payload_text=target.payload_text,
                request_id=f"{request.request_id}-{target.target_id}",
                force_create=(target.operation == "create_file"),
                allow_replace=target.allow_replace and policy.allow_replace,
                dry_run=False,
                created_at=created_at,
            )
        except Exception as exc:  # fail-stop visibility; exception is captured, not retried or hidden.
            failed.append(target_id)
            failure_seen = True
            warning = f"target_effect_exception:{type(exc).__name__}"
            warning_codes.append(warning)
            target_results.append(_target_result_from_effect(request=request, target=target, wing=None, status="workspace_change_target_execution_failed", before_digest=before_digest, after_digest=_target_digest(target_path), warning_codes=(warning,), created_at=created_at))
            continue
        after_digest = _target_digest(Path(wing.receipt.target_path))
        if wing.receipt.real_effect_performed and wing.postcondition.postcondition_status == "workspace_file_postcondition_passed":
            status = "workspace_change_target_execution_created" if wing.receipt.created_new_file else "workspace_change_target_execution_updated"
            applied.append(target_id)
            effect_wings.append(wing)
            produced_ids.extend([wing.receipt.receipt_id, wing.postcondition.check_id, wing.rollback_plan.plan_id, wing.production_audit.audit_id])
            produced_digests.extend([wing.receipt.digest, wing.postcondition.digest, wing.rollback_plan.digest, wing.production_audit.digest])
            produced_paths.append(wing.receipt.target_path)
        else:
            status = "workspace_change_target_execution_blocked" if wing.result.effect_status == "workspace_file_effect_blocked" else "workspace_change_target_execution_failed"
            failed.append(target_id)
            failure_seen = True
            warning_codes.extend(wing.result.warning_codes)
        target_results.append(_target_result_from_effect(request=request, target=target, wing=wing, status=status, before_digest=before_digest, after_digest=after_digest, warning_codes=wing.result.warning_codes, created_at=created_at))

    all_applied = len(applied) == len(request.target_order) and not failed and not skipped
    any_applied = bool(applied)
    partial = any_applied and (bool(failed) or bool(skipped) or len(applied) != len(request.target_order))
    if all_applied and warning_codes:
        status = "workspace_change_set_execution_performed_with_warnings"
    elif all_applied:
        status = "workspace_change_set_execution_performed"
    elif any_applied:
        status = "workspace_change_set_execution_partially_performed"
    elif failed:
        status = "workspace_change_set_execution_failed"
    else:
        status = "workspace_change_set_execution_incomplete"
    record = WorkspaceChangeSetExecutionResult(
        result_id=f"workspace-change-set-execution-result-{request.request_id}",
        request_id=request.request_id,
        workspace_root=request.workspace_root,
        execution_mode=request.execution_mode,
        target_results=tuple(target_results),
        applied_target_ids=tuple(applied),
        failed_target_ids=tuple(failed),
        skipped_target_ids=tuple(skipped),
        produced_record_ids=tuple(produced_ids),
        produced_record_digests=tuple(produced_digests),
        produced_paths=tuple(produced_paths),
        execution_status=status,
        warning_codes=tuple(sorted(set(warning_codes))),
        risk_codes=tuple(sorted(set(manifest.risk_codes + preflight_report.risk_codes + tuple(warning_codes)))),
        created_at=created_at,
        digest="",
        change_set_execution_performed=any_applied,
        all_targets_applied=all_applied,
        partial_state_visible=partial,
        host_mutation_performed=any_applied,
        target_write_performed=any_applied,
    )
    return replace(record, digest=deterministic_digest("workspace-change-set-execution-result-", record.to_dict())), tuple(effect_wings)


def build_workspace_change_set_execution_receipt(
    request: WorkspaceChangeSetExecutionRequest,
    result: WorkspaceChangeSetExecutionResult,
    *,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetExecutionReceipt:
    if result.execution_status == "workspace_change_set_execution_contradicted":
        status = "workspace_change_set_execution_receipt_contradicted"
    elif result.execution_status == "workspace_change_set_execution_blocked":
        status = "workspace_change_set_execution_receipt_blocked"
    elif result.execution_status in {"workspace_change_set_execution_failed", "workspace_change_set_execution_partially_performed"}:
        status = "workspace_change_set_execution_receipt_failed"
    elif result.warning_codes:
        status = "workspace_change_set_execution_receipt_recorded_with_warnings"
    elif result.change_set_execution_performed:
        status = "workspace_change_set_execution_receipt_recorded"
    else:
        status = "workspace_change_set_execution_receipt_incomplete"
    record = WorkspaceChangeSetExecutionReceipt(
        receipt_id=f"workspace-change-set-execution-receipt-{result.result_id}",
        request_id=request.request_id,
        result_id=result.result_id,
        workspace_root=result.workspace_root,
        execution_mode=result.execution_mode,
        receipt_status=status,
        evidence_summary=tuple(str(item) for item in summarize_workspace_change_set_execution_result(result).items()),
        applied_target_ids=result.applied_target_ids,
        failed_target_ids=result.failed_target_ids,
        skipped_target_ids=result.skipped_target_ids,
        produced_record_ids=result.produced_record_ids,
        produced_record_digests=result.produced_record_digests,
        produced_paths=result.produced_paths,
        blocked_actions=request.blocked_actions,
        warning_codes=result.warning_codes,
        risk_codes=result.risk_codes,
        created_at=created_at,
        digest="",
        host_mutation_performed=result.host_mutation_performed,
        target_write_performed=result.target_write_performed,
    )
    return replace(record, digest=deterministic_digest("workspace-change-set-execution-receipt-", record.to_dict()))


def _rollback_not_requested(execution_result: WorkspaceChangeSetExecutionResult, created_at: str) -> WorkspaceChangeSetRollbackExecutionResult:
    record = WorkspaceChangeSetRollbackExecutionResult(
        rollback_result_id=f"workspace-change-set-rollback-result-{execution_result.result_id}",
        source_execution_result_id=execution_result.result_id,
        workspace_root=execution_result.workspace_root,
        rollback_target_order=(),
        rollback_target_ids=(),
        rollback_status_by_target=(),
        rollback_receipt_ids=(),
        rollback_receipt_digests=(),
        rollback_postcondition_check_ids=(),
        rollback_postcondition_check_digests=(),
        rollback_audit_ids=(),
        rollback_audit_digests=(),
        rollback_status="workspace_change_set_rollback_not_requested",
        warning_codes=("rollback_not_requested",),
        risk_codes=(),
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=deterministic_digest("workspace-change-set-rollback-result-", record.to_dict()))


def execute_workspace_change_set_rollback(
    *,
    execution_result: WorkspaceChangeSetExecutionResult,
    target_effects: Sequence[WorkspaceFileEffectWingResult],
    rollback_target_ids: Sequence[str] | None = None,
    created_at: str = DEFAULT_CREATED_AT,
    rollback_runner: Any = run_workspace_file_rollback_wing,
) -> tuple[WorkspaceChangeSetRollbackExecutionResult, tuple[WorkspaceFileRollbackWingResult, ...]]:
    if not target_effects:
        return _rollback_not_requested(execution_result, created_at), ()
    ids_by_plan = {wing.rollback_plan.plan_id: target_id for wing, target_id in zip(target_effects, execution_result.applied_target_ids)}
    selected = list(target_effects)
    if rollback_target_ids is not None:
        selected_ids = set(rollback_target_ids)
        selected = [wing for wing in selected if ids_by_plan.get(wing.rollback_plan.plan_id) in selected_ids]
    selected = list(reversed(selected))
    status_entries: list[dict[str, str]] = []
    receipt_ids: list[str] = []
    receipt_digests: list[str] = []
    post_ids: list[str] = []
    post_digests: list[str] = []
    audit_ids: list[str] = []
    audit_digests: list[str] = []
    performed_ids: list[str] = []
    warnings: list[str] = []
    rollback_wings: list[WorkspaceFileRollbackWingResult] = []
    for wing in selected:
        target_id = ids_by_plan.get(wing.rollback_plan.plan_id, wing.receipt.relative_target_path)
        try:
            rollback = rollback_runner(effect_receipt=wing.receipt, rollback_plan=wing.rollback_plan, created_at=created_at)
        except Exception as exc:
            status_entries.append({"target_id": target_id, "rollback_status": "workspace_file_rollback_failed"})
            warnings.append(f"rollback_exception:{type(exc).__name__}:{target_id}")
            continue
        rollback_wings.append(rollback)
        status_entries.append({"target_id": target_id, "rollback_status": rollback.rollback_result.rollback_status})
        receipt_ids.append(rollback.rollback_receipt.receipt_id)
        receipt_digests.append(rollback.rollback_receipt.digest)
        post_ids.append(rollback.rollback_postcondition.check_id)
        post_digests.append(rollback.rollback_postcondition.digest)
        audit_ids.append(rollback.production_audit.audit_id)
        audit_digests.append(rollback.production_audit.digest)
        if rollback.rollback_result.real_rollback_performed:
            performed_ids.append(target_id)
        else:
            warnings.extend(rollback.rollback_result.warning_codes)
    if performed_ids and len(performed_ids) == len(selected) and not warnings:
        status = "workspace_change_set_rollback_performed"
    elif performed_ids and len(performed_ids) == len(selected):
        status = "workspace_change_set_rollback_performed_with_warnings"
    elif performed_ids:
        status = "workspace_change_set_rollback_partially_performed"
    else:
        status = "workspace_change_set_rollback_failed"
    record = WorkspaceChangeSetRollbackExecutionResult(
        rollback_result_id=f"workspace-change-set-rollback-result-{execution_result.result_id}",
        source_execution_result_id=execution_result.result_id,
        workspace_root=execution_result.workspace_root,
        rollback_target_order=tuple(entry["target_id"] for entry in status_entries),
        rollback_target_ids=tuple(performed_ids),
        rollback_status_by_target=tuple(status_entries),
        rollback_receipt_ids=tuple(receipt_ids),
        rollback_receipt_digests=tuple(receipt_digests),
        rollback_postcondition_check_ids=tuple(post_ids),
        rollback_postcondition_check_digests=tuple(post_digests),
        rollback_audit_ids=tuple(audit_ids),
        rollback_audit_digests=tuple(audit_digests),
        rollback_status=status,
        warning_codes=tuple(sorted(set(warnings))),
        risk_codes=execution_result.risk_codes,
        created_at=created_at,
        digest="",
        rollback_performed=bool(performed_ids),
        host_mutation_performed=bool(performed_ids),
    )
    return replace(record, digest=deterministic_digest("workspace-change-set-rollback-result-", record.to_dict())), tuple(rollback_wings)


def build_workspace_change_set_rollback_receipt(
    execution_receipt: WorkspaceChangeSetExecutionReceipt,
    rollback_result: WorkspaceChangeSetRollbackExecutionResult,
    *,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetRollbackReceipt:
    record = WorkspaceChangeSetRollbackReceipt(
        receipt_id=f"workspace-change-set-rollback-receipt-{rollback_result.rollback_result_id}",
        source_execution_receipt_id=execution_receipt.receipt_id,
        rollback_result_id=rollback_result.rollback_result_id,
        workspace_root=rollback_result.workspace_root,
        rollback_status=rollback_result.rollback_status,
        evidence_summary=tuple(str(item) for item in summarize_workspace_change_set_rollback_execution_result(rollback_result).items()),
        rollback_target_order=rollback_result.rollback_target_order,
        rollback_receipt_ids=rollback_result.rollback_receipt_ids,
        rollback_receipt_digests=rollback_result.rollback_receipt_digests,
        blocked_actions=execution_receipt.blocked_actions,
        warning_codes=rollback_result.warning_codes,
        risk_codes=rollback_result.risk_codes,
        created_at=created_at,
        digest="",
        rollback_performed=rollback_result.rollback_performed,
    )
    return replace(record, digest=deterministic_digest("workspace-change-set-rollback-receipt-", record.to_dict()))


def build_workspace_change_set_execution_ledger(
    *,
    request: WorkspaceChangeSetExecutionRequest,
    execution_receipt: WorkspaceChangeSetExecutionReceipt,
    execution_result: WorkspaceChangeSetExecutionResult,
    rollback_receipt: WorkspaceChangeSetRollbackReceipt | None = None,
    rollback_result: WorkspaceChangeSetRollbackExecutionResult | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetExecutionLedger:
    rollback_status_by_target = {entry["target_id"]: entry["rollback_status"] for entry in (rollback_result.rollback_status_by_target if rollback_result else ())}
    entries: list[dict[str, Any]] = []
    for index, target in enumerate(execution_result.target_results):
        entries.append({
            "index": index,
            "target_id": target.target_id,
            "relative_target_path": target.relative_target_path,
            "operation": target.operation,
            "target_execution_status": target.target_execution_status,
            "workspace_effect_receipt_id": target.workspace_effect_receipt_id,
            "workspace_rollback_plan_id": target.workspace_rollback_plan_id,
            "rollback_status": rollback_status_by_target.get(target.target_id),
            "target_write_performed": target.target_write_performed,
        })
    lifecycle = "workspace_change_set_execution_closed_after_rollback" if rollback_receipt and rollback_receipt.rollback_performed else "workspace_change_set_execution_closed_after_execute" if execution_result.all_targets_applied else "workspace_change_set_execution_partially_open" if execution_result.partial_state_visible else "workspace_change_set_execution_open"
    record = WorkspaceChangeSetExecutionLedger(
        ledger_id=f"workspace-change-set-execution-ledger-{execution_receipt.receipt_id}",
        request_id=request.request_id,
        execution_receipt_id=execution_receipt.receipt_id,
        rollback_receipt_id=rollback_receipt.receipt_id if rollback_receipt else None,
        target_event_entries=tuple(entries),
        execution_status=execution_result.execution_status,
        rollback_status=rollback_result.rollback_status if rollback_result else None,
        lifecycle_status=lifecycle,
        warning_codes=tuple(sorted(set(execution_result.warning_codes + (rollback_result.warning_codes if rollback_result else ())))),
        risk_codes=tuple(sorted(set(execution_result.risk_codes + (rollback_result.risk_codes if rollback_result else ())))),
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=deterministic_digest("workspace-change-set-execution-ledger-", record.to_dict()))


def build_workspace_change_set_execution_closure_report(
    *,
    execution_receipt: WorkspaceChangeSetExecutionReceipt,
    execution_result: WorkspaceChangeSetExecutionResult,
    ledger: WorkspaceChangeSetExecutionLedger | None = None,
    rollback_receipt: WorkspaceChangeSetRollbackReceipt | None = None,
    rollback_result: WorkspaceChangeSetRollbackExecutionResult | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetExecutionClosureReport:
    rolled_back = tuple(rollback_result.rollback_target_ids if rollback_result else ())
    open_ids = tuple(target_id for target_id in execution_result.applied_target_ids if target_id not in set(rolled_back))
    issues: list[str] = []
    if execution_result.failed_target_ids:
        issues.append("failed_targets_visible")
    if execution_result.skipped_target_ids:
        issues.append("skipped_targets_visible")
    if open_ids and execution_result.failed_target_ids:
        status = "workspace_change_set_execution_partially_open"
        issues.append("partial_state_visible")
    elif open_ids and execution_result.all_targets_applied and not rollback_result:
        status = "workspace_change_set_execution_closed_after_execute"
    elif open_ids and rollback_result and rollback_result.rollback_performed:
        status = "workspace_change_set_execution_rollback_incomplete"
        issues.append("rollback_incomplete")
    elif not open_ids and rollback_result and rollback_result.rollback_performed:
        status = "workspace_change_set_execution_closed_after_rollback"
    elif execution_result.failed_target_ids and not execution_result.applied_target_ids:
        status = "workspace_change_set_execution_failed"
    elif execution_result.applied_target_ids and not rollback_result and not execution_result.all_targets_applied:
        status = "workspace_change_set_execution_rollback_pending"
        issues.append("rollback_pending")
    else:
        status = "workspace_change_set_execution_open"
    record = WorkspaceChangeSetExecutionClosureReport(
        report_id=f"workspace-change-set-execution-closure-{execution_receipt.receipt_id}",
        ledger_id=ledger.ledger_id if ledger else None,
        execution_receipt_id=execution_receipt.receipt_id,
        rollback_receipt_id=rollback_receipt.receipt_id if rollback_receipt else None,
        closure_status=status,
        applied_target_ids=execution_result.applied_target_ids,
        rolled_back_target_ids=rolled_back,
        open_target_ids=open_ids,
        failed_target_ids=execution_result.failed_target_ids,
        skipped_target_ids=execution_result.skipped_target_ids,
        open_issue_codes=tuple(sorted(set(issues))),
        closure_codes=(status,),
        warning_codes=tuple(sorted(set(execution_result.warning_codes + (rollback_result.warning_codes if rollback_result else ())))),
        risk_codes=tuple(sorted(set(execution_result.risk_codes + (rollback_result.risk_codes if rollback_result else ())))),
        created_at=created_at,
        digest="",
    )
    return replace(record, digest=deterministic_digest("workspace-change-set-execution-closure-", record.to_dict()))


def _validate_record(record: Any, statuses: frozenset[str], status_field: str, contradicted_status: str) -> WorkspaceChangeSetExecutionValidationResult:
    payload = record.to_dict() if hasattr(record, "to_dict") else asdict(record)
    findings = _forbidden_true_findings(record)
    status = str(payload.get(status_field, ""))
    if status not in statuses:
        findings.append(f"unknown_{status_field}")
    return WorkspaceChangeSetExecutionValidationResult(not findings, status if not findings else contradicted_status, tuple(sorted(set(findings))))


def validate_workspace_change_target_execution_result(record: WorkspaceChangeTargetExecutionResult) -> WorkspaceChangeSetExecutionValidationResult:
    return _validate_record(record, TARGET_EXECUTION_STATUSES, "target_execution_status", "workspace_change_target_execution_contradicted")


def validate_workspace_change_set_execution_result(record: WorkspaceChangeSetExecutionResult) -> WorkspaceChangeSetExecutionValidationResult:
    return _validate_record(record, CHANGE_SET_EXECUTION_STATUSES, "execution_status", "workspace_change_set_execution_contradicted")


def validate_workspace_change_set_execution_receipt(record: WorkspaceChangeSetExecutionReceipt) -> WorkspaceChangeSetExecutionValidationResult:
    return _validate_record(record, RECEIPT_STATUSES, "receipt_status", "workspace_change_set_execution_receipt_contradicted")


def validate_workspace_change_set_rollback_execution_result(record: WorkspaceChangeSetRollbackExecutionResult) -> WorkspaceChangeSetExecutionValidationResult:
    return _validate_record(record, ROLLBACK_EXECUTION_STATUSES, "rollback_status", "workspace_change_set_rollback_contradicted")


def validate_workspace_change_set_rollback_receipt(record: WorkspaceChangeSetRollbackReceipt) -> WorkspaceChangeSetExecutionValidationResult:
    return _validate_record(record, ROLLBACK_EXECUTION_STATUSES, "rollback_status", "workspace_change_set_rollback_contradicted")


def validate_workspace_change_set_execution_ledger(record: WorkspaceChangeSetExecutionLedger) -> WorkspaceChangeSetExecutionValidationResult:
    findings = _forbidden_true_findings(record)
    if not record.metadata_only or not record.execution_ledger_only or not record.performs_no_new_effect or record.host_mutation_performed:
        findings.append("contradiction:ledger_effect_claim")
    return WorkspaceChangeSetExecutionValidationResult(not findings, record.lifecycle_status if not findings else "workspace_change_set_execution_contradicted", tuple(sorted(set(findings))))


def validate_workspace_change_set_execution_closure_report(record: WorkspaceChangeSetExecutionClosureReport) -> WorkspaceChangeSetExecutionValidationResult:
    findings = _forbidden_true_findings(record)
    if record.closure_status not in CLOSURE_STATUSES:
        findings.append("unknown_closure_status")
    if not record.metadata_only or not record.closure_report_only or not record.performs_no_new_effect or record.host_mutation_performed:
        findings.append("contradiction:closure_report_effect_claim")
    return WorkspaceChangeSetExecutionValidationResult(not findings, record.closure_status if not findings else "workspace_change_set_execution_contradicted", tuple(sorted(set(findings))))


def summarize_workspace_change_target_execution_result(result: WorkspaceChangeTargetExecutionResult) -> dict[str, Any]:
    return {
        "target_id": result.target_id,
        "relative_target_path": result.relative_target_path,
        "status": result.target_execution_status,
        "target_write_performed": result.target_write_performed,
        "workspace_effect_receipt_id": result.workspace_effect_receipt_id,
        "workspace_rollback_plan_id": result.workspace_rollback_plan_id,
        "general_filesystem_access_performed": False,
    }


def summarize_workspace_change_set_execution_result(result: WorkspaceChangeSetExecutionResult) -> dict[str, Any]:
    return {
        "result_id": result.result_id,
        "execution_status": result.execution_status,
        "applied_target_ids": result.applied_target_ids,
        "failed_target_ids": result.failed_target_ids,
        "skipped_target_ids": result.skipped_target_ids,
        "partial_state_visible": result.partial_state_visible,
        "bounded_change_set_execution_only": True,
        "general_filesystem_access_performed": False,
    }


def summarize_workspace_change_set_execution_receipt(receipt: WorkspaceChangeSetExecutionReceipt) -> dict[str, Any]:
    return {
        "receipt_id": receipt.receipt_id,
        "receipt_status": receipt.receipt_status,
        "applied_target_ids": receipt.applied_target_ids,
        "failed_target_ids": receipt.failed_target_ids,
        "skipped_target_ids": receipt.skipped_target_ids,
        "uses_single_target_workspace_file_helpers": True,
        "not_general_filesystem_access": True,
    }


def summarize_workspace_change_set_rollback_execution_result(result: WorkspaceChangeSetRollbackExecutionResult) -> dict[str, Any]:
    return {
        "rollback_result_id": result.rollback_result_id,
        "rollback_status": result.rollback_status,
        "rollback_target_order": result.rollback_target_order,
        "rolled_back_target_ids": result.rollback_target_ids,
        "exact_target_rollback_only": result.exact_target_rollback_only,
        "recursive_delete_performed": False,
        "wildcard_delete_performed": False,
        "unrelated_file_delete_performed": False,
    }


def summarize_workspace_change_set_rollback_receipt(receipt: WorkspaceChangeSetRollbackReceipt) -> dict[str, Any]:
    return {
        "receipt_id": receipt.receipt_id,
        "rollback_status": receipt.rollback_status,
        "rollback_target_order": receipt.rollback_target_order,
        "exact_target_rollback_only": True,
        "general_cleanup_performed": False,
    }


def summarize_workspace_change_set_execution_ledger(ledger: WorkspaceChangeSetExecutionLedger) -> dict[str, Any]:
    return {
        "ledger_id": ledger.ledger_id,
        "execution_status": ledger.execution_status,
        "rollback_status": ledger.rollback_status,
        "lifecycle_status": ledger.lifecycle_status,
        "target_event_count": len(ledger.target_event_entries),
        "metadata_only": True,
        "performs_no_new_effect": True,
    }


def summarize_workspace_change_set_execution_closure_report(report: WorkspaceChangeSetExecutionClosureReport) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "closure_status": report.closure_status,
        "open_target_ids": report.open_target_ids,
        "failed_target_ids": report.failed_target_ids,
        "skipped_target_ids": report.skipped_target_ids,
        "metadata_only": True,
        "performs_no_new_effect": True,
    }


def _ledger_output_path_is_safe(path_text: str, workspace_root: str) -> tuple[bool, str]:
    if not path_text or path_text.strip() == "":
        return False, "ledger_output_path_required"
    path = Path(path_text).expanduser()
    root = Path(workspace_root).expanduser()
    if path.resolve(strict=False) == Path(path.anchor or "/").resolve(strict=False):
        return False, "ledger_output_path_is_root"
    if path.exists() and path.is_dir():
        return False, "ledger_output_path_is_directory"
    if path.is_symlink():
        return False, "ledger_output_path_is_symlink"
    if not path.parent.exists():
        return False, "ledger_output_parent_missing"
    if not _inside_workspace(root, path):
        return False, "ledger_output_outside_workspace"
    return True, ""


def write_workspace_change_set_execution_ledger_artifact(ledger: WorkspaceChangeSetExecutionLedger, closure_report: WorkspaceChangeSetExecutionClosureReport, *, output_path: str, workspace_root: str) -> dict[str, Any]:
    ok, reason = _ledger_output_path_is_safe(output_path, workspace_root)
    if not ok:
        return {"artifact_written": False, "status": "workspace_change_set_ledger_artifact_blocked", "reason": reason, "path": output_path}
    payload = {
        "metadata_only": True,
        "explicit_ledger_artifact_only": True,
        "performs_no_new_effect": True,
        "host_mutation_performed": False,
        "ledger": ledger.to_dict(),
        "closure_report": closure_report.to_dict(),
    }
    Path(output_path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"artifact_written": True, "status": "workspace_change_set_ledger_artifact_written", "path": output_path, "digest": bytes_digest(json.dumps(payload, sort_keys=True).encode("utf-8"))}


def run_workspace_change_set_execution_wing(
    *,
    manifest: WorkspaceChangeSetManifest,
    preflight_report: WorkspaceChangeSetPreflightReport,
    rollback_plan: WorkspaceChangeSetRollbackPlan,
    transaction_plan: WorkspaceChangeSetTransactionPlan,
    execution_mode: str = "change_set_execute_full_guarded",
    rollback_on_failure: bool | None = None,
    rollback_after_execute: bool = False,
    write_ledger: bool | None = None,
    ledger_output_path: str | None = None,
    policy: WorkspaceChangeSetExecutionPolicy | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> WorkspaceChangeSetExecutionWingResult:
    policy = policy or build_default_workspace_change_set_execution_policy()
    request = build_workspace_change_set_execution_request(
        manifest=manifest,
        preflight_report=preflight_report,
        rollback_plan=rollback_plan,
        transaction_plan=transaction_plan,
        execution_mode=execution_mode,
        rollback_on_failure=rollback_on_failure,
        rollback_after_execute=rollback_after_execute,
        write_ledger=write_ledger,
        ledger_output_path=ledger_output_path,
        policy=policy,
        created_at=created_at,
    )
    execution_result, effect_wings = execute_workspace_change_set(request=request, manifest=manifest, preflight_report=preflight_report, rollback_plan=rollback_plan, transaction_plan=transaction_plan, policy=policy, created_at=created_at)
    execution_receipt = build_workspace_change_set_execution_receipt(request, execution_result, created_at=created_at)
    rollback_result = _rollback_not_requested(execution_result, created_at)
    rollback_receipt: WorkspaceChangeSetRollbackReceipt | None = None
    should_rollback = (request.rollback_after_execute and execution_result.applied_target_ids) or (request.rollback_on_failure and execution_result.failed_target_ids and execution_result.applied_target_ids)
    if should_rollback:
        rollback_result, _rollback_wings = execute_workspace_change_set_rollback(execution_result=execution_result, target_effects=effect_wings, created_at=created_at)
        rollback_receipt = build_workspace_change_set_rollback_receipt(execution_receipt, rollback_result, created_at=created_at)
    ledger = None
    if request.write_ledger:
        ledger = build_workspace_change_set_execution_ledger(request=request, execution_receipt=execution_receipt, execution_result=execution_result, rollback_receipt=rollback_receipt, rollback_result=rollback_result if rollback_result.rollback_status != "workspace_change_set_rollback_not_requested" else None, created_at=created_at)
    closure = build_workspace_change_set_execution_closure_report(execution_receipt=execution_receipt, execution_result=execution_result, ledger=ledger, rollback_receipt=rollback_receipt, rollback_result=rollback_result if rollback_result.rollback_status != "workspace_change_set_rollback_not_requested" else None, created_at=created_at)
    if ledger and ledger_output_path:
        artifact = write_workspace_change_set_execution_ledger_artifact(ledger, closure, output_path=ledger_output_path, workspace_root=request.workspace_root)
        if not artifact.get("artifact_written"):
            ledger = replace(ledger, warning_codes=tuple(sorted(set(ledger.warning_codes + (str(artifact.get("reason")),)))), digest="")
            ledger = replace(ledger, digest=deterministic_digest("workspace-change-set-execution-ledger-", ledger.to_dict()))
    return WorkspaceChangeSetExecutionWingResult(request, execution_result, execution_receipt, rollback_result, rollback_receipt, ledger, closure)
