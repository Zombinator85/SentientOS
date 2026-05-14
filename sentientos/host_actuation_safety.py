"""Metadata-only host actuation safety gate records.

This wing declares the gates that future host actuation would have to satisfy
before live authorization or fulfillment could be reviewed.  It does not grant
live authorization, execute actions, inspect privileged devices, open network
connections, invoke providers, assemble prompts, or mutate host state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence

SAFETY_STATUSES = frozenset({
    "host_actuation_safety_ready",
    "host_actuation_safety_ready_with_conditions",
    "host_actuation_safety_blocked",
    "host_actuation_safety_incomplete",
    "host_actuation_safety_contradicted",
})
GATE_ASSESSMENT_STATUSES = frozenset({
    "host_actuation_gate_satisfied",
    "host_actuation_gate_satisfied_with_conditions",
    "host_actuation_gate_missing",
    "host_actuation_gate_blocked",
    "host_actuation_gate_contradicted",
})
SAFETY_DOMAINS = frozenset({
    "diagnostics_only",
    "operator_review",
    "thermal_safety",
    "cooling_control_future",
    "power_control_future",
    "service_control_future",
    "cleanup_control_future",
    "driver_control_future",
    "package_control_future",
    "file_control_future",
})
SAFETY_GATE_LABELS = frozenset({
    "hardware_allowlist_required", "hardware_allowlist_declared",
    "os_backend_declaration_required", "os_backend_declared",
    "bounds_policy_required", "bounds_policy_declared",
    "cooldown_policy_required", "cooldown_policy_declared",
    "panic_stop_required", "panic_stop_declared",
    "operator_identity_required", "policy_identity_required",
    "explicit_scope_required", "target_scope_declared",
    "time_bounds_required", "expiry_required", "revocation_path_required",
    "control_plane_admission_required", "audit_receipt_required",
    "rollback_plan_required", "rollback_receipt_required", "effect_receipt_required",
    "postcondition_check_required", "runtime_supervisor_observation_required",
    "immutable_trace_required", "dry_run_rehearsal_required",
})
BLOCKED_ACTION_LABELS = frozenset({
    "live_authorization_grant", "host_mutation", "fan_pwm_write",
    "thermal_actuation", "power_profile_mutation", "process_kill",
    "service_restart", "package_install", "driver_install", "file_cleanup",
    "file_delete", "provider_invocation", "network_egress", "prompt_assembly",
    "federation_transport", "remote_execution",
})
FUTURE_DOMAINS = frozenset({
    "cooling_control_future", "power_control_future", "service_control_future",
    "cleanup_control_future", "driver_control_future", "package_control_future",
    "file_control_future",
})
_REQUIRED_GATES: Mapping[str, tuple[str, ...]] = {
    "diagnostics_only": ("operator_identity_required", "policy_identity_required", "audit_receipt_required", "immutable_trace_required"),
    "operator_review": ("operator_identity_required", "policy_identity_required", "explicit_scope_required", "audit_receipt_required", "immutable_trace_required"),
    "thermal_safety": ("os_backend_declaration_required", "bounds_policy_required", "panic_stop_required", "operator_identity_required", "policy_identity_required", "explicit_scope_required", "audit_receipt_required", "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required"),
    "cooling_control_future": ("hardware_allowlist_required", "os_backend_declaration_required", "bounds_policy_required", "cooldown_policy_required", "panic_stop_required", "operator_identity_required", "policy_identity_required", "explicit_scope_required", "target_scope_declared", "time_bounds_required", "expiry_required", "revocation_path_required", "control_plane_admission_required", "audit_receipt_required", "rollback_plan_required", "rollback_receipt_required", "effect_receipt_required", "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required"),
    "power_control_future": ("os_backend_declaration_required", "bounds_policy_required", "cooldown_policy_required", "panic_stop_required", "operator_identity_required", "policy_identity_required", "explicit_scope_required", "target_scope_declared", "time_bounds_required", "expiry_required", "revocation_path_required", "control_plane_admission_required", "audit_receipt_required", "rollback_plan_required", "rollback_receipt_required", "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required"),
    "cleanup_control_future": ("bounds_policy_required", "dry_run_rehearsal_required", "operator_identity_required", "policy_identity_required", "explicit_scope_required", "target_scope_declared", "time_bounds_required", "expiry_required", "revocation_path_required", "audit_receipt_required", "rollback_plan_required", "rollback_receipt_required", "postcondition_check_required", "immutable_trace_required"),
    "service_control_future": ("panic_stop_required", "operator_identity_required", "policy_identity_required", "explicit_scope_required", "target_scope_declared", "time_bounds_required", "expiry_required", "revocation_path_required", "control_plane_admission_required", "audit_receipt_required", "rollback_plan_required", "rollback_receipt_required", "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required"),
    "driver_control_future": ("os_backend_declaration_required", "panic_stop_required", "operator_identity_required", "policy_identity_required", "explicit_scope_required", "target_scope_declared", "time_bounds_required", "expiry_required", "revocation_path_required", "control_plane_admission_required", "audit_receipt_required", "rollback_plan_required", "rollback_receipt_required", "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required"),
    "package_control_future": ("os_backend_declaration_required", "bounds_policy_required", "operator_identity_required", "policy_identity_required", "explicit_scope_required", "target_scope_declared", "time_bounds_required", "expiry_required", "revocation_path_required", "control_plane_admission_required", "audit_receipt_required", "rollback_plan_required", "rollback_receipt_required", "postcondition_check_required", "immutable_trace_required"),
    "file_control_future": ("bounds_policy_required", "dry_run_rehearsal_required", "operator_identity_required", "policy_identity_required", "explicit_scope_required", "target_scope_declared", "time_bounds_required", "expiry_required", "revocation_path_required", "audit_receipt_required", "rollback_plan_required", "rollback_receipt_required", "postcondition_check_required", "immutable_trace_required"),
}
_BLOCKED_BY_DOMAIN: Mapping[str, tuple[str, ...]] = {
    "cooling_control_future": ("live_authorization_grant", "host_mutation", "fan_pwm_write", "thermal_actuation", "network_egress", "provider_invocation", "prompt_assembly"),
    "power_control_future": ("live_authorization_grant", "host_mutation", "power_profile_mutation", "network_egress", "provider_invocation", "prompt_assembly"),
    "cleanup_control_future": ("live_authorization_grant", "host_mutation", "file_cleanup", "file_delete", "network_egress", "provider_invocation", "prompt_assembly"),
    "service_control_future": ("live_authorization_grant", "host_mutation", "service_restart", "process_kill", "network_egress", "provider_invocation", "prompt_assembly"),
    "driver_control_future": ("live_authorization_grant", "host_mutation", "driver_install", "network_egress", "provider_invocation", "prompt_assembly"),
    "package_control_future": ("live_authorization_grant", "host_mutation", "package_install", "network_egress", "provider_invocation", "prompt_assembly"),
    "file_control_future": ("live_authorization_grant", "host_mutation", "file_cleanup", "file_delete", "network_egress", "provider_invocation", "prompt_assembly"),
}
_DECLARED_FOR_REQUIRED = {
    "hardware_allowlist_required": "hardware_allowlist_declared",
    "os_backend_declaration_required": "os_backend_declared",
    "bounds_policy_required": "bounds_policy_declared",
    "cooldown_policy_required": "cooldown_policy_declared",
    "panic_stop_required": "panic_stop_declared",
}

@dataclass(frozen=True)
class HostActuationSafetyPolicy:
    policy_id: str
    required_gates_by_domain: Mapping[str, tuple[str, ...]]
    blocked_actions_by_domain: Mapping[str, tuple[str, ...]]
    metadata_only: bool = True
    safety_gate_only: bool = True
    grants_live_authorization: bool = False
    grants_control_authority: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HardwareAllowlistEntry:
    entry_id: str
    hardware_kind: str
    hardware_label: str
    vendor_label: str | None
    model_label: str | None
    os_family: str
    backend_class: str
    allowed_for_domains: tuple[str, ...]
    denied_for_domains: tuple[str, ...]
    required_bounds_policy_labels: tuple[str, ...]
    required_cooldown_policy_labels: tuple[str, ...]
    required_panic_stop_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    allowlist_only: bool = True
    grants_control_authority: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HardwareAllowlistManifest:
    manifest_id: str
    entries: tuple[HardwareAllowlistEntry, ...]
    allowed_domain_labels: tuple[str, ...]
    denied_domain_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    allowlist_only: bool = True
    grants_control_authority: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class OSBackendDeclaration:
    declaration_id: str
    backend_class: str
    os_family: str
    backend_label: str
    supported_domains: tuple[str, ...]
    unsupported_domains: tuple[str, ...]
    required_privilege_labels: tuple[str, ...]
    required_scope_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    declaration_only: bool = True
    backend_loaded: bool = False
    backend_invoked: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class BoundsPolicy:
    policy_id: str
    domain: str
    target_label: str
    lower_bound_label: str
    upper_bound_label: str
    step_limit_label: str
    rate_limit_label: str
    forbidden_value_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    policy_only: bool = True
    bounds_enforced_live: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class CooldownPolicy:
    policy_id: str
    domain: str
    target_label: str
    minimum_interval_label: str
    maximum_attempts_label: str
    cooldown_reset_label: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    policy_only: bool = True
    cooldown_enforced_live: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class PanicStopContract:
    contract_id: str
    domain: str
    trigger_labels: tuple[str, ...]
    stop_labels: tuple[str, ...]
    operator_override_labels: tuple[str, ...]
    recovery_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    contract_only: bool = True
    panic_stop_executed: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostActionScopeManifest:
    scope_id: str
    domain: str
    target_labels: tuple[str, ...]
    allowed_action_labels: tuple[str, ...]
    forbidden_action_labels: tuple[str, ...]
    path_scope_labels: tuple[str, ...]
    service_scope_labels: tuple[str, ...]
    hardware_scope_labels: tuple[str, ...]
    time_bound_labels: tuple[str, ...]
    expiry_labels: tuple[str, ...]
    revocation_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    scope_only: bool = True
    grants_control_authority: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostActuationGateAssessment:
    assessment_id: str
    source_controlled_authorization_contract_id: str | None
    source_controlled_authorization_contract_digest: str | None
    domain: str
    gate_label: str
    gate_status: str
    evidence_labels: tuple[str, ...]
    missing_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    assessment_only: bool = True
    grants_control_authority: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class SafetyGateSatisfactionManifest:
    manifest_id: str
    source_controlled_authorization_contract_id: str | None
    source_controlled_authorization_contract_digest: str | None
    domain: str
    safety_status: str
    hardware_allowlist_manifest_id: str | None
    os_backend_declaration_id: str | None
    bounds_policy_id: str | None
    cooldown_policy_id: str | None
    panic_stop_contract_id: str | None
    host_action_scope_manifest_id: str | None
    gate_assessment_ids: tuple[str, ...]
    satisfied_gate_labels: tuple[str, ...]
    missing_gate_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    safety_gate_only: bool = True
    grants_live_authorization: bool = False
    grants_control_authority: bool = False
    fulfillment_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False
    fan_pwm_write_performed: bool = False
    thermal_actuation_performed: bool = False
    power_profile_mutation_performed: bool = False
    process_kill_performed: bool = False
    service_restart_performed: bool = False
    package_install_performed: bool = False
    driver_install_performed: bool = False
    file_cleanup_performed: bool = False
    provider_invocation_performed: bool = False
    network_performed: bool = False
    prompt_assembly_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostActuationSafetyValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()

@dataclass(frozen=True)
class HostActuationSafetyBundle:
    hardware_allowlist_manifest: HardwareAllowlistManifest | None
    os_backend_declaration: OSBackendDeclaration | None
    bounds_policy: BoundsPolicy | None
    cooldown_policy: CooldownPolicy | None
    panic_stop_contract: PanicStopContract | None
    host_action_scope_manifest: HostActionScopeManifest | None
    gate_assessments: tuple[HostActuationGateAssessment, ...]
    safety_gate_satisfaction_manifest: SafetyGateSatisfactionManifest
    metadata_only: bool = True
    safety_gate_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)


def _tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))

def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)

def _record_payload(record_or_payload: Any) -> dict[str, Any]:
    payload = record_or_payload.to_dict() if hasattr(record_or_payload, "to_dict") else dict(record_or_payload)
    payload["digest"] = ""
    return payload

def host_actuation_safety_digest(record_or_payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(_record_payload(record_or_payload)).encode("utf-8")).hexdigest()

hardware_allowlist_manifest_digest = host_actuation_safety_digest
os_backend_declaration_digest = host_actuation_safety_digest
bounds_policy_digest = host_actuation_safety_digest
cooldown_policy_digest = host_actuation_safety_digest
panic_stop_contract_digest = host_actuation_safety_digest
host_action_scope_manifest_digest = host_actuation_safety_digest
safety_gate_satisfaction_manifest_digest = host_actuation_safety_digest

def host_actuation_gate_assessment_digest(assessment: HostActuationGateAssessment | Mapping[str, Any]) -> str:
    payload = assessment.to_dict() if isinstance(assessment, HostActuationGateAssessment) else dict(assessment)
    return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_default_host_actuation_safety_policy() -> HostActuationSafetyPolicy:
    return HostActuationSafetyPolicy(
        policy_id="host-actuation-safety-gate-policy-v1",
        required_gates_by_domain={key: tuple(value) for key, value in _REQUIRED_GATES.items()},
        blocked_actions_by_domain={key: tuple(value) for key, value in _BLOCKED_BY_DOMAIN.items()},
    )

def _safe_domain(domain: str) -> str:
    if domain not in SAFETY_DOMAINS:
        raise ValueError(f"unsupported safety domain: {domain}")
    return domain

def _default_created(created_at: str | None) -> str:
    return created_at or "1970-01-01T00:00:00+00:00"

def build_hardware_allowlist_manifest(domain: str, *, created_at: str | None = None, entries: Sequence[HardwareAllowlistEntry] | None = None) -> HardwareAllowlistManifest:
    domain = _safe_domain(domain)
    default_entry = HardwareAllowlistEntry(
        entry_id=f"hardware-allowlist-entry-{domain}",
        hardware_kind="reviewer_declared_hardware_target",
        hardware_label=f"metadata-only-{domain}-target",
        vendor_label=None,
        model_label=None,
        os_family="declared_os_family_only",
        backend_class="declared_backend_class_only",
        allowed_for_domains=(domain,),
        denied_for_domains=tuple(sorted(SAFETY_DOMAINS - {domain})),
        required_bounds_policy_labels=("bounds_policy_declared",),
        required_cooldown_policy_labels=("cooldown_policy_declared",),
        required_panic_stop_labels=("panic_stop_declared",),
        warning_codes=("allowlist_does_not_grant_control",),
        risk_codes=(),
    )
    provisional = HardwareAllowlistManifest(
        manifest_id=f"hardware-allowlist-manifest-{domain}",
        entries=tuple(entries) if entries is not None else (default_entry,),
        allowed_domain_labels=(domain,),
        denied_domain_labels=tuple(sorted(SAFETY_DOMAINS - {domain})),
        warning_codes=("metadata_allowlist_only",),
        risk_codes=(),
        created_at=_default_created(created_at),
        digest="",
    )
    return replace(provisional, digest=hardware_allowlist_manifest_digest(provisional))

def build_os_backend_declaration(domain: str, *, created_at: str | None = None) -> OSBackendDeclaration:
    domain = _safe_domain(domain)
    provisional = OSBackendDeclaration(
        declaration_id=f"os-backend-declaration-{domain}",
        backend_class="declared_backend_class_only",
        os_family="declared_os_family_only",
        backend_label=f"metadata-only-{domain}-backend",
        supported_domains=(domain,),
        unsupported_domains=tuple(sorted(SAFETY_DOMAINS - {domain})),
        required_privilege_labels=("future_operator_privilege_review_required",),
        required_scope_labels=("explicit_scope_required", "target_scope_declared"),
        warning_codes=("backend_not_loaded_or_invoked",),
        risk_codes=(),
        created_at=_default_created(created_at),
        digest="",
    )
    return replace(provisional, digest=os_backend_declaration_digest(provisional))

def build_bounds_policy(domain: str, *, created_at: str | None = None, target_label: str = "declared_target_only") -> BoundsPolicy:
    domain = _safe_domain(domain)
    provisional = BoundsPolicy(
        policy_id=f"bounds-policy-{domain}", domain=domain, target_label=target_label,
        lower_bound_label="declared_lower_bound_only", upper_bound_label="declared_upper_bound_only",
        step_limit_label="declared_step_limit_only", rate_limit_label="declared_rate_limit_only",
        forbidden_value_labels=("unbounded_value", "unsafe_value"),
        warning_codes=("bounds_not_enforced_live",), risk_codes=(), created_at=_default_created(created_at), digest="",
    )
    return replace(provisional, digest=bounds_policy_digest(provisional))

def build_cooldown_policy(domain: str, *, created_at: str | None = None, target_label: str = "declared_target_only") -> CooldownPolicy:
    domain = _safe_domain(domain)
    provisional = CooldownPolicy(
        policy_id=f"cooldown-policy-{domain}", domain=domain, target_label=target_label,
        minimum_interval_label="declared_minimum_interval_only", maximum_attempts_label="declared_maximum_attempts_only",
        cooldown_reset_label="declared_cooldown_reset_only", warning_codes=("cooldown_not_enforced_live",),
        risk_codes=(), created_at=_default_created(created_at), digest="",
    )
    return replace(provisional, digest=cooldown_policy_digest(provisional))

def build_panic_stop_contract(domain: str, *, created_at: str | None = None) -> PanicStopContract:
    domain = _safe_domain(domain)
    provisional = PanicStopContract(
        contract_id=f"panic-stop-contract-{domain}", domain=domain,
        trigger_labels=("operator_panic_signal", "supervisor_anomaly_signal"),
        stop_labels=("future_control_grant_suspend", "future_fulfillment_halt"),
        operator_override_labels=("local_operator_required",),
        recovery_labels=("manual_review_required", "postcondition_recheck_required"),
        warning_codes=("panic_stop_not_executed",), risk_codes=(), created_at=_default_created(created_at), digest="",
    )
    return replace(provisional, digest=panic_stop_contract_digest(provisional))

def build_host_action_scope_manifest(domain: str, *, created_at: str | None = None) -> HostActionScopeManifest:
    domain = _safe_domain(domain)
    forbidden = _BLOCKED_BY_DOMAIN.get(domain, tuple(sorted(BLOCKED_ACTION_LABELS)))
    provisional = HostActionScopeManifest(
        scope_id=f"host-action-scope-{domain}", domain=domain,
        target_labels=(f"metadata-only-{domain}-target",),
        allowed_action_labels=("declare_safety_gate_posture", "review_gate_evidence"),
        forbidden_action_labels=tuple(sorted(set(forbidden))),
        path_scope_labels=("explicit_path_scope_required",) if domain in {"cleanup_control_future", "file_control_future"} else (),
        service_scope_labels=("explicit_service_scope_required",) if domain == "service_control_future" else (),
        hardware_scope_labels=("explicit_hardware_scope_required",) if domain in {"cooling_control_future", "power_control_future", "thermal_safety"} else (),
        time_bound_labels=("time_bounds_required",), expiry_labels=("expiry_required",), revocation_labels=("revocation_path_required",),
        warning_codes=("scope_manifest_does_not_authorize_action",), risk_codes=(), created_at=_default_created(created_at), digest="",
    )
    return replace(provisional, digest=host_action_scope_manifest_digest(provisional))


def _declared_labels(hardware: HardwareAllowlistManifest | None, os_backend: OSBackendDeclaration | None, bounds: BoundsPolicy | None, cooldown: CooldownPolicy | None, panic: PanicStopContract | None, scope: HostActionScopeManifest | None) -> set[str]:
    labels = {"operator_identity_required", "policy_identity_required", "time_bounds_required", "expiry_required", "revocation_path_required", "control_plane_admission_required", "audit_receipt_required", "rollback_plan_required", "rollback_receipt_required", "effect_receipt_required", "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required", "dry_run_rehearsal_required"}
    if hardware: labels.add("hardware_allowlist_declared")
    if os_backend: labels.add("os_backend_declared")
    if bounds: labels.add("bounds_policy_declared")
    if cooldown: labels.add("cooldown_policy_declared")
    if panic: labels.add("panic_stop_declared")
    if scope:
        labels.update({"explicit_scope_required", "target_scope_declared"})
    return labels

def assess_host_actuation_safety_gates(
    domain: str, *,
    hardware_allowlist_manifest: HardwareAllowlistManifest | None = None,
    os_backend_declaration: OSBackendDeclaration | None = None,
    bounds_policy: BoundsPolicy | None = None,
    cooldown_policy: CooldownPolicy | None = None,
    panic_stop_contract: PanicStopContract | None = None,
    host_action_scope_manifest: HostActionScopeManifest | None = None,
    source_controlled_authorization_contract_id: str | None = None,
    source_controlled_authorization_contract_digest: str | None = None,
) -> tuple[HostActuationGateAssessment, ...]:
    domain = _safe_domain(domain)
    declared = _declared_labels(hardware_allowlist_manifest, os_backend_declaration, bounds_policy, cooldown_policy, panic_stop_contract, host_action_scope_manifest)
    assessments: list[HostActuationGateAssessment] = []
    for gate in _REQUIRED_GATES[domain]:
        declared_gate = _DECLARED_FOR_REQUIRED.get(gate, gate)
        satisfied = declared_gate in declared or gate in declared
        status = "host_actuation_gate_satisfied" if satisfied else "host_actuation_gate_missing"
        missing = () if satisfied else (gate, declared_gate)
        evidence = (declared_gate,) if satisfied else ()
        assessment = HostActuationGateAssessment(
            assessment_id=f"host-actuation-gate-{domain}-{gate}",
            source_controlled_authorization_contract_id=source_controlled_authorization_contract_id,
            source_controlled_authorization_contract_digest=source_controlled_authorization_contract_digest,
            domain=domain, gate_label=gate, gate_status=status, evidence_labels=evidence,
            missing_labels=missing, blocked_actions=tuple(sorted(_BLOCKED_BY_DOMAIN.get(domain, ()))),
            warning_codes=("gate_assessment_metadata_only",), risk_codes=(),
        )
        assessments.append(assessment)
    return tuple(assessments)

def build_safety_gate_satisfaction_manifest(
    domain: str, *,
    hardware_allowlist_manifest: HardwareAllowlistManifest | None = None,
    os_backend_declaration: OSBackendDeclaration | None = None,
    bounds_policy: BoundsPolicy | None = None,
    cooldown_policy: CooldownPolicy | None = None,
    panic_stop_contract: PanicStopContract | None = None,
    host_action_scope_manifest: HostActionScopeManifest | None = None,
    gate_assessments: Sequence[HostActuationGateAssessment] | None = None,
    source_controlled_authorization_contract_id: str | None = None,
    source_controlled_authorization_contract_digest: str | None = None,
    created_at: str | None = None,
) -> SafetyGateSatisfactionManifest:
    domain = _safe_domain(domain)
    assessments = tuple(gate_assessments) if gate_assessments is not None else assess_host_actuation_safety_gates(
        domain,
        hardware_allowlist_manifest=hardware_allowlist_manifest,
        os_backend_declaration=os_backend_declaration,
        bounds_policy=bounds_policy,
        cooldown_policy=cooldown_policy,
        panic_stop_contract=panic_stop_contract,
        host_action_scope_manifest=host_action_scope_manifest,
        source_controlled_authorization_contract_id=source_controlled_authorization_contract_id,
        source_controlled_authorization_contract_digest=source_controlled_authorization_contract_digest,
    )
    missing = tuple(sorted({label for assessment in assessments for label in assessment.missing_labels}))
    satisfied = tuple(sorted({assessment.gate_label for assessment in assessments if assessment.gate_status in {"host_actuation_gate_satisfied", "host_actuation_gate_satisfied_with_conditions"}}))
    status = "host_actuation_safety_ready" if not missing and domain in {"diagnostics_only", "operator_review"} else "host_actuation_safety_ready_with_conditions" if not missing else "host_actuation_safety_incomplete"
    blocked = tuple(sorted(set(_BLOCKED_BY_DOMAIN.get(domain, ("live_authorization_grant", "host_mutation"))) | {"live_authorization_grant", "host_mutation"}))
    provisional = SafetyGateSatisfactionManifest(
        manifest_id=f"safety-gate-satisfaction-{domain}",
        source_controlled_authorization_contract_id=source_controlled_authorization_contract_id,
        source_controlled_authorization_contract_digest=source_controlled_authorization_contract_digest,
        domain=domain, safety_status=status,
        hardware_allowlist_manifest_id=getattr(hardware_allowlist_manifest, "manifest_id", None),
        os_backend_declaration_id=getattr(os_backend_declaration, "declaration_id", None),
        bounds_policy_id=getattr(bounds_policy, "policy_id", None),
        cooldown_policy_id=getattr(cooldown_policy, "policy_id", None),
        panic_stop_contract_id=getattr(panic_stop_contract, "contract_id", None),
        host_action_scope_manifest_id=getattr(host_action_scope_manifest, "scope_id", None),
        gate_assessment_ids=tuple(assessment.assessment_id for assessment in assessments),
        satisfied_gate_labels=satisfied, missing_gate_labels=missing, blocked_actions=blocked,
        warning_codes=("safety_gates_are_not_authorization",), risk_codes=(), created_at=_default_created(created_at), digest="",
    )
    return replace(provisional, digest=safety_gate_satisfaction_manifest_digest(provisional))


def build_safety_gates_for_domain(domain: str, *, created_at: str | None = None) -> HostActuationSafetyBundle:
    domain = _safe_domain(domain)
    hardware = build_hardware_allowlist_manifest(domain, created_at=created_at) if domain == "cooling_control_future" else None
    os_backend = build_os_backend_declaration(domain, created_at=created_at) if any(g == "os_backend_declaration_required" for g in _REQUIRED_GATES[domain]) else None
    bounds = build_bounds_policy(domain, created_at=created_at) if any(g == "bounds_policy_required" for g in _REQUIRED_GATES[domain]) else None
    cooldown = build_cooldown_policy(domain, created_at=created_at) if any(g == "cooldown_policy_required" for g in _REQUIRED_GATES[domain]) else None
    panic = build_panic_stop_contract(domain, created_at=created_at) if any(g == "panic_stop_required" for g in _REQUIRED_GATES[domain]) else None
    scope = build_host_action_scope_manifest(domain, created_at=created_at)
    assessments = assess_host_actuation_safety_gates(domain, hardware_allowlist_manifest=hardware, os_backend_declaration=os_backend, bounds_policy=bounds, cooldown_policy=cooldown, panic_stop_contract=panic, host_action_scope_manifest=scope)
    manifest = build_safety_gate_satisfaction_manifest(domain, hardware_allowlist_manifest=hardware, os_backend_declaration=os_backend, bounds_policy=bounds, cooldown_policy=cooldown, panic_stop_contract=panic, host_action_scope_manifest=scope, gate_assessments=assessments, created_at=created_at)
    return HostActuationSafetyBundle(hardware, os_backend, bounds, cooldown, panic, scope, assessments, manifest)

_AUTH_DOMAIN_MAP = {
    "future_cooling_authorization_review": "cooling_control_future",
    "future_power_authorization_review": "power_control_future",
    "future_cleanup_authorization_review": "cleanup_control_future",
    "future_service_authorization_review": "service_control_future",
    "thermal_safety_authorization_review": "thermal_safety",
    "operator_review_authorization_review": "operator_review",
    "diagnostics_authorization_review": "diagnostics_only",
}

def build_safety_gates_for_controlled_authorization_contract(contract: Any, *, created_at: str | None = None) -> HostActuationSafetyBundle:
    domain = _AUTH_DOMAIN_MAP.get(str(getattr(contract, "authorization_domain", "")), str(getattr(contract, "authorization_domain", "diagnostics_only")))
    if domain not in SAFETY_DOMAINS:
        domain = "diagnostics_only"
    base = build_safety_gates_for_domain(domain, created_at=created_at)
    assessments = assess_host_actuation_safety_gates(
        domain,
        hardware_allowlist_manifest=base.hardware_allowlist_manifest,
        os_backend_declaration=base.os_backend_declaration,
        bounds_policy=base.bounds_policy,
        cooldown_policy=base.cooldown_policy,
        panic_stop_contract=base.panic_stop_contract,
        host_action_scope_manifest=base.host_action_scope_manifest,
        source_controlled_authorization_contract_id=getattr(contract, "contract_id", None),
        source_controlled_authorization_contract_digest=getattr(contract, "digest", None),
    )
    manifest = build_safety_gate_satisfaction_manifest(
        domain,
        hardware_allowlist_manifest=base.hardware_allowlist_manifest,
        os_backend_declaration=base.os_backend_declaration,
        bounds_policy=base.bounds_policy,
        cooldown_policy=base.cooldown_policy,
        panic_stop_contract=base.panic_stop_contract,
        host_action_scope_manifest=base.host_action_scope_manifest,
        gate_assessments=assessments,
        source_controlled_authorization_contract_id=getattr(contract, "contract_id", None),
        source_controlled_authorization_contract_digest=getattr(contract, "digest", None),
        created_at=created_at,
    )
    return replace(base, gate_assessments=assessments, safety_gate_satisfaction_manifest=manifest)


def _validate_common(payload: Mapping[str, Any], *, prefix: str) -> list[str]:
    findings: list[str] = []
    if not payload.get("metadata_only", False): findings.append(prefix + "not_metadata_only")
    for flag in ("grants_live_authorization", "live_authorization_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "process_kill_performed", "service_restart_performed", "package_install_performed", "driver_install_performed", "file_cleanup_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed", "grants_control_authority", "backend_loaded", "backend_invoked", "bounds_enforced_live", "cooldown_enforced_live", "panic_stop_executed"):
        if payload.get(flag, False): findings.append(prefix + "forbidden_flag:" + flag)
    return findings

def validate_hardware_allowlist_manifest(manifest: HardwareAllowlistManifest | Mapping[str, Any]) -> HostActuationSafetyValidationResult:
    payload = manifest.to_dict() if isinstance(manifest, HardwareAllowlistManifest) else dict(manifest)
    findings = _validate_common(payload, prefix="hardware_allowlist_manifest:")
    if not payload.get("allowlist_only", False): findings.append("hardware_allowlist_manifest:not_allowlist_only")
    for entry in payload.get("entries", ()) or ():
        findings.extend(_validate_common(entry, prefix="hardware_allowlist_entry:"))
        if entry.get("grants_control_authority", False): findings.append("hardware_allowlist_entry:forbidden_flag:grants_control_authority")
    if payload.get("digest") and payload.get("digest") != hardware_allowlist_manifest_digest(payload): findings.append("hardware_allowlist_manifest:digest_mismatch")
    return HostActuationSafetyValidationResult(not findings, tuple(findings))

def validate_os_backend_declaration(declaration: OSBackendDeclaration | Mapping[str, Any]) -> HostActuationSafetyValidationResult:
    payload = declaration.to_dict() if isinstance(declaration, OSBackendDeclaration) else dict(declaration)
    findings = _validate_common(payload, prefix="os_backend_declaration:")
    if not payload.get("declaration_only", False): findings.append("os_backend_declaration:not_declaration_only")
    if payload.get("digest") and payload.get("digest") != os_backend_declaration_digest(payload): findings.append("os_backend_declaration:digest_mismatch")
    return HostActuationSafetyValidationResult(not findings, tuple(findings))

def validate_bounds_policy(policy: BoundsPolicy | Mapping[str, Any]) -> HostActuationSafetyValidationResult:
    payload = policy.to_dict() if isinstance(policy, BoundsPolicy) else dict(policy)
    findings = _validate_common(payload, prefix="bounds_policy:")
    if not payload.get("policy_only", False): findings.append("bounds_policy:not_policy_only")
    if payload.get("digest") and payload.get("digest") != bounds_policy_digest(payload): findings.append("bounds_policy:digest_mismatch")
    return HostActuationSafetyValidationResult(not findings, tuple(findings))

def validate_cooldown_policy(policy: CooldownPolicy | Mapping[str, Any]) -> HostActuationSafetyValidationResult:
    payload = policy.to_dict() if isinstance(policy, CooldownPolicy) else dict(policy)
    findings = _validate_common(payload, prefix="cooldown_policy:")
    if not payload.get("policy_only", False): findings.append("cooldown_policy:not_policy_only")
    if payload.get("digest") and payload.get("digest") != cooldown_policy_digest(payload): findings.append("cooldown_policy:digest_mismatch")
    return HostActuationSafetyValidationResult(not findings, tuple(findings))

def validate_panic_stop_contract(contract: PanicStopContract | Mapping[str, Any]) -> HostActuationSafetyValidationResult:
    payload = contract.to_dict() if isinstance(contract, PanicStopContract) else dict(contract)
    findings = _validate_common(payload, prefix="panic_stop_contract:")
    if not payload.get("contract_only", False): findings.append("panic_stop_contract:not_contract_only")
    if payload.get("digest") and payload.get("digest") != panic_stop_contract_digest(payload): findings.append("panic_stop_contract:digest_mismatch")
    return HostActuationSafetyValidationResult(not findings, tuple(findings))

def validate_host_action_scope_manifest(scope: HostActionScopeManifest | Mapping[str, Any]) -> HostActuationSafetyValidationResult:
    payload = scope.to_dict() if isinstance(scope, HostActionScopeManifest) else dict(scope)
    findings = _validate_common(payload, prefix="host_action_scope_manifest:")
    if not payload.get("scope_only", False): findings.append("host_action_scope_manifest:not_scope_only")
    if payload.get("digest") and payload.get("digest") != host_action_scope_manifest_digest(payload): findings.append("host_action_scope_manifest:digest_mismatch")
    return HostActuationSafetyValidationResult(not findings, tuple(findings))

def validate_host_actuation_gate_assessment(assessment: HostActuationGateAssessment | Mapping[str, Any]) -> HostActuationSafetyValidationResult:
    payload = assessment.to_dict() if isinstance(assessment, HostActuationGateAssessment) else dict(assessment)
    findings = _validate_common(payload, prefix="host_actuation_gate_assessment:")
    if payload.get("gate_status") not in GATE_ASSESSMENT_STATUSES: findings.append("host_actuation_gate_assessment:unknown_status")
    if not payload.get("assessment_only", False): findings.append("host_actuation_gate_assessment:not_assessment_only")
    return HostActuationSafetyValidationResult(not findings, tuple(findings))

def validate_safety_gate_satisfaction_manifest(manifest: SafetyGateSatisfactionManifest | Mapping[str, Any]) -> HostActuationSafetyValidationResult:
    payload = manifest.to_dict() if isinstance(manifest, SafetyGateSatisfactionManifest) else dict(manifest)
    findings = _validate_common(payload, prefix="safety_gate_satisfaction_manifest:")
    if payload.get("safety_status") not in SAFETY_STATUSES: findings.append("safety_gate_satisfaction_manifest:unknown_status")
    if not payload.get("safety_gate_only", False): findings.append("safety_gate_satisfaction_manifest:not_safety_gate_only")
    if payload.get("digest") and payload.get("digest") != safety_gate_satisfaction_manifest_digest(payload): findings.append("safety_gate_satisfaction_manifest:digest_mismatch")
    return HostActuationSafetyValidationResult(not findings, tuple(findings))


def summarize_hardware_allowlist_manifest(manifest: HardwareAllowlistManifest) -> dict[str, Any]:
    return {"manifest_id": manifest.manifest_id, "entry_count": len(manifest.entries), "metadata_only": manifest.metadata_only, "allowlist_only": manifest.allowlist_only, "grants_control_authority": manifest.grants_control_authority, "host_mutation_performed": manifest.host_mutation_performed, "digest": manifest.digest}

def summarize_os_backend_declaration(declaration: OSBackendDeclaration) -> dict[str, Any]:
    return {"declaration_id": declaration.declaration_id, "backend_class": declaration.backend_class, "metadata_only": declaration.metadata_only, "declaration_only": declaration.declaration_only, "backend_loaded": declaration.backend_loaded, "backend_invoked": declaration.backend_invoked, "host_mutation_performed": declaration.host_mutation_performed, "digest": declaration.digest}

def summarize_bounds_policy(policy: BoundsPolicy) -> dict[str, Any]:
    return {"policy_id": policy.policy_id, "domain": policy.domain, "metadata_only": policy.metadata_only, "policy_only": policy.policy_only, "bounds_enforced_live": policy.bounds_enforced_live, "host_mutation_performed": policy.host_mutation_performed, "digest": policy.digest}

def summarize_cooldown_policy(policy: CooldownPolicy) -> dict[str, Any]:
    return {"policy_id": policy.policy_id, "domain": policy.domain, "metadata_only": policy.metadata_only, "policy_only": policy.policy_only, "cooldown_enforced_live": policy.cooldown_enforced_live, "host_mutation_performed": policy.host_mutation_performed, "digest": policy.digest}

def summarize_panic_stop_contract(contract: PanicStopContract) -> dict[str, Any]:
    return {"contract_id": contract.contract_id, "domain": contract.domain, "metadata_only": contract.metadata_only, "contract_only": contract.contract_only, "panic_stop_executed": contract.panic_stop_executed, "host_mutation_performed": contract.host_mutation_performed, "digest": contract.digest}

def summarize_host_action_scope_manifest(scope: HostActionScopeManifest) -> dict[str, Any]:
    return {"scope_id": scope.scope_id, "domain": scope.domain, "metadata_only": scope.metadata_only, "scope_only": scope.scope_only, "grants_control_authority": scope.grants_control_authority, "host_mutation_performed": scope.host_mutation_performed, "digest": scope.digest}

def summarize_host_actuation_gate_assessment(assessment: HostActuationGateAssessment) -> dict[str, Any]:
    return {"assessment_id": assessment.assessment_id, "domain": assessment.domain, "gate_label": assessment.gate_label, "gate_status": assessment.gate_status, "metadata_only": assessment.metadata_only, "assessment_only": assessment.assessment_only, "grants_control_authority": assessment.grants_control_authority, "host_mutation_performed": assessment.host_mutation_performed}

def summarize_safety_gate_satisfaction_manifest(manifest: SafetyGateSatisfactionManifest) -> dict[str, Any]:
    return {"manifest_id": manifest.manifest_id, "domain": manifest.domain, "safety_status": manifest.safety_status, "satisfied_gate_count": len(manifest.satisfied_gate_labels), "missing_gate_count": len(manifest.missing_gate_labels), "blocked_actions": manifest.blocked_actions, "metadata_only": manifest.metadata_only, "safety_gate_only": manifest.safety_gate_only, "grants_live_authorization": manifest.grants_live_authorization, "grants_control_authority": manifest.grants_control_authority, "fulfillment_granted": manifest.fulfillment_granted, "effect_performed": manifest.effect_performed, "host_mutation_performed": manifest.host_mutation_performed, "digest": manifest.digest}

def summarize_host_actuation_safety_policy(policy: HostActuationSafetyPolicy) -> dict[str, Any]:
    return {"policy_id": policy.policy_id, "domain_count": len(policy.required_gates_by_domain), "metadata_only": policy.metadata_only, "safety_gate_only": policy.safety_gate_only, "grants_live_authorization": policy.grants_live_authorization, "grants_control_authority": policy.grants_control_authority, "host_mutation_performed": policy.host_mutation_performed}
