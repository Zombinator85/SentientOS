"""Metadata-only host steward / delegated runner authority boundary.

This module models authority records only. It does not implement runners, load
backends, execute processes, call providers, assemble prompts, use network
transport, inspect privileged devices, or mutate host state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence, TypeVar, cast

HOST_STEWARD_PROFILE_STATUSES = frozenset({
    "host_steward_authority_profile_ready",
    "host_steward_authority_profile_ready_with_warnings",
    "host_steward_authority_profile_blocked",
    "host_steward_authority_profile_incomplete",
    "host_steward_authority_profile_contradicted",
})
DELEGATED_RUNNER_BOUNDARY_STATUSES = frozenset({
    "delegated_runner_boundary_ready",
    "delegated_runner_boundary_ready_with_warnings",
    "delegated_runner_boundary_blocked",
    "delegated_runner_boundary_incomplete",
    "delegated_runner_boundary_contradicted",
})
CONTAINMENT_STATUSES = frozenset({
    "execution_containment_declared",
    "execution_containment_declared_with_warnings",
    "execution_containment_blocked",
    "execution_containment_incomplete",
    "execution_containment_contradicted",
})
BACKEND_AUTHORITY_STATUSES = frozenset({
    "backend_adapter_authority_declared",
    "backend_adapter_authority_declared_with_warnings",
    "backend_adapter_authority_blocked",
    "backend_adapter_authority_incomplete",
    "backend_adapter_authority_contradicted",
})
RUNNER_GRANT_SCAFFOLD_STATUSES = frozenset({
    "runner_capability_grant_scaffold_ready",
    "runner_capability_grant_scaffold_ready_with_conditions",
    "runner_capability_grant_scaffold_blocked",
    "runner_capability_grant_scaffold_incomplete",
    "runner_capability_grant_scaffold_contradicted",
})
BOUNDARY_ASSESSMENT_STATUSES = frozenset({
    "runner_boundary_assessment_passed",
    "runner_boundary_assessment_passed_with_warnings",
    "runner_boundary_assessment_blocked",
    "runner_boundary_assessment_incomplete",
    "runner_boundary_assessment_contradicted",
})
VIOLATION_RECEIPT_STATUSES = frozenset({
    "runner_boundary_violation_recorded",
    "runner_boundary_violation_recorded_with_warnings",
    "runner_boundary_violation_blocked",
    "runner_boundary_violation_incomplete",
    "runner_boundary_violation_contradicted",
})

AUTHORITY_MODES = frozenset({
    "full_local_host_steward_mode",
    "bounded_local_effect_mode",
    "dry_run_only_mode",
    "metadata_only_mode",
    "delegated_runner_mode",
    "offline_runner_mode",
    "no_network_runner_mode",
    "no_host_mutation_runner_mode",
    "diagnostic_file_effect_mode",
})
RUNNER_TRUST_CLASSES = frozenset({
    "trusted_core_runtime",
    "bounded_builtin_runner",
    "generated_code_runner",
    "plugin_runner",
    "backend_adapter_runner",
    "federation_import_runner",
    "external_tool_runner",
    "unknown_runner",
})
CONTAINMENT_CLASSES = frozenset({
    "metadata_only_containment",
    "dry_run_simulation_containment",
    "local_file_effect_containment",
    "exact_artifact_rollback_containment",
    "offline_no_network_containment",
    "bounded_workspace_containment",
    "future_os_sandbox_containment",
    "future_privileged_backend_containment",
})
AUTHORITY_LABELS = frozenset({
    "host_steward_may_hold_broad_local_authority",
    "delegated_runners_do_not_inherit_ambient_authority",
    "runner_authority_must_be_scoped",
    "runner_authority_must_be_revocable",
    "runner_authority_must_be_auditable",
    "runner_authority_must_be_time_bounded",
    "runner_must_have_explicit_capability_grant",
    "runner_must_have_effect_receipt",
    "runner_must_have_postcondition_check",
    "runner_must_have_rollback_plan",
    "runner_must_have_transaction_ledger",
    "runner_must_not_use_network_by_default",
    "runner_must_not_spawn_shell_by_default",
    "runner_must_not_use_subprocess_by_default",
    "runner_must_not_access_hardware_by_default",
    "runner_must_not_mutate_services_by_default",
    "runner_must_not_perform_cleanup_by_default",
    "runner_must_not_use_provider_by_default",
    "runner_must_not_assemble_prompt_by_default",
})
BLOCKED_ACTION_LABELS = frozenset({
    "ambient_authority_inheritance",
    "unscoped_runner_authority",
    "unrevocable_runner_authority",
    "unaudited_runner_authority",
    "runner_network_egress",
    "runner_provider_invocation",
    "runner_prompt_assembly",
    "runner_subprocess_execution",
    "runner_shell_execution",
    "runner_os_backend_invocation",
    "runner_hardware_control",
    "runner_service_control",
    "runner_power_control",
    "runner_cleanup",
    "runner_recursive_delete",
    "runner_unrelated_file_delete",
    "runner_fan_pwm_write",
    "runner_thermal_actuation",
    "federation_authority_import",
    "remote_execution",
    "control_plane_admission_execution",
})
UNTRUSTED_RUNNER_CLASSES = frozenset({"generated_code_runner", "plugin_runner", "federation_import_runner", "external_tool_runner", "unknown_runner"})
REQUIRED_RUNNER_DENIALS = tuple(sorted(label for label in AUTHORITY_LABELS if label.startswith("runner_must_not") or label == "delegated_runners_do_not_inherit_ambient_authority"))
FORBIDDEN_TRUE_FLAGS = (
    "grants_live_runner_authority",
    "executes_runner",
    "runner_implemented",
    "runner_executed",
    "host_mutation_performed",
    "containment_enforced_live",
    "backend_loaded",
    "backend_invoked",
    "live_runner_grant_issued",
    "authorizes_runner_execution",
    "network_performed",
    "network_egress_performed",
    "provider_invocation_performed",
    "prompt_assembly_performed",
    "subprocess_execution_performed",
    "shell_execution_performed",
    "hardware_control_performed",
    "service_control_performed",
    "power_control_performed",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "cleanup_performed",
    "control_plane_admission_execution_performed",
)


def _tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _digest_payload(payload: Mapping[str, Any]) -> str:
    clean = {key: value for key, value in payload.items() if key != "digest"}
    rendered = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()


_DigestRecord = TypeVar("_DigestRecord")


def _with_digest(record: _DigestRecord) -> _DigestRecord:
    return cast(_DigestRecord, replace(cast(Any, record), digest=_digest_payload(asdict(cast(Any, record)))))


@dataclass(frozen=True)
class HostStewardBoundaryValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HostStewardAuthorityPolicy:
    policy_id: str
    authority_modes: tuple[str, ...]
    runner_trust_classes: tuple[str, ...]
    containment_classes: tuple[str, ...]
    authority_labels: tuple[str, ...]
    blocked_action_labels: tuple[str, ...]
    metadata_only: bool = True
    policy_only: bool = True
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostStewardAuthorityProfile:
    profile_id: str
    authority_mode: str
    steward_identity_label: str
    operator_delegation_labels: tuple[str, ...]
    allowed_top_level_authority_labels: tuple[str, ...]
    prohibited_delegation_labels: tuple[str, ...]
    required_audit_labels: tuple[str, ...]
    required_revocation_labels: tuple[str, ...]
    required_boundary_labels: tuple[str, ...]
    profile_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str = ""
    metadata_only: bool = True
    authority_profile_only: bool = True
    grants_live_runner_authority: bool = False
    executes_runner: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DelegatedRunnerBoundaryProfile:
    boundary_id: str
    runner_trust_class: str
    containment_class: str
    allowed_authority_labels: tuple[str, ...]
    denied_authority_labels: tuple[str, ...]
    required_grant_labels: tuple[str, ...]
    required_receipt_labels: tuple[str, ...]
    required_revocation_labels: tuple[str, ...]
    required_audit_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    boundary_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str = ""
    metadata_only: bool = True
    boundary_profile_only: bool = True
    runner_implemented: bool = False
    runner_executed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionContainmentProfile:
    containment_id: str
    containment_class: str
    writable_scope_labels: tuple[str, ...]
    readable_scope_labels: tuple[str, ...]
    network_posture_label: str
    process_posture_label: str
    hardware_posture_label: str
    service_posture_label: str
    provider_posture_label: str
    prompt_posture_label: str
    blocked_actions: tuple[str, ...]
    containment_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str = ""
    metadata_only: bool = True
    containment_profile_only: bool = True
    containment_enforced_live: bool = False
    runner_executed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BackendAdapterAuthorityDeclaration:
    declaration_id: str
    adapter_label: str
    runner_trust_class: str
    backend_domain_labels: tuple[str, ...]
    required_capability_grant_labels: tuple[str, ...]
    denied_authority_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    declaration_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str = ""
    metadata_only: bool = True
    declaration_only: bool = True
    backend_loaded: bool = False
    backend_invoked: bool = False
    runner_executed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunnerCapabilityGrantScaffold:
    scaffold_id: str
    boundary_id: str
    containment_id: str
    backend_authority_declaration_id: str | None
    runner_trust_class: str
    containment_class: str
    grant_scope_labels: tuple[str, ...]
    grant_time_bound_labels: tuple[str, ...]
    grant_revocation_labels: tuple[str, ...]
    required_effect_receipt_labels: tuple[str, ...]
    required_postcondition_labels: tuple[str, ...]
    required_rollback_labels: tuple[str, ...]
    required_transaction_ledger_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    scaffold_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str = ""
    metadata_only: bool = True
    grant_scaffold_only: bool = True
    live_runner_grant_issued: bool = False
    runner_executed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunnerBoundaryAssessment:
    assessment_id: str
    profile_id: str
    boundary_id: str
    containment_id: str
    grant_scaffold_id: str | None
    assessment_status: str
    satisfied_boundary_labels: tuple[str, ...]
    missing_boundary_labels: tuple[str, ...]
    violation_codes: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str = ""
    metadata_only: bool = True
    assessment_only: bool = True
    authorizes_runner_execution: bool = False
    live_runner_grant_issued: bool = False
    runner_executed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunnerBoundaryViolationReceipt:
    receipt_id: str
    assessment_id: str | None
    runner_trust_class: str
    containment_class: str
    violation_status: str
    violation_codes: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str = ""
    metadata_only: bool = True
    violation_receipt_only: bool = True
    authorizes_runner_execution: bool = False
    live_runner_grant_issued: bool = False
    runner_executed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostStewardBoundaryWing:
    policy: HostStewardAuthorityPolicy
    host_steward_profile: HostStewardAuthorityProfile
    delegated_runner_boundaries: tuple[DelegatedRunnerBoundaryProfile, ...]
    containment_profiles: tuple[ExecutionContainmentProfile, ...]
    backend_declarations: tuple[BackendAdapterAuthorityDeclaration, ...]
    grant_scaffolds: tuple[RunnerCapabilityGrantScaffold, ...]
    boundary_assessments: tuple[RunnerBoundaryAssessment, ...]
    violation_receipts: tuple[RunnerBoundaryViolationReceipt, ...]
    metadata_only: bool = True
    wing_only: bool = True
    runner_executed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_default_host_steward_authority_policy() -> HostStewardAuthorityPolicy:
    return _with_digest(HostStewardAuthorityPolicy(
        policy_id="host-steward-boundary-policy-v1",
        authority_modes=tuple(sorted(AUTHORITY_MODES)),
        runner_trust_classes=tuple(sorted(RUNNER_TRUST_CLASSES)),
        containment_classes=tuple(sorted(CONTAINMENT_CLASSES)),
        authority_labels=tuple(sorted(AUTHORITY_LABELS)),
        blocked_action_labels=tuple(sorted(BLOCKED_ACTION_LABELS)),
    ))


def build_host_steward_authority_profile(*, profile_id: str = "default-host-steward-authority-profile", steward_identity_label: str = "sentientos_local_host_steward", created_at: str = "1970-01-01T00:00:00+00:00", authority_mode: str = "full_local_host_steward_mode") -> HostStewardAuthorityProfile:
    return _with_digest(HostStewardAuthorityProfile(
        profile_id=profile_id,
        authority_mode=authority_mode,
        steward_identity_label=steward_identity_label,
        operator_delegation_labels=("explicit_operator_delegation_required", "local_operator_authority_preserved"),
        allowed_top_level_authority_labels=("host_steward_may_hold_broad_local_authority",),
        prohibited_delegation_labels=("delegated_runners_do_not_inherit_ambient_authority", "ambient_authority_inheritance"),
        required_audit_labels=("runner_authority_must_be_auditable", "runner_must_have_effect_receipt", "runner_must_have_transaction_ledger"),
        required_revocation_labels=("runner_authority_must_be_revocable", "runner_authority_must_be_time_bounded"),
        required_boundary_labels=("runner_authority_must_be_scoped", "runner_must_have_explicit_capability_grant"),
        profile_status="host_steward_authority_profile_ready",
        warning_codes=(),
        risk_codes=("broad_authority_must_remain_top_level_operator_delegated",),
        created_at=created_at,
    ))


def _default_containment_for_runner(runner_trust_class: str, requested: str | None) -> str:
    if requested:
        return requested
    if runner_trust_class in UNTRUSTED_RUNNER_CLASSES:
        return "metadata_only_containment"
    if runner_trust_class == "bounded_builtin_runner":
        return "dry_run_simulation_containment"
    return "metadata_only_containment"


def build_delegated_runner_boundary_profile(*, boundary_id: str, runner_trust_class: str = "unknown_runner", containment_class: str | None = None, allowed_authority_labels: Sequence[str] = (), created_at: str = "1970-01-01T00:00:00+00:00") -> DelegatedRunnerBoundaryProfile:
    final_containment = _default_containment_for_runner(runner_trust_class, containment_class)
    allowed = _tuple(allowed_authority_labels)
    if final_containment in {"local_file_effect_containment", "exact_artifact_rollback_containment"} and runner_trust_class != "bounded_builtin_runner":
        allowed = ()
        status = "delegated_runner_boundary_blocked"
        risks: tuple[str, ...] = ("local_file_or_rollback_containment_requires_bounded_builtin_runner",)
    else:
        status = "delegated_runner_boundary_ready"
        risks = ()
    return _with_digest(DelegatedRunnerBoundaryProfile(
        boundary_id=boundary_id,
        runner_trust_class=runner_trust_class,
        containment_class=final_containment,
        allowed_authority_labels=allowed,
        denied_authority_labels=REQUIRED_RUNNER_DENIALS,
        required_grant_labels=("runner_must_have_explicit_capability_grant", "runner_authority_must_be_scoped", "runner_authority_must_be_time_bounded"),
        required_receipt_labels=("runner_must_have_effect_receipt", "runner_must_have_postcondition_check", "runner_must_have_transaction_ledger"),
        required_revocation_labels=("runner_authority_must_be_revocable",),
        required_audit_labels=("runner_authority_must_be_auditable",),
        blocked_actions=tuple(sorted(BLOCKED_ACTION_LABELS)),
        boundary_status=status,
        warning_codes=(),
        risk_codes=risks,
        created_at=created_at,
    ))


def build_execution_containment_profile(*, containment_id: str, containment_class: str = "metadata_only_containment", writable_scope_labels: Sequence[str] = (), readable_scope_labels: Sequence[str] = (), created_at: str = "1970-01-01T00:00:00+00:00") -> ExecutionContainmentProfile:
    return _with_digest(ExecutionContainmentProfile(
        containment_id=containment_id,
        containment_class=containment_class,
        writable_scope_labels=_tuple(writable_scope_labels),
        readable_scope_labels=_tuple(readable_scope_labels),
        network_posture_label="no_network_by_default",
        process_posture_label="no_process_spawn_by_default",
        hardware_posture_label="no_hardware_access_by_default",
        service_posture_label="no_service_mutation_by_default",
        provider_posture_label="no_provider_invocation_by_default",
        prompt_posture_label="no_prompt_assembly_by_default",
        blocked_actions=tuple(sorted(BLOCKED_ACTION_LABELS)),
        containment_status="execution_containment_declared",
        warning_codes=(),
        risk_codes=("containment_profile_is_not_live_sandbox_execution",),
        created_at=created_at,
    ))


def build_backend_adapter_authority_declaration(*, declaration_id: str, adapter_label: str, runner_trust_class: str = "backend_adapter_runner", backend_domain_labels: Sequence[str] = (), created_at: str = "1970-01-01T00:00:00+00:00") -> BackendAdapterAuthorityDeclaration:
    return _with_digest(BackendAdapterAuthorityDeclaration(
        declaration_id=declaration_id,
        adapter_label=adapter_label,
        runner_trust_class=runner_trust_class,
        backend_domain_labels=_tuple(backend_domain_labels),
        required_capability_grant_labels=("runner_must_have_explicit_capability_grant", "runner_authority_must_be_scoped"),
        denied_authority_labels=REQUIRED_RUNNER_DENIALS,
        blocked_actions=tuple(sorted(BLOCKED_ACTION_LABELS)),
        declaration_status="backend_adapter_authority_declared",
        warning_codes=(),
        risk_codes=("backend_authority_declaration_is_not_backend_invocation",),
        created_at=created_at,
    ))


def build_runner_capability_grant_scaffold(*, scaffold_id: str, boundary_id: str, containment_id: str, runner_trust_class: str = "unknown_runner", containment_class: str = "metadata_only_containment", backend_authority_declaration_id: str | None = None, grant_scope_labels: Sequence[str] = (), created_at: str = "1970-01-01T00:00:00+00:00") -> RunnerCapabilityGrantScaffold:
    return _with_digest(RunnerCapabilityGrantScaffold(
        scaffold_id=scaffold_id,
        boundary_id=boundary_id,
        containment_id=containment_id,
        backend_authority_declaration_id=backend_authority_declaration_id,
        runner_trust_class=runner_trust_class,
        containment_class=containment_class,
        grant_scope_labels=_tuple(grant_scope_labels) or ("metadata_scope_only",),
        grant_time_bound_labels=("grant_must_have_not_before", "grant_must_have_not_after"),
        grant_revocation_labels=("grant_must_be_revocable",),
        required_effect_receipt_labels=("runner_must_have_effect_receipt",),
        required_postcondition_labels=("runner_must_have_postcondition_check",),
        required_rollback_labels=("runner_must_have_rollback_plan",),
        required_transaction_ledger_labels=("runner_must_have_transaction_ledger",),
        blocked_actions=tuple(sorted(BLOCKED_ACTION_LABELS)),
        scaffold_status="runner_capability_grant_scaffold_ready",
        warning_codes=(),
        risk_codes=("grant_scaffold_is_not_live_runner_grant",),
        created_at=created_at,
    ))


def assess_runner_boundary(profile: HostStewardAuthorityProfile, boundary: DelegatedRunnerBoundaryProfile, containment: ExecutionContainmentProfile, grant_scaffold: RunnerCapabilityGrantScaffold | None = None, *, assessment_id: str = "runner-boundary-assessment", created_at: str = "1970-01-01T00:00:00+00:00") -> RunnerBoundaryAssessment:
    required = set(boundary.required_grant_labels + boundary.required_receipt_labels + boundary.required_revocation_labels + boundary.required_audit_labels + ("delegated_runners_do_not_inherit_ambient_authority",))
    present = set(boundary.denied_authority_labels + boundary.required_grant_labels + boundary.required_receipt_labels + boundary.required_revocation_labels + boundary.required_audit_labels + profile.prohibited_delegation_labels)
    missing = tuple(sorted(required - present))
    violations = () if not missing and "ambient_authority_inheritance" in boundary.blocked_actions else ("ambient_authority_boundary_missing",)
    status = "runner_boundary_assessment_passed" if not violations and not missing else "runner_boundary_assessment_blocked"
    return _with_digest(RunnerBoundaryAssessment(
        assessment_id=assessment_id,
        profile_id=profile.profile_id,
        boundary_id=boundary.boundary_id,
        containment_id=containment.containment_id,
        grant_scaffold_id=grant_scaffold.scaffold_id if grant_scaffold else None,
        assessment_status=status,
        satisfied_boundary_labels=tuple(sorted(required & present)),
        missing_boundary_labels=missing,
        violation_codes=violations,
        blocked_actions=tuple(sorted(set(boundary.blocked_actions + containment.blocked_actions))),
        warning_codes=(),
        risk_codes=("assessment_does_not_authorize_runner_execution",),
        created_at=created_at,
    ))


def build_runner_boundary_violation_receipt(*, receipt_id: str, runner_trust_class: str = "unknown_runner", containment_class: str = "metadata_only_containment", assessment_id: str | None = None, violation_codes: Sequence[str] = ("ambient_authority_inheritance_attempt",), created_at: str = "1970-01-01T00:00:00+00:00") -> RunnerBoundaryViolationReceipt:
    return _with_digest(RunnerBoundaryViolationReceipt(
        receipt_id=receipt_id,
        assessment_id=assessment_id,
        runner_trust_class=runner_trust_class,
        containment_class=containment_class,
        violation_status="runner_boundary_violation_recorded",
        violation_codes=_tuple(violation_codes),
        blocked_actions=tuple(sorted(BLOCKED_ACTION_LABELS)),
        warning_codes=(),
        risk_codes=("violation_receipt_is_not_execution_permission",),
        created_at=created_at,
    ))


def _validate_common(record: Any, *, status_field: str, allowed_statuses: frozenset[str], required_true_flag: str | None = None, required_blocked_actions: bool = False) -> HostStewardBoundaryValidationResult:
    payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    findings: list[str] = []
    if payload.get(status_field) not in allowed_statuses:
        findings.append(f"unknown_status:{payload.get(status_field)}")
    if payload.get("metadata_only") is not True:
        findings.append("not_metadata_only")
    if required_true_flag and payload.get(required_true_flag) is not True:
        findings.append(f"missing_flag:{required_true_flag}")
    for flag in FORBIDDEN_TRUE_FLAGS:
        if payload.get(flag, False):
            findings.append(f"forbidden_flag:{flag}")
    if required_blocked_actions:
        actions = set(payload.get("blocked_actions", ()) or ())
        if "ambient_authority_inheritance" not in actions:
            findings.append("missing_blocked_action:ambient_authority_inheritance")
        dangerous = BLOCKED_ACTION_LABELS - actions
        if dangerous:
            findings.append("missing_blocked_actions:" + ",".join(sorted(dangerous)))
    expected_digest = _digest_payload(payload)
    if payload.get("digest") != expected_digest:
        findings.append("digest_mismatch")
    return HostStewardBoundaryValidationResult(not findings, tuple(findings))


def validate_host_steward_authority_profile(profile: HostStewardAuthorityProfile | Mapping[str, Any]) -> HostStewardBoundaryValidationResult:
    result = _validate_common(profile, status_field="profile_status", allowed_statuses=HOST_STEWARD_PROFILE_STATUSES, required_true_flag="authority_profile_only")
    payload = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile)
    findings = list(result.findings)
    if "host_steward_may_hold_broad_local_authority" not in payload.get("allowed_top_level_authority_labels", ()): findings.append("missing_broad_host_steward_label")
    if "delegated_runners_do_not_inherit_ambient_authority" not in payload.get("prohibited_delegation_labels", ()): findings.append("missing_runner_ambient_denial")
    return HostStewardBoundaryValidationResult(not findings, tuple(findings))


def validate_delegated_runner_boundary_profile(boundary: DelegatedRunnerBoundaryProfile | Mapping[str, Any]) -> HostStewardBoundaryValidationResult:
    result = _validate_common(boundary, status_field="boundary_status", allowed_statuses=DELEGATED_RUNNER_BOUNDARY_STATUSES, required_true_flag="boundary_profile_only", required_blocked_actions=True)
    payload = boundary.to_dict() if hasattr(boundary, "to_dict") else dict(boundary)
    findings = list(result.findings)
    denied = set(payload.get("denied_authority_labels", ()) or ())
    if "delegated_runners_do_not_inherit_ambient_authority" not in denied: findings.append("missing_denial:delegated_runners_do_not_inherit_ambient_authority")
    if payload.get("runner_trust_class") in UNTRUSTED_RUNNER_CLASSES and payload.get("containment_class") not in {"metadata_only_containment", "dry_run_simulation_containment", "offline_no_network_containment"}:
        findings.append("untrusted_runner_has_mutating_containment")
    return HostStewardBoundaryValidationResult(not findings, tuple(findings))


def validate_execution_containment_profile(containment: ExecutionContainmentProfile | Mapping[str, Any]) -> HostStewardBoundaryValidationResult:
    return _validate_common(containment, status_field="containment_status", allowed_statuses=CONTAINMENT_STATUSES, required_true_flag="containment_profile_only", required_blocked_actions=True)


def validate_backend_adapter_authority_declaration(declaration: BackendAdapterAuthorityDeclaration | Mapping[str, Any]) -> HostStewardBoundaryValidationResult:
    return _validate_common(declaration, status_field="declaration_status", allowed_statuses=BACKEND_AUTHORITY_STATUSES, required_true_flag="declaration_only", required_blocked_actions=True)


def validate_runner_capability_grant_scaffold(scaffold: RunnerCapabilityGrantScaffold | Mapping[str, Any]) -> HostStewardBoundaryValidationResult:
    return _validate_common(scaffold, status_field="scaffold_status", allowed_statuses=RUNNER_GRANT_SCAFFOLD_STATUSES, required_true_flag="grant_scaffold_only", required_blocked_actions=True)


def validate_runner_boundary_assessment(assessment: RunnerBoundaryAssessment | Mapping[str, Any]) -> HostStewardBoundaryValidationResult:
    return _validate_common(assessment, status_field="assessment_status", allowed_statuses=BOUNDARY_ASSESSMENT_STATUSES, required_true_flag="assessment_only", required_blocked_actions=True)


def validate_runner_boundary_violation_receipt(receipt: RunnerBoundaryViolationReceipt | Mapping[str, Any]) -> HostStewardBoundaryValidationResult:
    return _validate_common(receipt, status_field="violation_status", allowed_statuses=VIOLATION_RECEIPT_STATUSES, required_true_flag="violation_receipt_only", required_blocked_actions=True)


def host_steward_boundary_digest(record: Any) -> str:
    payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    return _digest_payload(payload)


def _summary(record: Any, id_field: str, status_field: str) -> dict[str, Any]:
    payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    return {
        id_field: payload.get(id_field),
        "status": payload.get(status_field),
        "metadata_only": payload.get("metadata_only"),
        "runner_executed": payload.get("runner_executed", payload.get("executes_runner", False)),
        "live_runner_grant_issued": payload.get("live_runner_grant_issued", payload.get("grants_live_runner_authority", False)),
        "host_mutation_performed": payload.get("host_mutation_performed", False),
        "blocked_actions": tuple(payload.get("blocked_actions", ()) or ()),
        "digest": payload.get("digest"),
    }


def summarize_host_steward_authority_policy(policy: HostStewardAuthorityPolicy) -> dict[str, Any]: return {"policy_id": policy.policy_id, "metadata_only": policy.metadata_only, "policy_only": policy.policy_only, "blocked_action_count": len(policy.blocked_action_labels), "digest": policy.digest}
def summarize_host_steward_authority_profile(profile: HostStewardAuthorityProfile) -> dict[str, Any]: return _summary(profile, "profile_id", "profile_status") | {"authority_mode": profile.authority_mode, "allowed_top_level_authority_labels": profile.allowed_top_level_authority_labels}
def summarize_delegated_runner_boundary_profile(boundary: DelegatedRunnerBoundaryProfile) -> dict[str, Any]: return _summary(boundary, "boundary_id", "boundary_status") | {"runner_trust_class": boundary.runner_trust_class, "containment_class": boundary.containment_class, "denied_authority_labels": boundary.denied_authority_labels}
def summarize_execution_containment_profile(containment: ExecutionContainmentProfile) -> dict[str, Any]: return _summary(containment, "containment_id", "containment_status") | {"containment_class": containment.containment_class, "containment_enforced_live": containment.containment_enforced_live}
def summarize_backend_adapter_authority_declaration(declaration: BackendAdapterAuthorityDeclaration) -> dict[str, Any]: return _summary(declaration, "declaration_id", "declaration_status") | {"adapter_label": declaration.adapter_label, "backend_loaded": declaration.backend_loaded, "backend_invoked": declaration.backend_invoked}
def summarize_runner_capability_grant_scaffold(scaffold: RunnerCapabilityGrantScaffold) -> dict[str, Any]: return _summary(scaffold, "scaffold_id", "scaffold_status") | {"grant_scaffold_only": scaffold.grant_scaffold_only}
def summarize_runner_boundary_assessment(assessment: RunnerBoundaryAssessment) -> dict[str, Any]: return _summary(assessment, "assessment_id", "assessment_status") | {"authorizes_runner_execution": assessment.authorizes_runner_execution, "missing_boundary_labels": assessment.missing_boundary_labels}
def summarize_runner_boundary_violation_receipt(receipt: RunnerBoundaryViolationReceipt) -> dict[str, Any]: return _summary(receipt, "receipt_id", "violation_status") | {"violation_codes": receipt.violation_codes, "authorizes_runner_execution": receipt.authorizes_runner_execution}


def build_host_steward_boundary_wing(*, created_at: str = "1970-01-01T00:00:00+00:00") -> HostStewardBoundaryWing:
    policy = build_default_host_steward_authority_policy()
    profile = build_host_steward_authority_profile(created_at=created_at)
    generated = build_delegated_runner_boundary_profile(boundary_id="generated-plugin-federation-external-runner-boundary", runner_trust_class="generated_code_runner", created_at=created_at)
    plugin = build_delegated_runner_boundary_profile(boundary_id="plugin-runner-boundary", runner_trust_class="plugin_runner", created_at=created_at)
    federation = build_delegated_runner_boundary_profile(boundary_id="federation-import-runner-boundary", runner_trust_class="federation_import_runner", created_at=created_at)
    external = build_delegated_runner_boundary_profile(boundary_id="external-tool-runner-boundary", runner_trust_class="external_tool_runner", created_at=created_at)
    diagnostic = build_delegated_runner_boundary_profile(boundary_id="local-diagnostic-bounded-runner-boundary", runner_trust_class="bounded_builtin_runner", containment_class="local_file_effect_containment", allowed_authority_labels=("diagnostic_file_effect_mode",), created_at=created_at)
    containment = build_execution_containment_profile(containment_id="metadata-only-no-network-no-host-mutation-containment", created_at=created_at)
    diagnostic_containment = build_execution_containment_profile(containment_id="local-diagnostic-file-effect-containment", containment_class="local_file_effect_containment", writable_scope_labels=("caller_supplied_diagnostic_output_directory_only",), readable_scope_labels=("effect_receipt_metadata_only",), created_at=created_at)
    backend = build_backend_adapter_authority_declaration(declaration_id="future-backend-adapter-authority-declaration", adapter_label="future_metadata_only_backend_adapter", backend_domain_labels=("declaration_only_no_backend_load",), created_at=created_at)
    scaffold = build_runner_capability_grant_scaffold(scaffold_id="metadata-only-runner-capability-grant-scaffold", boundary_id=generated.boundary_id, containment_id=containment.containment_id, runner_trust_class=generated.runner_trust_class, containment_class=containment.containment_class, backend_authority_declaration_id=backend.declaration_id, created_at=created_at)
    assessment = assess_runner_boundary(profile, generated, containment, scaffold, assessment_id="metadata-only-runner-boundary-assessment", created_at=created_at)
    violation = build_runner_boundary_violation_receipt(receipt_id="ambient-authority-inheritance-violation-receipt", assessment_id=assessment.assessment_id, runner_trust_class=generated.runner_trust_class, containment_class=containment.containment_class, created_at=created_at)
    return HostStewardBoundaryWing(policy, profile, (generated, plugin, federation, external, diagnostic), (containment, diagnostic_containment), (backend,), (scaffold,), (assessment,), (violation,))


def summarize_host_steward_boundary_wing(wing: HostStewardBoundaryWing) -> dict[str, Any]:
    return {
        "metadata_only": wing.metadata_only,
        "wing_only": wing.wing_only,
        "runner_executed": wing.runner_executed,
        "host_mutation_performed": wing.host_mutation_performed,
        "host_steward_profile": summarize_host_steward_authority_profile(wing.host_steward_profile),
        "delegated_runner_boundaries": [summarize_delegated_runner_boundary_profile(item) for item in wing.delegated_runner_boundaries],
        "containment_profiles": [summarize_execution_containment_profile(item) for item in wing.containment_profiles],
        "backend_declarations": [summarize_backend_adapter_authority_declaration(item) for item in wing.backend_declarations],
        "grant_scaffolds": [summarize_runner_capability_grant_scaffold(item) for item in wing.grant_scaffolds],
        "boundary_assessments": [summarize_runner_boundary_assessment(item) for item in wing.boundary_assessments],
        "violation_receipts": [summarize_runner_boundary_violation_receipt(item) for item in wing.violation_receipts],
        "proof_delegated_runners_do_not_inherit_ambient_authority": all("ambient_authority_inheritance" in item.blocked_actions for item in wing.delegated_runner_boundaries),
        "proof_no_runner_executes_by_default": not wing.runner_executed and all(not item.runner_executed for item in wing.delegated_runner_boundaries),
    }
