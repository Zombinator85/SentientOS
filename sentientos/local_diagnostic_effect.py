"""Tier-1 local diagnostic effect pilot.

This module implements exactly one deliberately narrow real effect: writing one
metadata-only diagnostic artifact to an explicit caller-supplied local output
directory. It does not perform hardware control, service control, cleanup,
network egress, provider invocation, prompt assembly, subprocess execution,
shell execution, OS backend invocation, or control-plane execution.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

EFFECT_STATUSES = frozenset({
    "local_diagnostic_effect_requested",
    "local_diagnostic_effect_performed",
    "local_diagnostic_effect_blocked",
    "local_diagnostic_effect_incomplete",
    "local_diagnostic_effect_contradicted",
})
POSTCONDITION_STATUSES = frozenset({
    "local_diagnostic_postcondition_passed",
    "local_diagnostic_postcondition_passed_with_warnings",
    "local_diagnostic_postcondition_failed",
    "local_diagnostic_postcondition_blocked",
    "local_diagnostic_postcondition_incomplete",
    "local_diagnostic_postcondition_contradicted",
})
ROLLBACK_STATUSES = frozenset({
    "local_diagnostic_rollback_plan_ready",
    "local_diagnostic_rollback_plan_ready_with_warnings",
    "local_diagnostic_rollback_performed",
    "local_diagnostic_rollback_blocked",
    "local_diagnostic_rollback_incomplete",
    "local_diagnostic_rollback_contradicted",
})
AUDIT_STATUSES = frozenset({
    "local_diagnostic_production_audit_recorded",
    "local_diagnostic_production_audit_recorded_with_warnings",
    "local_diagnostic_production_audit_blocked",
    "local_diagnostic_production_audit_incomplete",
    "local_diagnostic_production_audit_contradicted",
})
EFFECT_DOMAINS = frozenset({
    "diagnostics_local_file_effect",
    "resource_pressure_local_file_effect",
    "operator_review_local_file_effect",
})
LOW_RISK_ADMISSION_DOMAINS = frozenset({
    "diagnostics_real_effect_candidate",
    "resource_pressure_real_effect_candidate",
    "operator_review_real_effect_candidate",
})
BLOCKING_ADMISSION_STATUSES = frozenset({
    "real_effect_admission_blocked",
    "real_effect_admission_incomplete",
    "real_effect_admission_contradicted",
})
BLOCKED_ACTION_LABELS = (
    "fan_pwm_write",
    "thermal_actuation",
    "power_profile_mutation",
    "process_kill",
    "service_restart",
    "package_install",
    "driver_install",
    "file_cleanup_unrelated",
    "file_delete_unrelated",
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
FORBIDDEN_PERFORMED_FLAGS = (
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "power_profile_mutation_performed",
    "process_kill_performed",
    "service_restart_performed",
    "package_install_performed",
    "driver_install_performed",
    "file_cleanup_performed",
    "file_delete_performed",
    "provider_invocation_performed",
    "network_performed",
    "prompt_assembly_performed",
    "subprocess_performed",
    "shell_performed",
    "os_backend_invoked",
    "control_plane_admission_execution_performed",
)
DEFAULT_ARTIFACT_NAME = "sentientos_local_diagnostic_effect.json"
DEFAULT_CREATED_AT = "1970-01-01T00:00:00+00:00"


@dataclass(frozen=True)
class LocalDiagnosticEffectValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalDiagnosticEffectPolicy:
    policy_id: str
    allowed_effect_domains: tuple[str, ...]
    low_risk_source_admission_domains: tuple[str, ...]
    required_scope_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    default_artifact_media_type: str = "application/json"
    warning_codes: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ("tier1_local_file_write_is_real_host_mutation",)
    local_only: bool = True
    diagnostic_only: bool = True
    exact_artifact_rollback_deferred: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalDiagnosticEffectRequest:
    request_id: str
    source_real_effect_admission_bundle_id: str | None
    source_real_effect_admission_bundle_digest: str | None
    effect_domain: str
    output_dir: str
    artifact_name: str
    artifact_media_type: str
    artifact_payload_summary: str
    force_overwrite: bool
    required_scope_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    request_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    local_effect_requested: bool = True
    diagnostic_only: bool = True
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    subprocess_performed: bool = False
    shell_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalDiagnosticEffectResult:
    result_id: str
    request_id: str
    output_path: str
    artifact_digest: str
    byte_count: int
    effect_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    real_effect_performed: bool = False
    local_file_write_performed: bool = False
    host_mutation_performed: bool = False
    fan_pwm_write_performed: bool = False
    thermal_actuation_performed: bool = False
    power_profile_mutation_performed: bool = False
    process_kill_performed: bool = False
    service_restart_performed: bool = False
    package_install_performed: bool = False
    driver_install_performed: bool = False
    file_cleanup_performed: bool = False
    file_delete_performed: bool = False
    provider_invocation_performed: bool = False
    network_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalDiagnosticEffectReceipt:
    receipt_id: str
    request_id: str
    result_id: str
    effect_domain: str
    output_path: str
    artifact_digest: str
    byte_count: int
    effect_status: str
    evidence_summary: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    real_effect_receipt_created: bool = False
    real_effect_performed: bool = False
    local_file_write_performed: bool = False
    host_mutation_performed: bool = False
    diagnostic_only: bool = True
    fan_pwm_write_performed: bool = False
    thermal_actuation_performed: bool = False
    power_profile_mutation_performed: bool = False
    process_kill_performed: bool = False
    service_restart_performed: bool = False
    package_install_performed: bool = False
    driver_install_performed: bool = False
    file_cleanup_performed: bool = False
    file_delete_performed: bool = False
    provider_invocation_performed: bool = False
    network_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalDiagnosticPostconditionCheck:
    check_id: str
    receipt_id: str
    output_path: str
    expected_artifact_digest: str
    observed_artifact_digest: str
    expected_byte_count: int
    observed_byte_count: int
    postcondition_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    real_postcondition_check_performed: bool = True
    host_mutation_performed: bool = False
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalDiagnosticRollbackPlan:
    plan_id: str
    receipt_id: str
    output_path: str
    rollback_strategy_labels: tuple[str, ...]
    rollback_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    rollback_plan_only: bool = True
    real_rollback_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalDiagnosticRollbackReceipt:
    receipt_id: str
    plan_id: str
    output_path: str
    rollback_status: str
    rollback_reason_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    rollback_receipt_only: bool = True
    real_rollback_performed: bool = False
    host_mutation_performed: bool = False
    file_delete_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalDiagnosticProductionAuditReceipt:
    audit_id: str
    effect_receipt_id: str
    postcondition_check_id: str
    rollback_plan_id: str
    rollback_receipt_id: str | None
    audit_status: str
    evidence_summary: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    production_audit_receipt_created: bool = True
    audit_for_local_diagnostic_effect_only: bool = True
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LocalDiagnosticEffectWingRecords(NamedTuple):
    request: LocalDiagnosticEffectRequest
    result: LocalDiagnosticEffectResult
    receipt: LocalDiagnosticEffectReceipt
    postcondition_check: LocalDiagnosticPostconditionCheck
    rollback_plan: LocalDiagnosticRollbackPlan
    rollback_receipt: LocalDiagnosticRollbackReceipt
    production_audit_receipt: LocalDiagnosticProductionAuditReceipt


def _tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _source_payload(source: Any) -> Mapping[str, Any]:
    return source.to_dict() if hasattr(source, "to_dict") else dict(source)


def _payload(record_or_payload: Any) -> dict[str, Any]:
    payload = dict(_source_payload(record_or_payload))
    payload["digest"] = ""
    return payload


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def local_diagnostic_effect_digest(record_or_payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(_payload(record_or_payload)).encode("utf-8")).hexdigest()


local_diagnostic_effect_request_digest = local_diagnostic_effect_digest
local_diagnostic_effect_result_digest = local_diagnostic_effect_digest
local_diagnostic_effect_receipt_digest = local_diagnostic_effect_digest
local_diagnostic_postcondition_check_digest = local_diagnostic_effect_digest
local_diagnostic_rollback_plan_digest = local_diagnostic_effect_digest
local_diagnostic_rollback_receipt_digest = local_diagnostic_effect_digest
local_diagnostic_production_audit_receipt_digest = local_diagnostic_effect_digest


def _digest_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]


def _artifact_bytes(request: LocalDiagnosticEffectRequest, payload: Mapping[str, Any] | None = None) -> bytes:
    artifact = {
        "schema_version": "sentientos.local_diagnostic_effect.v1",
        "effect_domain": request.effect_domain,
        "request_id": request.request_id,
        "created_at": request.created_at,
        "artifact_payload_summary": request.artifact_payload_summary,
        "diagnostic_only": True,
        "local_only": True,
        "network_performed": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
        "subprocess_performed": False,
        "shell_performed": False,
        "blocked_actions": tuple(request.blocked_actions),
        "payload": dict(payload or {}),
    }
    return (_canonical_json(artifact) + "\n").encode("utf-8")


def _artifact_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_default_local_diagnostic_effect_policy() -> LocalDiagnosticEffectPolicy:
    return LocalDiagnosticEffectPolicy(
        policy_id="local-diagnostic-effect-policy-v1",
        allowed_effect_domains=tuple(sorted(EFFECT_DOMAINS)),
        low_risk_source_admission_domains=tuple(sorted(LOW_RISK_ADMISSION_DOMAINS)),
        required_scope_labels=("explicit_output_dir_required", "single_artifact_name_required", "diagnostic_metadata_only", "local_file_write_only"),
        blocked_actions=BLOCKED_ACTION_LABELS,
    )


def _output_dir_findings(output_dir: str) -> list[str]:
    findings: list[str] = []
    if not str(output_dir).strip():
        findings.append("empty_output_dir")
        return findings
    path = Path(output_dir).expanduser()
    if path == path.anchor or str(path.resolve()) == path.anchor:
        findings.append("output_dir_is_filesystem_root")
    return findings


def _artifact_name_findings(artifact_name: str) -> list[str]:
    findings: list[str] = []
    if not artifact_name or not artifact_name.strip():
        findings.append("empty_artifact_name")
    candidate = Path(artifact_name)
    if candidate.is_absolute():
        findings.append("absolute_artifact_name")
    if any(sep and sep in artifact_name for sep in ("/", os.sep, os.altsep)):
        findings.append("artifact_name_contains_path_separator")
    if ".." in candidate.parts or artifact_name in {".", ".."}:
        findings.append("artifact_name_path_traversal")
    return findings


def _source_admission_findings(source: Any | None, policy: LocalDiagnosticEffectPolicy) -> tuple[list[str], tuple[str | None, str | None]]:
    if source is None:
        return [], (None, None)
    payload = _source_payload(source)
    findings: list[str] = []
    bundle_id = payload.get("bundle_id")
    digest = payload.get("digest")
    if payload.get("bundle_status") in BLOCKING_ADMISSION_STATUSES:
        findings.append("source_real_effect_admission_not_eligible")
    if payload.get("admission_domain") not in policy.low_risk_source_admission_domains:
        findings.append("source_real_effect_admission_domain_not_low_risk")
    return findings, (str(bundle_id) if bundle_id else None, str(digest) if digest else None)


def build_local_diagnostic_effect_request(
    *,
    output_dir: str | Path,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    artifact_media_type: str = "application/json",
    artifact_payload_summary: str = "deterministic local diagnostic metadata artifact",
    effect_domain: str = "diagnostics_local_file_effect",
    force_overwrite: bool = False,
    required_scope_labels: Sequence[str] | None = None,
    blocked_actions: Sequence[str] | None = None,
    source_real_effect_admission_bundle: Any | None = None,
    created_at: str = DEFAULT_CREATED_AT,
    policy: LocalDiagnosticEffectPolicy | None = None,
) -> LocalDiagnosticEffectRequest:
    policy = policy or build_default_local_diagnostic_effect_policy()
    warnings: list[str] = []
    risks = list(policy.risk_codes)
    source_findings, (source_id, source_digest) = _source_admission_findings(source_real_effect_admission_bundle, policy)
    findings = _output_dir_findings(str(output_dir)) + _artifact_name_findings(artifact_name) + source_findings
    if effect_domain not in policy.allowed_effect_domains:
        findings.append("unsupported_effect_domain")
    status = "local_diagnostic_effect_requested" if not findings else "local_diagnostic_effect_blocked"
    warnings.extend(findings)
    payload = {
        "request_id": "",
        "source_real_effect_admission_bundle_id": source_id,
        "source_real_effect_admission_bundle_digest": source_digest,
        "effect_domain": effect_domain,
        "output_dir": str(output_dir),
        "artifact_name": artifact_name,
        "artifact_media_type": artifact_media_type,
        "artifact_payload_summary": artifact_payload_summary,
        "force_overwrite": bool(force_overwrite),
        "required_scope_labels": tuple(required_scope_labels or policy.required_scope_labels),
        "blocked_actions": tuple(blocked_actions or policy.blocked_actions),
        "request_status": status,
        "warning_codes": tuple(warnings),
        "risk_codes": tuple(risks),
        "created_at": created_at,
        "digest": "",
        "local_effect_requested": True,
        "diagnostic_only": True,
        "network_performed": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
        "subprocess_performed": False,
        "shell_performed": False,
    }
    payload["request_id"] = _digest_id("local-diagnostic-effect-request-", payload)
    payload["digest"] = local_diagnostic_effect_request_digest(payload)
    return LocalDiagnosticEffectRequest(**payload)


def _output_path(request: LocalDiagnosticEffectRequest) -> Path:
    return Path(request.output_dir).expanduser() / request.artifact_name


def validate_local_diagnostic_effect_request(request: LocalDiagnosticEffectRequest | Mapping[str, Any]) -> LocalDiagnosticEffectValidationResult:
    p = _source_payload(request)
    findings = _output_dir_findings(str(p.get("output_dir", ""))) + _artifact_name_findings(str(p.get("artifact_name", "")))
    if p.get("effect_domain") not in EFFECT_DOMAINS:
        findings.append("unsupported_effect_domain")
    if p.get("request_status") not in EFFECT_STATUSES:
        findings.append("unknown_request_status")
    for flag in ("network_performed", "provider_invocation_performed", "prompt_assembly_performed", "subprocess_performed", "shell_performed"):
        if p.get(flag):
            findings.append(f"forbidden_{flag}")
    return LocalDiagnosticEffectValidationResult(ok=not findings and p.get("request_status") == "local_diagnostic_effect_requested", findings=tuple(findings))


def _blocked_result(request: LocalDiagnosticEffectRequest, status: str, warnings: Sequence[str], created_at: str) -> LocalDiagnosticEffectResult:
    out = str(_output_path(request))
    payload = {
        "result_id": "",
        "request_id": request.request_id,
        "output_path": out,
        "artifact_digest": "",
        "byte_count": 0,
        "effect_status": status,
        "warning_codes": tuple(warnings),
        "risk_codes": request.risk_codes,
        "created_at": created_at,
        "digest": "",
        "real_effect_performed": False,
        "local_file_write_performed": False,
        "host_mutation_performed": False,
    }
    payload["result_id"] = _digest_id("local-diagnostic-effect-result-", payload)
    payload["digest"] = local_diagnostic_effect_result_digest(payload)
    return LocalDiagnosticEffectResult(**payload)


def perform_local_diagnostic_effect(
    request: LocalDiagnosticEffectRequest,
    *,
    artifact_payload: Mapping[str, Any] | None = None,
    dry_run: bool = False,
    created_at: str | None = None,
) -> LocalDiagnosticEffectResult:
    created = created_at or request.created_at
    validation = validate_local_diagnostic_effect_request(request)
    if not validation.ok:
        return _blocked_result(request, "local_diagnostic_effect_blocked", validation.findings, created)
    out_dir = Path(request.output_dir).expanduser()
    out_path = _output_path(request)
    resolved_dir = out_dir.resolve(strict=False)
    resolved_out = out_path.resolve(strict=False)
    if resolved_out.parent != resolved_dir:
        return _blocked_result(request, "local_diagnostic_effect_contradicted", ("output_path_escapes_output_dir",), created)
    data = _artifact_bytes(request, artifact_payload)
    digest = _artifact_digest(data)
    if dry_run:
        return _blocked_result(request, "local_diagnostic_effect_requested", ("dry_run_no_write_performed",), created)
    if out_path.exists() and not request.force_overwrite:
        return _blocked_result(request, "local_diagnostic_effect_blocked", ("artifact_exists_without_force",), created)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = out_dir / f".{request.artifact_name}.{request.request_id}.tmp"
    with tmp_path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, out_path)
    payload = {
        "result_id": "",
        "request_id": request.request_id,
        "output_path": str(out_path),
        "artifact_digest": digest,
        "byte_count": len(data),
        "effect_status": "local_diagnostic_effect_performed",
        "warning_codes": (),
        "risk_codes": request.risk_codes,
        "created_at": created,
        "digest": "",
        "real_effect_performed": True,
        "local_file_write_performed": True,
        "host_mutation_performed": True,
    }
    payload["result_id"] = _digest_id("local-diagnostic-effect-result-", payload)
    payload["digest"] = local_diagnostic_effect_result_digest(payload)
    return LocalDiagnosticEffectResult(**payload)


def build_local_diagnostic_effect_receipt(request: LocalDiagnosticEffectRequest, result: LocalDiagnosticEffectResult, *, created_at: str | None = None) -> LocalDiagnosticEffectReceipt:
    success = result.effect_status == "local_diagnostic_effect_performed"
    payload = {
        "receipt_id": "",
        "request_id": request.request_id,
        "result_id": result.result_id,
        "effect_domain": request.effect_domain,
        "output_path": result.output_path,
        "artifact_digest": result.artifact_digest,
        "byte_count": result.byte_count,
        "effect_status": result.effect_status,
        "evidence_summary": ("single deterministic diagnostic artifact write to explicit output directory",) if success else ("effect not performed",),
        "blocked_actions": request.blocked_actions,
        "warning_codes": result.warning_codes,
        "risk_codes": result.risk_codes,
        "created_at": created_at or result.created_at,
        "digest": "",
        "real_effect_receipt_created": success,
        "real_effect_performed": success,
        "local_file_write_performed": success,
        "host_mutation_performed": success,
    }
    payload["receipt_id"] = _digest_id("local-diagnostic-effect-receipt-", payload)
    payload["digest"] = local_diagnostic_effect_receipt_digest(payload)
    return LocalDiagnosticEffectReceipt(**payload)


def perform_local_diagnostic_postcondition_check(receipt: LocalDiagnosticEffectReceipt, *, created_at: str | None = None) -> LocalDiagnosticPostconditionCheck:
    warnings: tuple[str, ...] = ()
    observed_digest = ""
    observed_count = 0
    status = "local_diagnostic_postcondition_blocked"
    if receipt.real_effect_performed and receipt.output_path:
        try:
            data = Path(receipt.output_path).read_bytes()
            observed_digest = _artifact_digest(data)
            observed_count = len(data)
            status = "local_diagnostic_postcondition_passed" if observed_digest == receipt.artifact_digest and observed_count == receipt.byte_count else "local_diagnostic_postcondition_failed"
        except OSError:
            warnings = ("artifact_readback_failed",)
            status = "local_diagnostic_postcondition_failed"
    payload = {
        "check_id": "",
        "receipt_id": receipt.receipt_id,
        "output_path": receipt.output_path,
        "expected_artifact_digest": receipt.artifact_digest,
        "observed_artifact_digest": observed_digest,
        "expected_byte_count": receipt.byte_count,
        "observed_byte_count": observed_count,
        "postcondition_status": status,
        "warning_codes": warnings,
        "risk_codes": receipt.risk_codes,
        "created_at": created_at or receipt.created_at,
        "digest": "",
    }
    payload["check_id"] = _digest_id("local-diagnostic-postcondition-", payload)
    payload["digest"] = local_diagnostic_postcondition_check_digest(payload)
    return LocalDiagnosticPostconditionCheck(**payload)


def build_local_diagnostic_rollback_plan(receipt: LocalDiagnosticEffectReceipt, *, created_at: str | None = None) -> LocalDiagnosticRollbackPlan:
    warnings = ("exact_artifact_rollback_execution_deferred",)
    payload = {
        "plan_id": "",
        "receipt_id": receipt.receipt_id,
        "output_path": receipt.output_path,
        "rollback_strategy_labels": ("exact_artifact_path_known", "manual_operator_removal_possible", "automatic_deletion_not_performed_by_default"),
        "rollback_status": "local_diagnostic_rollback_plan_ready_with_warnings",
        "warning_codes": warnings,
        "risk_codes": receipt.risk_codes,
        "created_at": created_at or receipt.created_at,
        "digest": "",
    }
    payload["plan_id"] = _digest_id("local-diagnostic-rollback-plan-", payload)
    payload["digest"] = local_diagnostic_rollback_plan_digest(payload)
    return LocalDiagnosticRollbackPlan(**payload)


def build_local_diagnostic_rollback_receipt(plan: LocalDiagnosticRollbackPlan, *, created_at: str | None = None) -> LocalDiagnosticRollbackReceipt:
    payload = {
        "receipt_id": "",
        "plan_id": plan.plan_id,
        "output_path": plan.output_path,
        "rollback_status": "local_diagnostic_rollback_incomplete",
        "rollback_reason_codes": ("rollback_execution_deferred_no_deletion_performed",),
        "warning_codes": plan.warning_codes,
        "risk_codes": plan.risk_codes,
        "created_at": created_at or plan.created_at,
        "digest": "",
    }
    payload["receipt_id"] = _digest_id("local-diagnostic-rollback-receipt-", payload)
    payload["digest"] = local_diagnostic_rollback_receipt_digest(payload)
    return LocalDiagnosticRollbackReceipt(**payload)


def build_local_diagnostic_production_audit_receipt(
    receipt: LocalDiagnosticEffectReceipt,
    postcondition_check: LocalDiagnosticPostconditionCheck,
    rollback_plan: LocalDiagnosticRollbackPlan,
    rollback_receipt: LocalDiagnosticRollbackReceipt | None = None,
    *,
    created_at: str | None = None,
) -> LocalDiagnosticProductionAuditReceipt:
    ok = receipt.real_effect_receipt_created and postcondition_check.postcondition_status.startswith("local_diagnostic_postcondition_passed")
    payload = {
        "audit_id": "",
        "effect_receipt_id": receipt.receipt_id,
        "postcondition_check_id": postcondition_check.check_id,
        "rollback_plan_id": rollback_plan.plan_id,
        "rollback_receipt_id": rollback_receipt.receipt_id if rollback_receipt else None,
        "audit_status": "local_diagnostic_production_audit_recorded" if ok else "local_diagnostic_production_audit_recorded_with_warnings",
        "evidence_summary": ("effect receipt recorded", "postcondition readback limited to artifact path", "rollback plan recorded", "rollback execution deferred"),
        "warning_codes": tuple(receipt.warning_codes + postcondition_check.warning_codes + rollback_plan.warning_codes + (rollback_receipt.warning_codes if rollback_receipt else ())),
        "risk_codes": receipt.risk_codes,
        "created_at": created_at or receipt.created_at,
        "digest": "",
    }
    payload["audit_id"] = _digest_id("local-diagnostic-production-audit-", payload)
    payload["digest"] = local_diagnostic_production_audit_receipt_digest(payload)
    return LocalDiagnosticProductionAuditReceipt(**payload)


def _validate_forbidden_false(payload: Mapping[str, Any]) -> list[str]:
    return [f"forbidden_{flag}" for flag in FORBIDDEN_PERFORMED_FLAGS if payload.get(flag)]


def validate_local_diagnostic_effect_result(result: LocalDiagnosticEffectResult | Mapping[str, Any]) -> LocalDiagnosticEffectValidationResult:
    p = _source_payload(result)
    findings = _validate_forbidden_false(p)
    if p.get("effect_status") not in EFFECT_STATUSES:
        findings.append("unknown_effect_status")
    if p.get("real_effect_performed") != (p.get("effect_status") == "local_diagnostic_effect_performed"):
        findings.append("real_effect_flag_mismatch")
    return LocalDiagnosticEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_local_diagnostic_effect_receipt(receipt: LocalDiagnosticEffectReceipt | Mapping[str, Any]) -> LocalDiagnosticEffectValidationResult:
    p = _source_payload(receipt)
    findings = _validate_forbidden_false(p)
    if not p.get("diagnostic_only"):
        findings.append("receipt_not_diagnostic_only")
    return LocalDiagnosticEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_local_diagnostic_postcondition_check(check: LocalDiagnosticPostconditionCheck | Mapping[str, Any]) -> LocalDiagnosticEffectValidationResult:
    p = _source_payload(check)
    findings = []
    if p.get("postcondition_status") not in POSTCONDITION_STATUSES:
        findings.append("unknown_postcondition_status")
    for flag in ("host_mutation_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed"):
        if p.get(flag):
            findings.append(f"forbidden_{flag}")
    return LocalDiagnosticEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_local_diagnostic_rollback_plan(plan: LocalDiagnosticRollbackPlan | Mapping[str, Any]) -> LocalDiagnosticEffectValidationResult:
    p = _source_payload(plan)
    findings = []
    if p.get("rollback_status") not in ROLLBACK_STATUSES:
        findings.append("unknown_rollback_status")
    if not p.get("rollback_plan_only") or p.get("real_rollback_performed") or p.get("host_mutation_performed"):
        findings.append("rollback_plan_claims_execution")
    return LocalDiagnosticEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_local_diagnostic_rollback_receipt(receipt: LocalDiagnosticRollbackReceipt | Mapping[str, Any]) -> LocalDiagnosticEffectValidationResult:
    p = _source_payload(receipt)
    findings = []
    if p.get("rollback_status") not in ROLLBACK_STATUSES:
        findings.append("unknown_rollback_status")
    if p.get("real_rollback_performed") or p.get("host_mutation_performed") or p.get("file_delete_performed"):
        findings.append("rollback_receipt_claims_deletion")
    return LocalDiagnosticEffectValidationResult(ok=not findings, findings=tuple(findings))


def validate_local_diagnostic_production_audit_receipt(receipt: LocalDiagnosticProductionAuditReceipt | Mapping[str, Any]) -> LocalDiagnosticEffectValidationResult:
    p = _source_payload(receipt)
    findings = []
    if p.get("audit_status") not in AUDIT_STATUSES:
        findings.append("unknown_audit_status")
    for flag in ("host_mutation_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed"):
        if p.get(flag):
            findings.append(f"forbidden_{flag}")
    if not p.get("audit_for_local_diagnostic_effect_only"):
        findings.append("audit_scope_not_local_diagnostic_only")
    return LocalDiagnosticEffectValidationResult(ok=not findings, findings=tuple(findings))


def summarize_local_diagnostic_effect_request(record: LocalDiagnosticEffectRequest | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("request_id", "source_real_effect_admission_bundle_id", "effect_domain", "output_dir", "artifact_name", "force_overwrite", "request_status", "local_effect_requested", "diagnostic_only", "network_performed", "provider_invocation_performed", "prompt_assembly_performed", "subprocess_performed", "shell_performed", "digest")}


def summarize_local_diagnostic_effect_result(record: LocalDiagnosticEffectResult | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("result_id", "request_id", "output_path", "artifact_digest", "byte_count", "effect_status", "real_effect_performed", "local_file_write_performed", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed", "digest")}


def summarize_local_diagnostic_effect_receipt(record: LocalDiagnosticEffectReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("receipt_id", "request_id", "result_id", "effect_domain", "output_path", "artifact_digest", "byte_count", "effect_status", "real_effect_receipt_created", "real_effect_performed", "local_file_write_performed", "host_mutation_performed", "diagnostic_only", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed", "digest")}


def summarize_local_diagnostic_postcondition_check(record: LocalDiagnosticPostconditionCheck | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("check_id", "receipt_id", "output_path", "expected_artifact_digest", "observed_artifact_digest", "expected_byte_count", "observed_byte_count", "postcondition_status", "real_postcondition_check_performed", "host_mutation_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed", "digest")}


def summarize_local_diagnostic_rollback_plan(record: LocalDiagnosticRollbackPlan | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("plan_id", "receipt_id", "output_path", "rollback_strategy_labels", "rollback_status", "rollback_plan_only", "real_rollback_performed", "host_mutation_performed", "digest")}


def summarize_local_diagnostic_rollback_receipt(record: LocalDiagnosticRollbackReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("receipt_id", "plan_id", "output_path", "rollback_status", "rollback_reason_codes", "rollback_receipt_only", "real_rollback_performed", "host_mutation_performed", "file_delete_performed", "digest")}


def summarize_local_diagnostic_production_audit_receipt(record: LocalDiagnosticProductionAuditReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("audit_id", "effect_receipt_id", "postcondition_check_id", "rollback_plan_id", "rollback_receipt_id", "audit_status", "production_audit_receipt_created", "audit_for_local_diagnostic_effect_only", "network_performed", "provider_invocation_performed", "prompt_assembly_performed", "host_mutation_performed", "digest")}


def summarize_local_diagnostic_effect_wing(records: LocalDiagnosticEffectWingRecords) -> dict[str, Any]:
    return {
        "request": summarize_local_diagnostic_effect_request(records.request),
        "result": summarize_local_diagnostic_effect_result(records.result),
        "receipt": summarize_local_diagnostic_effect_receipt(records.receipt),
        "postcondition_check": summarize_local_diagnostic_postcondition_check(records.postcondition_check),
        "rollback_plan": summarize_local_diagnostic_rollback_plan(records.rollback_plan),
        "rollback_receipt": summarize_local_diagnostic_rollback_receipt(records.rollback_receipt),
        "production_audit_receipt": summarize_local_diagnostic_production_audit_receipt(records.production_audit_receipt),
    }


def run_local_diagnostic_effect_wing(
    *,
    output_dir: str | Path,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    effect_domain: str = "diagnostics_local_file_effect",
    artifact_payload_summary: str = "deterministic local diagnostic metadata artifact",
    artifact_payload: Mapping[str, Any] | None = None,
    force_overwrite: bool = False,
    dry_run: bool = False,
    source_real_effect_admission_bundle: Any | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> LocalDiagnosticEffectWingRecords:
    request = build_local_diagnostic_effect_request(
        output_dir=output_dir,
        artifact_name=artifact_name,
        effect_domain=effect_domain,
        artifact_payload_summary=artifact_payload_summary,
        force_overwrite=force_overwrite,
        source_real_effect_admission_bundle=source_real_effect_admission_bundle,
        created_at=created_at,
    )
    result = perform_local_diagnostic_effect(request, artifact_payload=artifact_payload, dry_run=dry_run, created_at=created_at)
    receipt = build_local_diagnostic_effect_receipt(request, result, created_at=created_at)
    postcondition = perform_local_diagnostic_postcondition_check(receipt, created_at=created_at)
    rollback_plan = build_local_diagnostic_rollback_plan(receipt, created_at=created_at)
    rollback_receipt = build_local_diagnostic_rollback_receipt(rollback_plan, created_at=created_at)
    audit = build_local_diagnostic_production_audit_receipt(receipt, postcondition, rollback_plan, rollback_receipt, created_at=created_at)
    return LocalDiagnosticEffectWingRecords(request, result, receipt, postcondition, rollback_plan, rollback_receipt, audit)
