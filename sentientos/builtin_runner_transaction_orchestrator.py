"""Bounded runner transaction orchestrator wing.

This module orchestrates only the existing bounded built-in runner actions for
local diagnostic artifact write and optional exact-artifact rollback, then
optionally builds the local effect transaction ledger. It is not a general
runner framework and it does not use subprocesses, shell execution, network
egress, provider invocation, prompt assembly, generated code, plugins,
federation imports, external tools, service/power/hardware/fan/PWM/thermal
control, or general cleanup.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.builtin_local_effect_runner import run_builtin_local_effect_runner_wing
from sentientos.local_diagnostic_effect import DEFAULT_ARTIFACT_NAME, DEFAULT_CREATED_AT
from sentientos.local_effect_transaction_ledger import (
    build_transaction_ledger_from_local_diagnostic_records,
    summarize_local_effect_transaction_ledger,
    summarize_local_effect_transaction_lifecycle_report,
    summarize_local_effect_transaction_ledger_artifact_receipt,
    write_local_effect_transaction_ledger_artifact,
)
from sentientos.workspace_file_transaction_ledger import (
    build_transaction_ledger_from_workspace_file_records,
    write_workspace_file_transaction_ledger_artifact,
)

DIAGNOSTIC_TRANSACTION_MODES = (
    "diagnostic_write_only",
    "diagnostic_write_with_rollback",
    "diagnostic_write_with_ledger",
    "diagnostic_write_rollback_with_ledger",
)
WORKSPACE_FILE_TRANSACTION_MODES = (
    "workspace_file_update_only",
    "workspace_file_update_with_rollback",
    "workspace_file_update_with_ledger",
    "workspace_file_update_rollback_with_ledger",
)
TRANSACTION_MODES = DIAGNOSTIC_TRANSACTION_MODES + WORKSPACE_FILE_TRANSACTION_MODES
PLAN_STATUSES = frozenset({
    "builtin_runner_transaction_plan_ready",
    "builtin_runner_transaction_plan_ready_with_warnings",
    "builtin_runner_transaction_plan_blocked",
    "builtin_runner_transaction_plan_incomplete",
    "builtin_runner_transaction_plan_contradicted",
})
EXECUTION_STATUSES = frozenset({
    "builtin_runner_transaction_requested",
    "builtin_runner_transaction_performed",
    "builtin_runner_transaction_performed_with_warnings",
    "builtin_runner_transaction_blocked",
    "builtin_runner_transaction_failed",
    "builtin_runner_transaction_incomplete",
    "builtin_runner_transaction_contradicted",
})
RECEIPT_STATUSES = frozenset({
    "builtin_runner_transaction_receipt_recorded",
    "builtin_runner_transaction_receipt_recorded_with_warnings",
    "builtin_runner_transaction_receipt_blocked",
    "builtin_runner_transaction_receipt_failed",
    "builtin_runner_transaction_receipt_incomplete",
    "builtin_runner_transaction_receipt_contradicted",
})
CLOSURE_STATUSES = frozenset({
    "builtin_runner_transaction_open",
    "builtin_runner_transaction_closed_after_write",
    "builtin_runner_transaction_closed_after_rollback",
    "builtin_runner_transaction_rollback_pending",
    "builtin_runner_transaction_ledger_pending",
    "builtin_runner_transaction_failed",
    "builtin_runner_transaction_contradicted",
})
REQUIRED_TRANSACTION_LABELS = (
    "bounded_builtin_runner_required",
    "local_diagnostic_artifact_write_only",
    "exact_artifact_rollback_only",
    "transaction_ledger_required_when_requested",
    "workspace_scoped_file_update_only",
    "workspace_scoped_file_exact_rollback_only",
    "workspace_file_transaction_ledger_required_when_requested",
    "single_explicit_workspace_target_only",
    "runner_receipt_required",
    "effect_receipt_required",
    "postcondition_check_required",
    "production_audit_required",
    "rollback_plan_required",
    "rollback_receipt_required_when_rollback_requested",
    "rollback_postcondition_required_when_rollback_requested",
    "rollback_audit_required_when_rollback_requested",
    "no_subprocess",
    "no_shell",
    "no_network",
    "no_provider",
    "no_prompt_assembly",
    "no_general_cleanup",
    "no_hardware_control",
    "no_service_control",
    "no_power_control",
    "no_fan_pwm",
    "no_thermal_actuation",
)
BLOCKED_ACTIONS = (
    "generated_code_execution",
    "plugin_execution",
    "federation_import_execution",
    "external_tool_execution",
    "subprocess_execution",
    "shell_execution",
    "network_egress",
    "provider_invocation",
    "prompt_assembly",
    "os_backend_invocation",
    "hardware_control",
    "fan_pwm_write",
    "thermal_actuation",
    "power_profile_mutation",
    "process_kill",
    "service_restart",
    "package_install",
    "driver_install",
    "general_cleanup",
    "directory_cleanup",
    "recursive_delete",
    "wildcard_delete",
    "unrelated_file_delete",
    "remote_execution",
    "control_plane_admission_execution",
    "general_filesystem_access",
)
FORBIDDEN_TRUE_FLAGS = (
    "subprocess_used",
    "shell_used",
    "network_used",
    "provider_invocation_performed",
    "prompt_assembly_performed",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "power_profile_mutation_performed",
    "process_kill_performed",
    "service_restart_performed",
    "package_install_performed",
    "driver_install_performed",
    "general_cleanup_performed",
    "recursive_delete_performed",
    "unrelated_file_delete_performed",
    "hardware_control_performed",
)


@dataclass(frozen=True)
class BuiltinRunnerTransactionValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BuiltinRunnerTransactionPolicy:
    policy_id: str
    allowed_transaction_modes: tuple[str, ...]
    required_transaction_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    created_at: str
    digest: str
    bounded_builtin_runner_only: bool = True
    in_process_only: bool = True
    general_runner_framework: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BuiltinRunnerTransactionPlan:
    plan_id: str
    transaction_mode: str
    runner_declaration_id: str | None
    output_dir: str
    artifact_name: str
    workspace_root: str | None
    relative_target_path: str | None
    payload_text: str | None
    allow_replace: bool
    ledger_output_path: str | None
    force: bool
    rollback_after_write: bool
    write_ledger: bool
    required_transaction_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    plan_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    plan_only: bool = True
    runner_invoked: bool = False
    host_mutation_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BuiltinRunnerTransactionExecutionRequest:
    request_id: str
    plan_id: str
    transaction_mode: str
    output_dir: str
    artifact_name: str
    workspace_root: str | None
    relative_target_path: str | None
    payload_text: str | None
    allow_replace: bool
    ledger_output_path: str | None
    force: bool
    rollback_after_write: bool
    write_ledger: bool
    required_transaction_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    request_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    transaction_requested: bool = True
    runner_invoked: bool = False
    host_mutation_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BuiltinRunnerTransactionResult:
    result_id: str
    request_id: str
    transaction_mode: str
    write_runner_receipt_id: str | None
    rollback_runner_receipt_id: str | None
    ledger_id: str | None
    lifecycle_report_id: str | None
    ledger_artifact_receipt_id: str | None
    produced_record_ids: tuple[str, ...]
    produced_record_digests: tuple[str, ...]
    produced_paths: tuple[str, ...]
    transaction_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    runner_invoked: bool = False
    local_diagnostic_write_performed: bool = False
    exact_artifact_rollback_performed: bool = False
    workspace_scoped_file_update_performed: bool = False
    workspace_scoped_file_exact_rollback_performed: bool = False
    transaction_ledger_built: bool = False
    ledger_artifact_written: bool = False
    host_mutation_performed: bool = False
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
    general_cleanup_performed: bool = False
    recursive_delete_performed: bool = False
    unrelated_file_delete_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BuiltinRunnerTransactionReceipt:
    receipt_id: str
    request_id: str
    result_id: str
    transaction_mode: str
    receipt_status: str
    evidence_summary: tuple[str, ...]
    write_runner_receipt_id: str | None
    rollback_runner_receipt_id: str | None
    ledger_id: str | None
    lifecycle_report_id: str | None
    ledger_artifact_receipt_id: str | None
    produced_record_ids: tuple[str, ...]
    produced_record_digests: tuple[str, ...]
    produced_paths: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    transaction_receipt_created: bool = True
    runner_invoked: bool = False
    transaction_ledger_built: bool = False
    host_mutation_performed: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    fan_pwm_write_performed: bool = False
    thermal_actuation_performed: bool = False
    power_profile_mutation_performed: bool = False
    service_restart_performed: bool = False
    process_kill_performed: bool = False
    package_install_performed: bool = False
    driver_install_performed: bool = False
    general_cleanup_performed: bool = False
    recursive_delete_performed: bool = False
    unrelated_file_delete_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BuiltinRunnerTransactionClosureReport:
    report_id: str
    transaction_receipt_id: str
    transaction_mode: str
    closure_status: str
    lifecycle_status: str | None
    present_record_kinds: tuple[str, ...]
    missing_record_kinds: tuple[str, ...]
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
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BuiltinRunnerTransactionWingRecords(NamedTuple):
    policy: BuiltinRunnerTransactionPolicy
    plan: BuiltinRunnerTransactionPlan
    request: BuiltinRunnerTransactionExecutionRequest
    result: BuiltinRunnerTransactionResult | None
    receipt: BuiltinRunnerTransactionReceipt | None
    closure_report: BuiltinRunnerTransactionClosureReport | None


def _source_payload(source: Any) -> dict[str, Any]:
    if source is None:
        return {}
    if hasattr(source, "to_dict"):
        return dict(source.to_dict())
    if hasattr(source, "_asdict"):
        return dict(source._asdict())
    return dict(source)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def builtin_runner_transaction_digest(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload["digest"] = ""
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _digest_id(prefix: str, value: Mapping[str, Any]) -> str:
    return prefix + builtin_runner_transaction_digest(value)[:24]


def _with_digest(prefix: str, payload: dict[str, Any], id_field: str) -> dict[str, Any]:
    payload[id_field] = _digest_id(prefix, payload)
    payload["digest"] = builtin_runner_transaction_digest(payload)
    return payload


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _record_ids_digests(records: Sequence[Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ids: list[str] = []
    digests: list[str] = []
    for record in records:
        payload = _source_payload(record)
        for key in ("receipt_id", "report_id", "ledger_id", "check_id", "audit_id", "plan_id", "result_id", "request_id"):
            if payload.get(key):
                ids.append(str(payload[key]))
                break
        if payload.get("digest"):
            digests.append(str(payload["digest"]))
    return tuple(ids), tuple(digests)


def build_default_builtin_runner_transaction_policy(*, created_at: str = DEFAULT_CREATED_AT) -> BuiltinRunnerTransactionPolicy:
    payload = {
        "policy_id": "",
        "allowed_transaction_modes": TRANSACTION_MODES,
        "required_transaction_labels": REQUIRED_TRANSACTION_LABELS,
        "blocked_actions": BLOCKED_ACTIONS,
        "created_at": created_at,
        "digest": "",
        "bounded_builtin_runner_only": True,
        "in_process_only": True,
        "general_runner_framework": False,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
    }
    return BuiltinRunnerTransactionPolicy(**_with_digest("builtin-runner-transaction-policy-", payload, "policy_id"))


def _mode_flags(mode: str) -> tuple[bool, bool]:
    return mode in {"diagnostic_write_with_rollback", "diagnostic_write_rollback_with_ledger", "workspace_file_update_with_rollback", "workspace_file_update_rollback_with_ledger"}, mode in {"diagnostic_write_with_ledger", "diagnostic_write_rollback_with_ledger", "workspace_file_update_with_ledger", "workspace_file_update_rollback_with_ledger"}


def _is_workspace_mode(mode: str) -> bool:
    return mode in WORKSPACE_FILE_TRANSACTION_MODES


def _is_diagnostic_mode(mode: str) -> bool:
    return mode in DIAGNOSTIC_TRANSACTION_MODES


def build_builtin_runner_transaction_plan(
    *,
    output_dir: str | Path = "",
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    transaction_mode: str = "diagnostic_write_only",
    workspace_root: str | Path | None = None,
    relative_target_path: str | None = None,
    payload_text: str | None = None,
    allow_replace: bool = True,
    ledger_output_path: str | Path | None = None,
    force: bool = False,
    runner_declaration_id: str | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> BuiltinRunnerTransactionPlan:
    warnings: list[str] = []
    status = "builtin_runner_transaction_plan_ready"
    if transaction_mode not in TRANSACTION_MODES:
        warnings.append("unsupported_transaction_mode")
        status = "builtin_runner_transaction_plan_blocked"
    workspace_mode = _is_workspace_mode(transaction_mode)
    if _is_diagnostic_mode(transaction_mode) and not str(output_dir):
        warnings.append("missing_output_dir")
        status = "builtin_runner_transaction_plan_incomplete"
    if workspace_mode:
        if not workspace_root:
            warnings.append("missing_workspace_root")
        if not relative_target_path:
            warnings.append("missing_relative_target_path")
        if payload_text is None:
            warnings.append("missing_payload_text")
        if warnings and status == "builtin_runner_transaction_plan_ready":
            status = "builtin_runner_transaction_plan_incomplete"
    rollback, write_ledger = _mode_flags(transaction_mode) if transaction_mode in TRANSACTION_MODES else (False, False)
    if ledger_output_path and not write_ledger:
        warnings.append("ledger_output_ignored_without_ledger_mode")
        status = "builtin_runner_transaction_plan_ready_with_warnings" if status.endswith("ready") else status
    payload = {
        "plan_id": "",
        "transaction_mode": transaction_mode,
        "runner_declaration_id": runner_declaration_id,
        "output_dir": str(output_dir),
        "artifact_name": artifact_name,
        "workspace_root": str(workspace_root) if workspace_root is not None else None,
        "relative_target_path": relative_target_path,
        "payload_text": payload_text,
        "allow_replace": allow_replace,
        "ledger_output_path": str(ledger_output_path) if ledger_output_path is not None else None,
        "force": force,
        "rollback_after_write": rollback,
        "write_ledger": write_ledger,
        "required_transaction_labels": REQUIRED_TRANSACTION_LABELS,
        "blocked_actions": BLOCKED_ACTIONS,
        "plan_status": status,
        "warning_codes": tuple(warnings),
        "risk_codes": ("bounded_runner_transaction_orchestration_can_perform_explicit_local_effects",),
        "created_at": created_at,
        "digest": "",
        "metadata_only": True,
        "plan_only": True,
        "runner_invoked": False,
        "host_mutation_performed": False,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
    }
    return BuiltinRunnerTransactionPlan(**_with_digest("builtin-runner-transaction-plan-", payload, "plan_id"))


def build_builtin_runner_transaction_execution_request(plan: BuiltinRunnerTransactionPlan, *, created_at: str | None = None) -> BuiltinRunnerTransactionExecutionRequest:
    status = "builtin_runner_transaction_requested" if plan.plan_status in {"builtin_runner_transaction_plan_ready", "builtin_runner_transaction_plan_ready_with_warnings"} else "builtin_runner_transaction_blocked"
    payload = {
        "request_id": "",
        "plan_id": plan.plan_id,
        "transaction_mode": plan.transaction_mode,
        "output_dir": plan.output_dir,
        "artifact_name": plan.artifact_name,
        "workspace_root": plan.workspace_root,
        "relative_target_path": plan.relative_target_path,
        "payload_text": plan.payload_text,
        "allow_replace": plan.allow_replace,
        "ledger_output_path": plan.ledger_output_path,
        "force": plan.force,
        "rollback_after_write": plan.rollback_after_write,
        "write_ledger": plan.write_ledger,
        "required_transaction_labels": plan.required_transaction_labels,
        "blocked_actions": plan.blocked_actions,
        "request_status": status,
        "warning_codes": plan.warning_codes,
        "risk_codes": plan.risk_codes,
        "created_at": created_at or plan.created_at,
        "digest": "",
        "transaction_requested": True,
        "runner_invoked": False,
        "host_mutation_performed": False,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
    }
    return BuiltinRunnerTransactionExecutionRequest(**_with_digest("builtin-runner-transaction-request-", payload, "request_id"))


def _result_from_request(request: BuiltinRunnerTransactionExecutionRequest, *, status: str, warnings: Sequence[str] = (), records: Sequence[Any] = (), paths: Sequence[str] = (), write_runner_receipt_id: str | None = None, rollback_runner_receipt_id: str | None = None, ledger_id: str | None = None, lifecycle_report_id: str | None = None, ledger_artifact_receipt_id: str | None = None, write_ok: bool = False, rollback_ok: bool = False, ledger_ok: bool = False, artifact_ok: bool = False, runner_invoked: bool = False) -> BuiltinRunnerTransactionResult:
    ids, digests = _record_ids_digests(records)
    workspace_mode = _is_workspace_mode(request.transaction_mode)
    mutation = write_ok or rollback_ok or artifact_ok
    payload = {
        "result_id": "",
        "request_id": request.request_id,
        "transaction_mode": request.transaction_mode,
        "write_runner_receipt_id": write_runner_receipt_id,
        "rollback_runner_receipt_id": rollback_runner_receipt_id,
        "ledger_id": ledger_id,
        "lifecycle_report_id": lifecycle_report_id,
        "ledger_artifact_receipt_id": ledger_artifact_receipt_id,
        "produced_record_ids": ids,
        "produced_record_digests": digests,
        "produced_paths": tuple(paths),
        "transaction_status": status,
        "warning_codes": tuple(sorted(set(request.warning_codes + tuple(warnings)))),
        "risk_codes": request.risk_codes,
        "created_at": request.created_at,
        "digest": "",
        "runner_invoked": runner_invoked,
        "local_diagnostic_write_performed": write_ok and not workspace_mode,
        "exact_artifact_rollback_performed": rollback_ok and not workspace_mode,
        "workspace_scoped_file_update_performed": write_ok and workspace_mode,
        "workspace_scoped_file_exact_rollback_performed": rollback_ok and workspace_mode,
        "transaction_ledger_built": ledger_ok,
        "ledger_artifact_written": artifact_ok,
        "host_mutation_performed": mutation,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
        "fan_pwm_write_performed": False,
        "thermal_actuation_performed": False,
        "power_profile_mutation_performed": False,
        "process_kill_performed": False,
        "service_restart_performed": False,
        "package_install_performed": False,
        "driver_install_performed": False,
        "general_cleanup_performed": False,
        "recursive_delete_performed": False,
        "unrelated_file_delete_performed": False,
    }
    return BuiltinRunnerTransactionResult(**_with_digest("builtin-runner-transaction-result-", payload, "result_id"))


def _run_workspace_file_transaction(request: BuiltinRunnerTransactionExecutionRequest) -> BuiltinRunnerTransactionResult:
    records: list[Any] = []
    paths: list[str] = []
    warnings: list[str] = []
    write_receipt_id = rollback_receipt_id = ledger_id = report_id = artifact_receipt_id = None
    write_ok = rollback_ok = ledger_ok = artifact_ok = False
    workspace_root = Path(str(request.workspace_root or "")).expanduser()

    write_wing = run_builtin_local_effect_runner_wing(
        action_kind="workspace_scoped_file_update",
        workspace_root=request.workspace_root,
        relative_target_path=request.relative_target_path,
        payload_text=request.payload_text,
        records_dir=request.workspace_root,
        allow_replace=request.allow_replace,
        force=request.force,
        dry_run=False,
        created_at=request.created_at,
    )
    records.extend([write_wing.request])
    if write_wing.result:
        records.append(write_wing.result)
        paths.extend(write_wing.result.output_paths)
    if write_wing.execution_receipt:
        records.append(write_wing.execution_receipt)
        write_receipt_id = write_wing.execution_receipt.receipt_id
    if write_wing.block_receipt:
        records.append(write_wing.block_receipt)
        warnings.extend(write_wing.block_receipt.block_reason_codes)
    write_ok = bool(write_wing.result and write_wing.result.result_status == "builtin_runner_invocation_performed")
    if not write_ok:
        return _result_from_request(request, status="builtin_runner_transaction_failed", warnings=tuple(warnings) or ("workspace_file_update_failed",), records=records, paths=paths, write_runner_receipt_id=write_receipt_id, runner_invoked=bool(write_wing.result and write_wing.result.delegated_runner_invoked))

    if request.rollback_after_write:
        try:
            rollback_wing = run_builtin_local_effect_runner_wing(
                action_kind="workspace_scoped_file_exact_rollback",
                workspace_effect_receipt_path=workspace_root / "workspace_effect_receipt.json",
                workspace_rollback_plan_path=workspace_root / "workspace_rollback_plan.json",
                workspace_root_scope=request.workspace_root,
                dry_run=False,
                created_at=request.created_at,
            )
            records.extend([rollback_wing.request])
            if rollback_wing.result:
                records.append(rollback_wing.result)
                paths.extend(rollback_wing.result.output_paths)
            if rollback_wing.execution_receipt:
                records.append(rollback_wing.execution_receipt)
                rollback_receipt_id = rollback_wing.execution_receipt.receipt_id
            if rollback_wing.block_receipt:
                records.append(rollback_wing.block_receipt)
                warnings.extend(rollback_wing.block_receipt.block_reason_codes)
            rollback_ok = bool(rollback_wing.result and rollback_wing.result.result_status == "builtin_runner_invocation_performed")
        except Exception as exc:  # keep write-success / rollback-failure partial state visible
            rollback_ok = False
            warnings.append("workspace_rollback_failed:" + exc.__class__.__name__)
        if not rollback_ok:
            warnings.append("workspace_rollback_failed_transaction_left_open")

    if request.write_ledger:
        try:
            bundle = build_transaction_ledger_from_workspace_file_records(
                effect_request=_load(workspace_root / "workspace_request.json"),
                preimage=_load(workspace_root / "workspace_preimage.json"),
                effect_result=_load(workspace_root / "workspace_effect_result.json"),
                effect_receipt=_load(workspace_root / "workspace_effect_receipt.json"),
                postcondition_check=_load(workspace_root / "workspace_postcondition_check.json"),
                production_audit=_load(workspace_root / "workspace_production_audit.json"),
                rollback_plan=_load(workspace_root / "workspace_rollback_plan.json"),
                rollback_result=_load(workspace_root / "workspace_rollback_result.json"),
                rollback_receipt=_load(workspace_root / "workspace_rollback_receipt.json"),
                rollback_postcondition_check=_load(workspace_root / "workspace_rollback_postcondition_check.json"),
                rollback_audit=_load(workspace_root / "workspace_rollback_audit.json"),
                created_at=request.created_at,
            )
            ledger, report = bundle.ledger, bundle.lifecycle_report
            ledger_id, report_id = ledger.ledger_id, report.report_id
            ledger_ok = True
            records.extend([ledger, report])
            if request.ledger_output_path:
                artifact_receipt = write_workspace_file_transaction_ledger_artifact(ledger, request.ledger_output_path, lifecycle_report=report, created_at=request.created_at, force=request.force)
                artifact_receipt_id = artifact_receipt.receipt_id
                artifact_ok = True
                records.append(artifact_receipt)
                paths.append(artifact_receipt.output_path)
        except Exception as exc:  # keep partial write/rollback state visible
            warnings.append("workspace_ledger_failed:" + exc.__class__.__name__)

    if request.rollback_after_write and not rollback_ok:
        status = "builtin_runner_transaction_incomplete"
    elif request.write_ledger and not ledger_ok:
        status = "builtin_runner_transaction_incomplete"
        warnings.append("workspace_ledger_pending")
    elif warnings:
        status = "builtin_runner_transaction_performed_with_warnings"
    else:
        status = "builtin_runner_transaction_performed"
    return _result_from_request(request, status=status, warnings=warnings, records=records, paths=paths, write_runner_receipt_id=write_receipt_id, rollback_runner_receipt_id=rollback_receipt_id, ledger_id=ledger_id, lifecycle_report_id=report_id, ledger_artifact_receipt_id=artifact_receipt_id, write_ok=write_ok, rollback_ok=rollback_ok, ledger_ok=ledger_ok, artifact_ok=artifact_ok, runner_invoked=True)


def _run_diagnostic_transaction(request: BuiltinRunnerTransactionExecutionRequest) -> BuiltinRunnerTransactionResult:
    records: list[Any] = []
    paths: list[str] = []
    warnings: list[str] = []
    write_receipt_id = rollback_receipt_id = ledger_id = report_id = artifact_receipt_id = None
    write_ok = rollback_ok = ledger_ok = artifact_ok = False
    out = Path(request.output_dir).expanduser()

    write_wing = run_builtin_local_effect_runner_wing(
        action_kind="local_diagnostic_artifact_write",
        output_dir=request.output_dir,
        artifact_name=request.artifact_name,
        force=request.force,
        dry_run=False,
        created_at=request.created_at,
    )
    records.extend([write_wing.request])
    if write_wing.result:
        records.append(write_wing.result)
        paths.extend(write_wing.result.output_paths)
    if write_wing.execution_receipt:
        records.append(write_wing.execution_receipt)
        write_receipt_id = write_wing.execution_receipt.receipt_id
    if write_wing.block_receipt:
        records.append(write_wing.block_receipt)
        warnings.extend(write_wing.block_receipt.block_reason_codes)
    write_ok = bool(write_wing.result and write_wing.result.result_status == "builtin_runner_invocation_performed")
    if not write_ok:
        return _result_from_request(request, status="builtin_runner_transaction_failed", warnings=tuple(warnings) or ("diagnostic_write_failed",), records=records, paths=paths, write_runner_receipt_id=write_receipt_id, runner_invoked=bool(write_wing.result and write_wing.result.delegated_runner_invoked))

    if request.rollback_after_write:
        try:
            rollback_wing = run_builtin_local_effect_runner_wing(
                action_kind="local_diagnostic_exact_rollback",
                effect_receipt_path=out / "effect_receipt.json",
                rollback_plan_path=out / "rollback_plan.json",
                output_dir_scope=request.output_dir,
                dry_run=False,
                created_at=request.created_at,
            )
            records.extend([rollback_wing.request])
            if rollback_wing.result:
                records.append(rollback_wing.result)
                paths.extend(rollback_wing.result.output_paths)
            if rollback_wing.execution_receipt:
                records.append(rollback_wing.execution_receipt)
                rollback_receipt_id = rollback_wing.execution_receipt.receipt_id
            if rollback_wing.block_receipt:
                records.append(rollback_wing.block_receipt)
                warnings.extend(rollback_wing.block_receipt.block_reason_codes)
            rollback_ok = bool(rollback_wing.result and rollback_wing.result.result_status == "builtin_runner_invocation_performed")
        except Exception as exc:  # keep write-success / rollback-failure partial state visible
            rollback_ok = False
            warnings.append("rollback_failed:" + exc.__class__.__name__)
        if not rollback_ok:
            warnings.append("rollback_failed_transaction_left_open")

    if request.write_ledger:
        try:
            bundle = build_transaction_ledger_from_local_diagnostic_records(
                effect_receipt=_load(out / "effect_receipt.json"),
                postcondition_check=_load(out / "postcondition_check.json"),
                production_audit=_load(out / "production_audit.json"),
                rollback_plan=_load(out / "rollback_plan.json"),
                exact_rollback_receipt=_load(out / "rollback_receipt.json"),
                rollback_postcondition_check=_load(out / "rollback_postcondition_check.json"),
                rollback_audit=_load(out / "rollback_audit.json"),
                created_at=request.created_at,
            )
            ledger, report = bundle.ledger, bundle.lifecycle_report
            ledger_id, report_id = ledger.ledger_id, report.report_id
            ledger_ok = True
            records.extend([ledger, report])
            if request.ledger_output_path:
                artifact_receipt = write_local_effect_transaction_ledger_artifact(ledger, request.ledger_output_path, lifecycle_report=report, created_at=request.created_at, force=request.force)
                artifact_receipt_id = artifact_receipt.receipt_id
                artifact_ok = True
                records.append(artifact_receipt)
                paths.append(artifact_receipt.output_path)
        except Exception as exc:  # keep partial write/rollback state visible
            warnings.append("ledger_failed:" + exc.__class__.__name__)

    if request.rollback_after_write and not rollback_ok:
        status = "builtin_runner_transaction_incomplete"
    elif request.write_ledger and not ledger_ok:
        status = "builtin_runner_transaction_incomplete"
        warnings.append("ledger_pending")
    elif warnings:
        status = "builtin_runner_transaction_performed_with_warnings"
    else:
        status = "builtin_runner_transaction_performed"
    return _result_from_request(request, status=status, warnings=warnings, records=records, paths=paths, write_runner_receipt_id=write_receipt_id, rollback_runner_receipt_id=rollback_receipt_id, ledger_id=ledger_id, lifecycle_report_id=report_id, ledger_artifact_receipt_id=artifact_receipt_id, write_ok=write_ok, rollback_ok=rollback_ok, ledger_ok=ledger_ok, artifact_ok=artifact_ok, runner_invoked=True)


def run_builtin_runner_transaction(request: BuiltinRunnerTransactionExecutionRequest, *, dry_run: bool = False) -> BuiltinRunnerTransactionResult:
    validation = validate_builtin_runner_transaction_execution_request(request)
    if not validation.ok:
        return _result_from_request(request, status="builtin_runner_transaction_blocked", warnings=validation.findings)
    if dry_run:
        return _result_from_request(request, status="builtin_runner_transaction_requested", warnings=("dry_run_no_runner_invoked",))
    if _is_workspace_mode(request.transaction_mode):
        return _run_workspace_file_transaction(request)
    return _run_diagnostic_transaction(request)

def build_builtin_runner_transaction_receipt(request: BuiltinRunnerTransactionExecutionRequest, result: BuiltinRunnerTransactionResult, *, created_at: str | None = None) -> BuiltinRunnerTransactionReceipt:
    validation = validate_builtin_runner_transaction_result(result)
    if not validation.ok:
        status = "builtin_runner_transaction_receipt_contradicted"
    elif result.transaction_status == "builtin_runner_transaction_blocked":
        status = "builtin_runner_transaction_receipt_blocked"
    elif result.transaction_status == "builtin_runner_transaction_failed":
        status = "builtin_runner_transaction_receipt_failed"
    elif result.transaction_status == "builtin_runner_transaction_incomplete":
        status = "builtin_runner_transaction_receipt_incomplete"
    elif result.warning_codes:
        status = "builtin_runner_transaction_receipt_recorded_with_warnings"
    else:
        status = "builtin_runner_transaction_receipt_recorded"
    evidence = (("bounded runner transaction orchestrator used only built-in workspace file update/exact rollback actions",) if _is_workspace_mode(result.transaction_mode) else ("bounded runner transaction orchestrator used only built-in local diagnostic write/exact rollback actions",))
    payload = {
        "receipt_id": "",
        "request_id": request.request_id,
        "result_id": result.result_id,
        "transaction_mode": result.transaction_mode,
        "receipt_status": status,
        "evidence_summary": evidence,
        "write_runner_receipt_id": result.write_runner_receipt_id,
        "rollback_runner_receipt_id": result.rollback_runner_receipt_id,
        "ledger_id": result.ledger_id,
        "lifecycle_report_id": result.lifecycle_report_id,
        "ledger_artifact_receipt_id": result.ledger_artifact_receipt_id,
        "produced_record_ids": result.produced_record_ids,
        "produced_record_digests": result.produced_record_digests,
        "produced_paths": result.produced_paths,
        "blocked_actions": request.blocked_actions,
        "warning_codes": tuple(sorted(set(result.warning_codes + validation.findings))),
        "risk_codes": result.risk_codes,
        "created_at": created_at or result.created_at,
        "digest": "",
        "transaction_receipt_created": True,
        "runner_invoked": result.runner_invoked,
        "transaction_ledger_built": result.transaction_ledger_built,
        "host_mutation_performed": result.host_mutation_performed,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
        "fan_pwm_write_performed": False,
        "thermal_actuation_performed": False,
        "power_profile_mutation_performed": False,
        "service_restart_performed": False,
        "process_kill_performed": False,
        "package_install_performed": False,
        "driver_install_performed": False,
        "general_cleanup_performed": False,
        "recursive_delete_performed": False,
        "unrelated_file_delete_performed": False,
    }
    return BuiltinRunnerTransactionReceipt(**_with_digest("builtin-runner-transaction-receipt-", payload, "receipt_id"))


def build_builtin_runner_transaction_closure_report(receipt: BuiltinRunnerTransactionReceipt, *, result: BuiltinRunnerTransactionResult | None = None, lifecycle_report: Any | None = None, created_at: str | None = None) -> BuiltinRunnerTransactionClosureReport:
    warnings = list(receipt.warning_codes)
    lifecycle_status = _source_payload(lifecycle_report).get("lifecycle_status") if lifecycle_report else None
    if lifecycle_status is None and receipt.ledger_id:
        if _is_workspace_mode(receipt.transaction_mode):
            lifecycle_status = "workspace_file_lifecycle_complete_with_rollback" if receipt.rollback_runner_receipt_id else "workspace_file_lifecycle_rollback_pending"
        else:
            lifecycle_status = "local_effect_lifecycle_complete_with_rollback" if receipt.rollback_runner_receipt_id else "local_effect_lifecycle_rollback_pending"
    present = ["transaction_receipt"]
    missing: list[str] = []
    closure_codes: list[str] = []
    open_issues: list[str] = []
    write_kind = "workspace_file_update_runner_receipt" if _is_workspace_mode(receipt.transaction_mode) else "diagnostic_write_runner_receipt"
    rollback_kind = "workspace_file_rollback_runner_receipt" if _is_workspace_mode(receipt.transaction_mode) else "diagnostic_rollback_runner_receipt"
    if receipt.write_runner_receipt_id:
        present.append(write_kind)
    else:
        missing.append(write_kind)
    if receipt.transaction_mode in {"diagnostic_write_with_rollback", "diagnostic_write_rollback_with_ledger", "workspace_file_update_with_rollback", "workspace_file_update_rollback_with_ledger"}:
        if receipt.rollback_runner_receipt_id:
            present.append(rollback_kind)
        else:
            missing.append(rollback_kind)
            open_issues.append("rollback_pending")
    if receipt.transaction_mode in {"diagnostic_write_with_ledger", "diagnostic_write_rollback_with_ledger", "workspace_file_update_with_ledger", "workspace_file_update_rollback_with_ledger"}:
        if receipt.ledger_id:
            present.append("transaction_ledger")
        else:
            missing.append("transaction_ledger")
            open_issues.append("ledger_pending")
    if receipt.receipt_status.endswith("contradicted"):
        closure = "builtin_runner_transaction_contradicted"
    elif receipt.receipt_status in {"builtin_runner_transaction_receipt_failed", "builtin_runner_transaction_receipt_blocked"}:
        closure = "builtin_runner_transaction_failed"
    elif "ledger_pending" in open_issues:
        closure = "builtin_runner_transaction_ledger_pending"
    elif "rollback_pending" in open_issues:
        closure = "builtin_runner_transaction_rollback_pending"
    elif receipt.rollback_runner_receipt_id:
        closure = "builtin_runner_transaction_closed_after_rollback"
        closure_codes.append("write_and_exact_rollback_recorded")
    elif receipt.write_runner_receipt_id:
        closure = "builtin_runner_transaction_closed_after_write"
        closure_codes.append("write_recorded_without_requested_rollback")
    else:
        closure = "builtin_runner_transaction_open"
    payload = {
        "report_id": "",
        "transaction_receipt_id": receipt.receipt_id,
        "transaction_mode": receipt.transaction_mode,
        "closure_status": closure,
        "lifecycle_status": lifecycle_status,
        "present_record_kinds": tuple(present),
        "missing_record_kinds": tuple(missing),
        "open_issue_codes": tuple(open_issues),
        "closure_codes": tuple(closure_codes),
        "warning_codes": tuple(warnings),
        "risk_codes": receipt.risk_codes,
        "created_at": created_at or receipt.created_at,
        "digest": "",
        "metadata_only": True,
        "closure_report_only": True,
        "performs_no_new_effect": True,
        "host_mutation_performed": False,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
    }
    return BuiltinRunnerTransactionClosureReport(**_with_digest("builtin-runner-transaction-closure-", payload, "report_id"))


def _validate_common(record: Any, *, statuses: frozenset[str], status_field: str) -> list[str]:
    p = _source_payload(record)
    findings: list[str] = []
    if p.get(status_field) not in statuses:
        findings.append("unknown_" + status_field)
    for flag in FORBIDDEN_TRUE_FLAGS:
        if p.get(flag):
            findings.append(f"forbidden_{flag}")
    if p.get("digest") != builtin_runner_transaction_digest(p):
        findings.append("digest_mismatch")
    return findings


def validate_builtin_runner_transaction_plan(record: BuiltinRunnerTransactionPlan | Mapping[str, Any]) -> BuiltinRunnerTransactionValidationResult:
    findings = _validate_common(record, statuses=PLAN_STATUSES, status_field="plan_status")
    p = _source_payload(record)
    if p.get("transaction_mode") not in TRANSACTION_MODES:
        findings.append("unsupported_transaction_mode")
    if p.get("runner_invoked") or p.get("host_mutation_performed"):
        findings.append("plan_claims_effect")
    return BuiltinRunnerTransactionValidationResult(not findings and p.get("plan_status") not in {"builtin_runner_transaction_plan_blocked", "builtin_runner_transaction_plan_contradicted"}, tuple(findings))


def validate_builtin_runner_transaction_execution_request(record: BuiltinRunnerTransactionExecutionRequest | Mapping[str, Any]) -> BuiltinRunnerTransactionValidationResult:
    findings = _validate_common(record, statuses=EXECUTION_STATUSES, status_field="request_status")
    p = _source_payload(record)
    if p.get("request_status") != "builtin_runner_transaction_requested":
        findings.append("request_not_ready")
    if p.get("transaction_mode") not in TRANSACTION_MODES:
        findings.append("unsupported_transaction_mode")
    if _is_diagnostic_mode(str(p.get("transaction_mode"))) and not p.get("output_dir"):
        findings.append("missing_output_dir")
    if _is_workspace_mode(str(p.get("transaction_mode"))):
        if not p.get("workspace_root"):
            findings.append("missing_workspace_root")
        if not p.get("relative_target_path"):
            findings.append("missing_relative_target_path")
        if p.get("payload_text") is None:
            findings.append("missing_payload_text")
    return BuiltinRunnerTransactionValidationResult(not findings, tuple(findings))


def validate_builtin_runner_transaction_result(record: BuiltinRunnerTransactionResult | Mapping[str, Any]) -> BuiltinRunnerTransactionValidationResult:
    findings = _validate_common(record, statuses=EXECUTION_STATUSES, status_field="transaction_status")
    p = _source_payload(record)
    if p.get("transaction_mode") not in TRANSACTION_MODES:
        findings.append("unsupported_transaction_mode")
    return BuiltinRunnerTransactionValidationResult(not findings, tuple(findings))


def validate_builtin_runner_transaction_receipt(record: BuiltinRunnerTransactionReceipt | Mapping[str, Any]) -> BuiltinRunnerTransactionValidationResult:
    findings = _validate_common(record, statuses=RECEIPT_STATUSES, status_field="receipt_status")
    p = _source_payload(record)
    if not p.get("transaction_receipt_created"):
        findings.append("missing_transaction_receipt_created")
    return BuiltinRunnerTransactionValidationResult(not findings, tuple(findings))


def validate_builtin_runner_transaction_closure_report(record: BuiltinRunnerTransactionClosureReport | Mapping[str, Any]) -> BuiltinRunnerTransactionValidationResult:
    findings = _validate_common(record, statuses=CLOSURE_STATUSES, status_field="closure_status")
    p = _source_payload(record)
    if p.get("host_mutation_performed"):
        findings.append("closure_report_claims_effect")
    return BuiltinRunnerTransactionValidationResult(not findings, tuple(findings))


def summarize_builtin_runner_transaction_plan(record: BuiltinRunnerTransactionPlan | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("plan_id", "transaction_mode", "output_dir", "artifact_name", "workspace_root", "relative_target_path", "payload_text", "allow_replace", "ledger_output_path", "force", "rollback_after_write", "write_ledger", "plan_status", "warning_codes", "metadata_only", "plan_only", "runner_invoked", "host_mutation_performed", "subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "digest")}


def summarize_builtin_runner_transaction_execution_request(record: BuiltinRunnerTransactionExecutionRequest | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("request_id", "plan_id", "transaction_mode", "output_dir", "artifact_name", "workspace_root", "relative_target_path", "payload_text", "allow_replace", "ledger_output_path", "force", "rollback_after_write", "write_ledger", "request_status", "warning_codes", "transaction_requested", "runner_invoked", "host_mutation_performed", "subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "digest")}


def summarize_builtin_runner_transaction_result(record: BuiltinRunnerTransactionResult | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("result_id", "request_id", "transaction_mode", "write_runner_receipt_id", "rollback_runner_receipt_id", "ledger_id", "lifecycle_report_id", "ledger_artifact_receipt_id", "produced_record_ids", "produced_record_digests", "produced_paths", "transaction_status", "warning_codes", "runner_invoked", "local_diagnostic_write_performed", "exact_artifact_rollback_performed", "workspace_scoped_file_update_performed", "workspace_scoped_file_exact_rollback_performed", "transaction_ledger_built", "ledger_artifact_written", "host_mutation_performed", "subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "general_cleanup_performed", "recursive_delete_performed", "unrelated_file_delete_performed", "digest")}


def summarize_builtin_runner_transaction_receipt(record: BuiltinRunnerTransactionReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("receipt_id", "request_id", "result_id", "transaction_mode", "receipt_status", "evidence_summary", "write_runner_receipt_id", "rollback_runner_receipt_id", "ledger_id", "lifecycle_report_id", "ledger_artifact_receipt_id", "produced_record_ids", "produced_record_digests", "produced_paths", "runner_invoked", "transaction_ledger_built", "host_mutation_performed", "subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "general_cleanup_performed", "recursive_delete_performed", "unrelated_file_delete_performed", "digest")}


def summarize_builtin_runner_transaction_closure_report(record: BuiltinRunnerTransactionClosureReport | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("report_id", "transaction_receipt_id", "transaction_mode", "closure_status", "lifecycle_status", "present_record_kinds", "missing_record_kinds", "open_issue_codes", "closure_codes", "metadata_only", "closure_report_only", "performs_no_new_effect", "host_mutation_performed", "subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "digest")}


def run_builtin_runner_transaction_wing(
    *,
    output_dir: str | Path = "",
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    transaction_mode: str = "diagnostic_write_only",
    workspace_root: str | Path | None = None,
    relative_target_path: str | None = None,
    payload_text: str | None = None,
    allow_replace: bool = True,
    ledger_output_path: str | Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    created_at: str = DEFAULT_CREATED_AT,
) -> BuiltinRunnerTransactionWingRecords:
    policy = build_default_builtin_runner_transaction_policy(created_at=created_at)
    plan = build_builtin_runner_transaction_plan(output_dir=output_dir, artifact_name=artifact_name, transaction_mode=transaction_mode, workspace_root=workspace_root, relative_target_path=relative_target_path, payload_text=payload_text, allow_replace=allow_replace, ledger_output_path=ledger_output_path, force=force, created_at=created_at)
    request = build_builtin_runner_transaction_execution_request(plan, created_at=created_at)
    if not validate_builtin_runner_transaction_plan(plan).ok or not validate_builtin_runner_transaction_execution_request(request).ok:
        result = _result_from_request(request, status="builtin_runner_transaction_blocked", warnings=plan.warning_codes)
    else:
        result = run_builtin_runner_transaction(request, dry_run=dry_run)
    receipt = build_builtin_runner_transaction_receipt(request, result, created_at=created_at)
    closure = build_builtin_runner_transaction_closure_report(receipt, result=result, created_at=created_at)
    return BuiltinRunnerTransactionWingRecords(policy, plan, request, result, receipt, closure)


def summarize_builtin_runner_transaction_wing(records: BuiltinRunnerTransactionWingRecords) -> dict[str, Any]:
    return {
        "policy": {"policy_id": records.policy.policy_id, "allowed_transaction_modes": records.policy.allowed_transaction_modes, "bounded_builtin_runner_only": True, "not_general_runner_framework": True, "digest": records.policy.digest},
        "plan": summarize_builtin_runner_transaction_plan(records.plan),
        "request": summarize_builtin_runner_transaction_execution_request(records.request),
        "result": summarize_builtin_runner_transaction_result(records.result) if records.result else None,
        "receipt": summarize_builtin_runner_transaction_receipt(records.receipt) if records.receipt else None,
        "closure_report": summarize_builtin_runner_transaction_closure_report(records.closure_report) if records.closure_report else None,
        "bounded_transaction_orchestrator_only": True,
        "supported_runner_actions": ("local_diagnostic_artifact_write", "local_diagnostic_exact_rollback", "workspace_scoped_file_update", "workspace_scoped_file_exact_rollback"),
        "single_explicit_workspace_target_only": True,
        "no_general_filesystem_access": True,
        "transaction_ledger_explicit": True,
        "not_general_runner_framework": True,
    }
