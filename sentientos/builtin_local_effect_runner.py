"""Bounded built-in local effect runner pilot.

This module is the first in-process delegated runner implementation for the
Host Steward / Delegated Runner Boundary model. It supports only the existing
local diagnostic artifact write and exact-artifact rollback pilots. It is not a
general runner framework and it never uses subprocesses, shell execution,
network egress, provider invocation, prompt assembly, plugin loading, generated
code execution, control-plane admission execution, hardware control, service
control, power control, fan/PWM writes, thermal actuation, or general cleanup.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.local_diagnostic_effect import (
    DEFAULT_ARTIFACT_NAME,
    DEFAULT_CREATED_AT,
    run_local_diagnostic_effect_wing,
    run_local_diagnostic_exact_rollback_wing,
)

RUNNER_DECLARATION_STATUSES = frozenset({
    "builtin_local_runner_declared",
    "builtin_local_runner_declared_with_warnings",
    "builtin_local_runner_blocked",
    "builtin_local_runner_incomplete",
    "builtin_local_runner_contradicted",
})
RUNNER_INVOCATION_REQUEST_STATUSES = frozenset({
    "builtin_runner_invocation_requested",
    "builtin_runner_invocation_blocked",
    "builtin_runner_invocation_incomplete",
    "builtin_runner_invocation_contradicted",
})
RUNNER_INVOCATION_RESULT_STATUSES = frozenset({
    "builtin_runner_invocation_performed",
    "builtin_runner_invocation_blocked",
    "builtin_runner_invocation_failed",
    "builtin_runner_invocation_incomplete",
    "builtin_runner_invocation_contradicted",
})
RUNNER_EXECUTION_RECEIPT_STATUSES = frozenset({
    "builtin_runner_execution_receipt_recorded",
    "builtin_runner_execution_receipt_recorded_with_warnings",
    "builtin_runner_execution_receipt_blocked",
    "builtin_runner_execution_receipt_incomplete",
    "builtin_runner_execution_receipt_contradicted",
})
RUNNER_BLOCK_RECEIPT_STATUSES = frozenset({
    "builtin_runner_block_receipt_recorded",
    "builtin_runner_block_receipt_incomplete",
    "builtin_runner_block_receipt_contradicted",
})
RUNNER_ACTION_KINDS = ("local_diagnostic_artifact_write", "local_diagnostic_exact_rollback")
RUNNER_TRUST_CLASS = "bounded_builtin_runner"
CONTAINMENT_CLASSES = ("local_file_effect_containment", "exact_artifact_rollback_containment")
REQUIRED_RUNNER_LABELS = (
    "delegated_runners_do_not_inherit_ambient_authority",
    "runner_authority_must_be_scoped",
    "runner_authority_must_be_revocable",
    "runner_authority_must_be_auditable",
    "runner_must_have_explicit_capability_grant",
    "runner_must_have_effect_receipt",
    "runner_must_have_postcondition_check",
    "runner_must_have_rollback_plan",
    "runner_must_have_transaction_ledger",
    "local_diagnostic_effect_only",
    "exact_artifact_rollback_only",
)
BLOCKED_ACTIONS = (
    "ambient_authority_inheritance",
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
)
UNTRUSTED_RUNNER_TRUST_CLASSES = ("generated_code_runner", "plugin_runner", "federation_import_runner", "external_tool_runner")
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
    "control_plane_admission_execution_performed",
)
CONTRADICTION_WARNING_CODES = {
    "boundary_contradiction",
    "containment_contradiction",
    "grant_scaffold_contradiction",
    "generated_code_runner_blocked",
    "plugin_runner_blocked",
    "federation_import_runner_blocked",
    "external_tool_runner_blocked",
}


@dataclass(frozen=True)
class BuiltinRunnerValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BuiltinLocalEffectRunnerPolicy:
    policy_id: str
    runner_trust_class: str
    allowed_action_kinds: tuple[str, ...]
    allowed_containment_classes: tuple[str, ...]
    required_runner_labels: tuple[str, ...]
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
class BuiltinLocalEffectRunnerDeclaration:
    declaration_id: str
    runner_label: str
    runner_trust_class: str
    supported_action_kinds: tuple[str, ...]
    supported_containment_classes: tuple[str, ...]
    required_runner_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    declaration_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    declaration_only: bool = True
    runner_implemented: bool = True
    in_process_only: bool = True
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BuiltinRunnerInvocationRequest:
    request_id: str
    runner_declaration_id: str
    boundary_profile_id: str | None
    containment_profile_id: str | None
    grant_scaffold_id: str | None
    action_kind: str
    output_dir: str | None
    artifact_name: str | None
    effect_receipt_path: str | None
    rollback_plan_path: str | None
    output_dir_scope: str | None
    force: bool
    dry_run: bool
    required_runner_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    request_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    runner_invocation_requested: bool = True
    delegated_runner_invoked: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BuiltinRunnerInvocationResult:
    result_id: str
    request_id: str
    action_kind: str
    result_status: str
    produced_record_ids: tuple[str, ...]
    produced_record_digests: tuple[str, ...]
    output_paths: tuple[str, ...]
    evidence_summary: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    delegated_runner_invoked: bool = False
    in_process_only: bool = True
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    local_diagnostic_effect_performed: bool = False
    exact_artifact_rollback_performed: bool = False
    host_mutation_performed: bool = False
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
class BuiltinRunnerExecutionReceipt:
    receipt_id: str
    request_id: str
    result_id: str
    runner_declaration_id: str
    action_kind: str
    receipt_status: str
    evidence_summary: tuple[str, ...]
    produced_record_ids: tuple[str, ...]
    produced_record_digests: tuple[str, ...]
    output_paths: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    runner_execution_receipt_created: bool = True
    delegated_runner_invoked: bool = False
    in_process_only: bool = True
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    host_mutation_performed: bool = False
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
class BuiltinRunnerBlockReceipt:
    receipt_id: str
    request_id: str | None
    runner_declaration_id: str | None
    action_kind: str | None
    block_status: str
    block_reason_codes: tuple[str, ...]
    missing_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    block_receipt_only: bool = True
    delegated_runner_invoked: bool = False
    subprocess_used: bool = False
    shell_used: bool = False
    network_used: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BuiltinLocalEffectRunnerWingRecords(NamedTuple):
    declaration: BuiltinLocalEffectRunnerDeclaration
    request: BuiltinRunnerInvocationRequest
    result: BuiltinRunnerInvocationResult | None
    execution_receipt: BuiltinRunnerExecutionReceipt | None
    block_receipt: BuiltinRunnerBlockReceipt | None


def _source_payload(source: Any) -> Mapping[str, Any]:
    if hasattr(source, "to_dict"):
        return source.to_dict()
    if hasattr(source, "_asdict"):
        return source._asdict()
    if hasattr(source, "__dict__") and not isinstance(source, Mapping):
        return asdict(source)
    return source


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def builtin_local_effect_runner_digest(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload["digest"] = ""
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _digest_id(prefix: str, value: Mapping[str, Any]) -> str:
    return prefix + builtin_local_effect_runner_digest(value)[:24]


def _with_digest(prefix: str, payload: dict[str, Any], id_field: str) -> dict[str, Any]:
    payload[id_field] = _digest_id(prefix, payload)
    payload["digest"] = builtin_local_effect_runner_digest(payload)
    return payload


def _json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def _record_ids_and_digests(records: Sequence[Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ids: list[str] = []
    digests: list[str] = []
    for record in records:
        payload = _source_payload(record)
        for key in ("receipt_id", "check_id", "plan_id", "audit_id", "request_id", "result_id"):
            if payload.get(key):
                ids.append(str(payload[key]))
                break
        if payload.get("digest"):
            digests.append(str(payload["digest"]))
    return tuple(ids), tuple(digests)


def build_default_builtin_local_effect_runner_policy(*, created_at: str = DEFAULT_CREATED_AT) -> BuiltinLocalEffectRunnerPolicy:
    payload = {
        "policy_id": "",
        "runner_trust_class": RUNNER_TRUST_CLASS,
        "allowed_action_kinds": RUNNER_ACTION_KINDS,
        "allowed_containment_classes": CONTAINMENT_CLASSES,
        "required_runner_labels": REQUIRED_RUNNER_LABELS,
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
    return BuiltinLocalEffectRunnerPolicy(**_with_digest("builtin-local-effect-runner-policy-", payload, "policy_id"))


def build_builtin_local_effect_runner_declaration(
    *,
    runner_label: str = "builtin_local_effect_runner",
    runner_trust_class: str = RUNNER_TRUST_CLASS,
    supported_action_kinds: Sequence[str] = RUNNER_ACTION_KINDS,
    supported_containment_classes: Sequence[str] = CONTAINMENT_CLASSES,
    required_runner_labels: Sequence[str] = REQUIRED_RUNNER_LABELS,
    blocked_actions: Sequence[str] = BLOCKED_ACTIONS,
    created_at: str = DEFAULT_CREATED_AT,
) -> BuiltinLocalEffectRunnerDeclaration:
    warnings: list[str] = []
    status = "builtin_local_runner_declared"
    if runner_trust_class != RUNNER_TRUST_CLASS:
        warnings.append(f"{runner_trust_class}_blocked")
        status = "builtin_local_runner_blocked"
    if tuple(supported_action_kinds) != RUNNER_ACTION_KINDS:
        warnings.append("unsupported_action_surface")
        status = "builtin_local_runner_blocked"
    missing_labels = tuple(label for label in REQUIRED_RUNNER_LABELS if label not in required_runner_labels)
    if missing_labels:
        warnings.append("missing_required_runner_labels")
        status = "builtin_local_runner_blocked"
    missing_blocks = tuple(label for label in BLOCKED_ACTIONS if label not in blocked_actions)
    if missing_blocks:
        warnings.append("missing_blocked_action_labels")
        status = "builtin_local_runner_blocked"
    payload = {
        "declaration_id": "",
        "runner_label": runner_label,
        "runner_trust_class": runner_trust_class,
        "supported_action_kinds": tuple(supported_action_kinds),
        "supported_containment_classes": tuple(supported_containment_classes),
        "required_runner_labels": tuple(required_runner_labels),
        "blocked_actions": tuple(blocked_actions),
        "declaration_status": status,
        "warning_codes": tuple(warnings),
        "risk_codes": ("bounded_builtin_runner_can_perform_two_explicit_local_effects",),
        "created_at": created_at,
        "digest": "",
        "metadata_only": True,
        "declaration_only": True,
        "runner_implemented": True,
        "in_process_only": True,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
    }
    return BuiltinLocalEffectRunnerDeclaration(**_with_digest("builtin-local-effect-runner-declaration-", payload, "declaration_id"))


def build_builtin_runner_invocation_request(
    declaration: BuiltinLocalEffectRunnerDeclaration | Mapping[str, Any],
    *,
    action_kind: str,
    output_dir: str | Path | None = None,
    artifact_name: str | None = None,
    effect_receipt_path: str | Path | None = None,
    rollback_plan_path: str | Path | None = None,
    output_dir_scope: str | Path | None = None,
    boundary_profile_id: str | None = "boundary-profile-builtin-local-effect-runner",
    containment_profile_id: str | None = "containment-profile-builtin-local-effect-runner",
    grant_scaffold_id: str | None = "grant-scaffold-builtin-local-effect-runner",
    force: bool = False,
    dry_run: bool = False,
    required_runner_labels: Sequence[str] = REQUIRED_RUNNER_LABELS,
    blocked_actions: Sequence[str] = BLOCKED_ACTIONS,
    created_at: str = DEFAULT_CREATED_AT,
) -> BuiltinRunnerInvocationRequest:
    decl = _source_payload(declaration)
    warnings: list[str] = []
    status = "builtin_runner_invocation_requested"
    if decl.get("runner_trust_class") != RUNNER_TRUST_CLASS:
        warnings.append(f"{decl.get('runner_trust_class', 'unknown_runner')}_blocked")
    if action_kind not in RUNNER_ACTION_KINDS:
        warnings.append("unsupported_action_kind")
    missing_labels = tuple(label for label in REQUIRED_RUNNER_LABELS if label not in required_runner_labels)
    if missing_labels:
        warnings.append("missing_required_runner_labels")
    missing_blocks = tuple(label for label in BLOCKED_ACTIONS if label not in blocked_actions)
    if missing_blocks:
        warnings.append("missing_blocked_action_labels")
    if boundary_profile_id in (None, "", "contradicted"):
        warnings.append("boundary_contradiction")
    if containment_profile_id in (None, "", "contradicted"):
        warnings.append("containment_contradiction")
    if grant_scaffold_id in (None, "", "contradicted"):
        warnings.append("grant_scaffold_contradiction")
    if action_kind == "local_diagnostic_artifact_write" and not output_dir:
        warnings.append("missing_output_dir")
    if action_kind == "local_diagnostic_exact_rollback" and (not effect_receipt_path or not rollback_plan_path or not output_dir_scope):
        warnings.append("missing_exact_rollback_inputs")
    if warnings:
        status = "builtin_runner_invocation_contradicted" if any(code in CONTRADICTION_WARNING_CODES or code.endswith("_blocked") for code in warnings) else "builtin_runner_invocation_blocked"
    payload = {
        "request_id": "",
        "runner_declaration_id": str(decl.get("declaration_id", "")),
        "boundary_profile_id": boundary_profile_id,
        "containment_profile_id": containment_profile_id,
        "grant_scaffold_id": grant_scaffold_id,
        "action_kind": action_kind,
        "output_dir": str(output_dir) if output_dir is not None else None,
        "artifact_name": artifact_name,
        "effect_receipt_path": str(effect_receipt_path) if effect_receipt_path is not None else None,
        "rollback_plan_path": str(rollback_plan_path) if rollback_plan_path is not None else None,
        "output_dir_scope": str(output_dir_scope) if output_dir_scope is not None else None,
        "force": force,
        "dry_run": dry_run,
        "required_runner_labels": tuple(required_runner_labels),
        "blocked_actions": tuple(blocked_actions),
        "request_status": status,
        "warning_codes": tuple(warnings),
        "risk_codes": ("delegated_runner_invocation_can_perform_only_allowed_local_effects",),
        "created_at": created_at,
        "digest": "",
        "runner_invocation_requested": True,
        "delegated_runner_invoked": False,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
    }
    return BuiltinRunnerInvocationRequest(**_with_digest("builtin-runner-invocation-request-", payload, "request_id"))


def _result_payload(request: BuiltinRunnerInvocationRequest, *, status: str, evidence: Sequence[str], output_paths: Sequence[str] = (), produced_records: Sequence[Any] = (), warnings: Sequence[str] = (), local_effect: bool = False, exact_rollback: bool = False, invoked: bool = False, created_at: str | None = None) -> dict[str, Any]:
    ids, digests = _record_ids_and_digests(produced_records)
    performed = local_effect or exact_rollback
    payload = {
        "result_id": "",
        "request_id": request.request_id,
        "action_kind": request.action_kind,
        "result_status": status,
        "produced_record_ids": ids,
        "produced_record_digests": digests,
        "output_paths": tuple(output_paths),
        "evidence_summary": tuple(evidence),
        "warning_codes": tuple(warnings),
        "risk_codes": request.risk_codes,
        "created_at": created_at or request.created_at,
        "digest": "",
        "delegated_runner_invoked": invoked,
        "in_process_only": True,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
        "local_diagnostic_effect_performed": local_effect,
        "exact_artifact_rollback_performed": exact_rollback,
        "host_mutation_performed": performed,
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
    return _with_digest("builtin-runner-invocation-result-", payload, "result_id")


def run_builtin_local_effect_runner(request: BuiltinRunnerInvocationRequest) -> BuiltinRunnerInvocationResult:
    validation = validate_builtin_runner_invocation_request(request)
    if not validation.ok:
        return BuiltinRunnerInvocationResult(**_result_payload(request, status="builtin_runner_invocation_blocked", evidence=("runner invocation blocked before delegated runner ran",), warnings=validation.findings, invoked=False))
    if request.dry_run:
        return BuiltinRunnerInvocationResult(**_result_payload(request, status="builtin_runner_invocation_blocked", evidence=("dry-run request validated; underlying write/delete not performed",), warnings=("dry_run_no_host_mutation_performed",), invoked=False))
    if request.action_kind == "local_diagnostic_artifact_write":
        records = run_local_diagnostic_effect_wing(output_dir=request.output_dir or "", artifact_name=request.artifact_name or DEFAULT_ARTIFACT_NAME, force_overwrite=request.force, dry_run=False, created_at=request.created_at)
        output_dir = Path(request.output_dir or "").expanduser()
        if records.result.effect_status == "local_diagnostic_effect_performed":
            paths = {
                "effect_receipt.json": records.receipt.to_dict(),
                "postcondition_check.json": records.postcondition_check.to_dict(),
                "production_audit.json": records.production_audit_receipt.to_dict(),
                "rollback_plan.json": records.rollback_plan.to_dict(),
            }
            for name, payload in paths.items():
                _json_write(output_dir / name, payload)
        produced = (records.receipt, records.postcondition_check, records.production_audit_receipt, records.rollback_plan)
        success = records.result.effect_status == "local_diagnostic_effect_performed" and records.result.real_effect_performed
        status = "builtin_runner_invocation_performed" if success else "builtin_runner_invocation_failed"
        outputs = tuple(str(output_dir / name) for name in ("effect_receipt.json", "postcondition_check.json", "production_audit.json", "rollback_plan.json")) + (records.result.output_path,)
        evidence = ("in-process local diagnostic artifact write invoked through bounded built-in runner",) if success else ("local diagnostic artifact write did not perform a host mutation",)
        return BuiltinRunnerInvocationResult(**_result_payload(request, status=status, evidence=evidence, output_paths=outputs, produced_records=produced, warnings=records.result.warning_codes, local_effect=success, invoked=True))
    if request.action_kind == "local_diagnostic_exact_rollback":
        effect_receipt = _load_json(request.effect_receipt_path)
        rollback_plan = _load_json(request.rollback_plan_path)
        records = run_local_diagnostic_exact_rollback_wing(effect_receipt, rollback_plan, output_dir_scope=request.output_dir_scope or "", allow_missing_artifact=False, dry_run=False, created_at=request.created_at)
        output_dir = Path(request.output_dir_scope or "").expanduser()
        if records.result.rollback_status == "local_diagnostic_exact_rollback_performed":
            for name, payload in {
                "rollback_receipt.json": records.receipt.to_dict(),
                "rollback_postcondition_check.json": records.postcondition_check.to_dict(),
                "rollback_audit.json": records.audit_receipt.to_dict(),
            }.items():
                _json_write(output_dir / name, payload)
        produced = (records.receipt, records.postcondition_check, records.audit_receipt)
        success = records.result.rollback_status == "local_diagnostic_exact_rollback_performed" and records.result.real_rollback_performed
        status = "builtin_runner_invocation_performed" if success else "builtin_runner_invocation_failed"
        outputs = tuple(str(output_dir / name) for name in ("rollback_receipt.json", "rollback_postcondition_check.json", "rollback_audit.json")) + (records.result.output_path,)
        evidence = ("in-process exact-artifact rollback invoked through bounded built-in runner",) if success else ("exact-artifact rollback did not perform a host mutation",)
        return BuiltinRunnerInvocationResult(**_result_payload(request, status=status, evidence=evidence, output_paths=outputs, produced_records=produced, warnings=records.result.warning_codes, exact_rollback=success, invoked=True))
    return BuiltinRunnerInvocationResult(**_result_payload(request, status="builtin_runner_invocation_blocked", evidence=("unsupported action kind blocked",), warnings=("unsupported_action_kind",), invoked=False))


def build_builtin_runner_execution_receipt(declaration: BuiltinLocalEffectRunnerDeclaration | Mapping[str, Any], request: BuiltinRunnerInvocationRequest, result: BuiltinRunnerInvocationResult, *, created_at: str | None = None) -> BuiltinRunnerExecutionReceipt:
    decl = _source_payload(declaration)
    success = result.result_status == "builtin_runner_invocation_performed"
    if success:
        status = "builtin_runner_execution_receipt_recorded"
    elif result.result_status == "builtin_runner_invocation_blocked":
        status = "builtin_runner_execution_receipt_blocked"
    else:
        status = "builtin_runner_execution_receipt_recorded_with_warnings"
    payload = {
        "receipt_id": "",
        "request_id": request.request_id,
        "result_id": result.result_id,
        "runner_declaration_id": str(decl.get("declaration_id", "")),
        "action_kind": request.action_kind,
        "receipt_status": status,
        "evidence_summary": result.evidence_summary,
        "produced_record_ids": result.produced_record_ids,
        "produced_record_digests": result.produced_record_digests,
        "output_paths": result.output_paths,
        "blocked_actions": request.blocked_actions,
        "warning_codes": result.warning_codes,
        "risk_codes": result.risk_codes,
        "created_at": created_at or result.created_at,
        "digest": "",
        "runner_execution_receipt_created": True,
        "delegated_runner_invoked": result.delegated_runner_invoked,
        "in_process_only": True,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
        "host_mutation_performed": result.host_mutation_performed,
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
    return BuiltinRunnerExecutionReceipt(**_with_digest("builtin-runner-execution-receipt-", payload, "receipt_id"))


def build_builtin_runner_block_receipt(request: BuiltinRunnerInvocationRequest | None = None, declaration: BuiltinLocalEffectRunnerDeclaration | Mapping[str, Any] | None = None, *, action_kind: str | None = None, block_reason_codes: Sequence[str] = (), missing_labels: Sequence[str] = (), created_at: str = DEFAULT_CREATED_AT) -> BuiltinRunnerBlockReceipt:
    decl = _source_payload(declaration) if declaration is not None else {}
    reasons = tuple(block_reason_codes or (getattr(request, "warning_codes", ()) if request is not None else ("blocked_without_request",)))
    payload = {
        "receipt_id": "",
        "request_id": getattr(request, "request_id", None),
        "runner_declaration_id": str(decl.get("declaration_id", "")) if decl else getattr(request, "runner_declaration_id", None),
        "action_kind": action_kind or getattr(request, "action_kind", None),
        "block_status": "builtin_runner_block_receipt_recorded" if reasons else "builtin_runner_block_receipt_incomplete",
        "block_reason_codes": reasons,
        "missing_labels": tuple(missing_labels),
        "blocked_actions": tuple(getattr(request, "blocked_actions", BLOCKED_ACTIONS)),
        "warning_codes": reasons,
        "risk_codes": tuple(getattr(request, "risk_codes", ())),
        "created_at": created_at,
        "digest": "",
        "metadata_only": True,
        "block_receipt_only": True,
        "delegated_runner_invoked": False,
        "subprocess_used": False,
        "shell_used": False,
        "network_used": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
        "host_mutation_performed": False,
    }
    return BuiltinRunnerBlockReceipt(**_with_digest("builtin-runner-block-receipt-", payload, "receipt_id"))


def _validate_common(payload: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    for flag in FORBIDDEN_TRUE_FLAGS:
        if payload.get(flag):
            findings.append(f"forbidden_{flag}")
    return findings


def validate_builtin_local_effect_runner_declaration(record: BuiltinLocalEffectRunnerDeclaration | Mapping[str, Any]) -> BuiltinRunnerValidationResult:
    p = _source_payload(record)
    findings = _validate_common(p)
    if p.get("declaration_status") not in RUNNER_DECLARATION_STATUSES:
        findings.append("unknown_declaration_status")
    if p.get("runner_trust_class") != RUNNER_TRUST_CLASS:
        findings.append("runner_trust_class_not_bounded_builtin")
    if tuple(p.get("supported_action_kinds", ())) != RUNNER_ACTION_KINDS:
        findings.append("supported_action_kinds_not_exact")
    if not p.get("runner_implemented") or not p.get("in_process_only"):
        findings.append("runner_not_bounded_in_process")
    return BuiltinRunnerValidationResult(ok=not findings and p.get("declaration_status") == "builtin_local_runner_declared", findings=tuple(findings))


def validate_builtin_runner_invocation_request(record: BuiltinRunnerInvocationRequest | Mapping[str, Any]) -> BuiltinRunnerValidationResult:
    p = _source_payload(record)
    findings = _validate_common(p)
    if p.get("request_status") not in RUNNER_INVOCATION_REQUEST_STATUSES:
        findings.append("unknown_request_status")
    if p.get("request_status") != "builtin_runner_invocation_requested":
        findings.extend(str(code) for code in p.get("warning_codes", ()))
    if p.get("action_kind") not in RUNNER_ACTION_KINDS:
        findings.append("unsupported_action_kind")
    missing_labels = tuple(label for label in REQUIRED_RUNNER_LABELS if label not in tuple(p.get("required_runner_labels", ())))
    if missing_labels:
        findings.append("missing_required_runner_labels")
    missing_blocks = tuple(label for label in BLOCKED_ACTIONS if label not in tuple(p.get("blocked_actions", ())))
    if missing_blocks:
        findings.append("missing_blocked_action_labels")
    if p.get("action_kind") == "local_diagnostic_artifact_write" and not p.get("output_dir"):
        findings.append("missing_output_dir")
    if p.get("action_kind") == "local_diagnostic_exact_rollback" and (not p.get("effect_receipt_path") or not p.get("rollback_plan_path") or not p.get("output_dir_scope")):
        findings.append("missing_exact_rollback_inputs")
    return BuiltinRunnerValidationResult(ok=not findings and p.get("request_status") == "builtin_runner_invocation_requested", findings=tuple(dict.fromkeys(findings)))


def validate_builtin_runner_invocation_result(record: BuiltinRunnerInvocationResult | Mapping[str, Any]) -> BuiltinRunnerValidationResult:
    p = _source_payload(record)
    findings = _validate_common(p)
    if p.get("result_status") not in RUNNER_INVOCATION_RESULT_STATUSES:
        findings.append("unknown_result_status")
    performed = p.get("result_status") == "builtin_runner_invocation_performed"
    if bool(p.get("host_mutation_performed")) != performed:
        findings.append("host_mutation_performed_mismatch")
    if p.get("local_diagnostic_effect_performed") and p.get("exact_artifact_rollback_performed"):
        findings.append("multiple_action_effects_claimed")
    return BuiltinRunnerValidationResult(ok=not findings, findings=tuple(findings))


def validate_builtin_runner_execution_receipt(record: BuiltinRunnerExecutionReceipt | Mapping[str, Any]) -> BuiltinRunnerValidationResult:
    p = _source_payload(record)
    findings = _validate_common(p)
    if p.get("receipt_status") not in RUNNER_EXECUTION_RECEIPT_STATUSES:
        findings.append("unknown_receipt_status")
    if not p.get("runner_execution_receipt_created"):
        findings.append("missing_runner_execution_receipt_created")
    return BuiltinRunnerValidationResult(ok=not findings, findings=tuple(findings))


def validate_builtin_runner_block_receipt(record: BuiltinRunnerBlockReceipt | Mapping[str, Any]) -> BuiltinRunnerValidationResult:
    p = _source_payload(record)
    findings = _validate_common(p)
    if p.get("block_status") not in RUNNER_BLOCK_RECEIPT_STATUSES:
        findings.append("unknown_block_status")
    if p.get("delegated_runner_invoked") or p.get("host_mutation_performed"):
        findings.append("block_receipt_claims_effect")
    return BuiltinRunnerValidationResult(ok=not findings and p.get("block_status") == "builtin_runner_block_receipt_recorded", findings=tuple(findings))


def summarize_builtin_local_effect_runner_declaration(record: BuiltinLocalEffectRunnerDeclaration | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("declaration_id", "runner_label", "runner_trust_class", "supported_action_kinds", "supported_containment_classes", "declaration_status", "runner_implemented", "in_process_only", "subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "digest")}


def summarize_builtin_runner_invocation_request(record: BuiltinRunnerInvocationRequest | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("request_id", "runner_declaration_id", "action_kind", "output_dir", "artifact_name", "effect_receipt_path", "rollback_plan_path", "output_dir_scope", "dry_run", "request_status", "warning_codes", "runner_invocation_requested", "delegated_runner_invoked", "subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "digest")}


def summarize_builtin_runner_invocation_result(record: BuiltinRunnerInvocationResult | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("result_id", "request_id", "action_kind", "result_status", "produced_record_ids", "produced_record_digests", "output_paths", "evidence_summary", "delegated_runner_invoked", "in_process_only", "subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "local_diagnostic_effect_performed", "exact_artifact_rollback_performed", "host_mutation_performed", "general_cleanup_performed", "recursive_delete_performed", "unrelated_file_delete_performed", "digest")}


def summarize_builtin_runner_execution_receipt(record: BuiltinRunnerExecutionReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("receipt_id", "request_id", "result_id", "runner_declaration_id", "action_kind", "receipt_status", "evidence_summary", "produced_record_ids", "produced_record_digests", "output_paths", "delegated_runner_invoked", "in_process_only", "subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "host_mutation_performed", "general_cleanup_performed", "recursive_delete_performed", "unrelated_file_delete_performed", "digest")}


def summarize_builtin_runner_block_receipt(record: BuiltinRunnerBlockReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("receipt_id", "request_id", "runner_declaration_id", "action_kind", "block_status", "block_reason_codes", "missing_labels", "blocked_actions", "metadata_only", "block_receipt_only", "delegated_runner_invoked", "subprocess_used", "shell_used", "network_used", "provider_invocation_performed", "prompt_assembly_performed", "host_mutation_performed", "digest")}


def run_builtin_local_effect_runner_wing(
    *,
    action_kind: str,
    output_dir: str | Path | None = None,
    artifact_name: str | None = None,
    effect_receipt_path: str | Path | None = None,
    rollback_plan_path: str | Path | None = None,
    output_dir_scope: str | Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    created_at: str = DEFAULT_CREATED_AT,
) -> BuiltinLocalEffectRunnerWingRecords:
    declaration = build_builtin_local_effect_runner_declaration(created_at=created_at)
    request = build_builtin_runner_invocation_request(
        declaration,
        action_kind=action_kind,
        output_dir=output_dir,
        artifact_name=artifact_name,
        effect_receipt_path=effect_receipt_path,
        rollback_plan_path=rollback_plan_path,
        output_dir_scope=output_dir_scope,
        force=force,
        dry_run=dry_run,
        created_at=created_at,
    )
    request_validation = validate_builtin_runner_invocation_request(request)
    if not request_validation.ok:
        return BuiltinLocalEffectRunnerWingRecords(declaration, request, None, None, build_builtin_runner_block_receipt(request, declaration, block_reason_codes=request_validation.findings, created_at=created_at))
    result = run_builtin_local_effect_runner(request)
    if result.result_status == "builtin_runner_invocation_blocked":
        if request.dry_run and "dry_run_no_host_mutation_performed" in result.warning_codes:
            return BuiltinLocalEffectRunnerWingRecords(declaration, request, result, None, None)
        return BuiltinLocalEffectRunnerWingRecords(declaration, request, result, None, build_builtin_runner_block_receipt(request, declaration, block_reason_codes=result.warning_codes, created_at=created_at))
    receipt = build_builtin_runner_execution_receipt(declaration, request, result, created_at=created_at)
    return BuiltinLocalEffectRunnerWingRecords(declaration, request, result, receipt, None)


def summarize_builtin_local_effect_runner_wing(records: BuiltinLocalEffectRunnerWingRecords) -> dict[str, Any]:
    return {
        "declaration": summarize_builtin_local_effect_runner_declaration(records.declaration),
        "request": summarize_builtin_runner_invocation_request(records.request),
        "result": summarize_builtin_runner_invocation_result(records.result) if records.result else None,
        "execution_receipt": summarize_builtin_runner_execution_receipt(records.execution_receipt) if records.execution_receipt else None,
        "block_receipt": summarize_builtin_runner_block_receipt(records.block_receipt) if records.block_receipt else None,
        "bounded_builtin_runner_only": True,
        "supported_action_kinds": RUNNER_ACTION_KINDS,
        "not_general_runner_framework": True,
    }
