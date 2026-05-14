"""Metadata-only authorization review for execution readiness manifests.

This wing evaluates whether an ExecutionReadinessManifest is complete, bounded,
and safe enough to be presented for future operator/policy authorization
consideration. It does not grant authorization, execute host actions, mutate host
state, write fan/PWM controls, change thermal or power settings, kill processes,
restart services, install packages or drivers, delete files, perform cleanup,
perform network calls, invoke providers, assemble prompts, transport federation
state, or perform remote execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.effect_proof import EXECUTION_READINESS_STATUSES, ExecutionReadinessManifest, execution_readiness_manifest_digest

AUTHORIZATION_REVIEW_PACKET_STATUSES = frozenset({
    "authorization_review_packet_ready",
    "authorization_review_packet_ready_with_conditions",
    "authorization_review_packet_blocked",
    "authorization_review_packet_incomplete",
    "authorization_review_packet_contradicted",
})
AUTHORIZATION_REVIEW_DECISION_STATUSES = frozenset({
    "authorization_review_eligible_for_operator_review",
    "authorization_review_eligible_with_conditions",
    "authorization_review_blocked",
    "authorization_review_incomplete",
    "authorization_review_contradicted",
})
AUTHORIZATION_REVIEW_RECEIPT_STATUSES = frozenset({
    "authorization_review_receipt_recorded",
    "authorization_review_receipt_recorded_with_warnings",
    "authorization_review_receipt_blocked",
    "authorization_review_receipt_incomplete",
    "authorization_review_receipt_contradicted",
})
FUTURE_AUTHORIZATION_GRANT_SCHEMA_STATUSES = frozenset({
    "future_authorization_grant_schema_ready",
    "future_authorization_grant_schema_ready_with_conditions",
    "future_authorization_grant_schema_blocked",
    "future_authorization_grant_schema_incomplete",
    "future_authorization_grant_schema_contradicted",
})
AUTHORIZATION_DOMAINS = frozenset({
    "diagnostics_authorization_review",
    "operator_review_authorization_review",
    "resource_pressure_authorization_review",
    "thermal_safety_authorization_review",
    "disk_safety_authorization_review",
    "service_health_authorization_review",
    "future_cooling_authorization_review",
    "future_power_authorization_review",
    "future_cleanup_authorization_review",
    "future_service_authorization_review",
})
APPROVAL_CLASSES = frozenset({
    "no_operator_action_required_for_diagnostics",
    "operator_explicit_approval_required",
    "policy_explicit_approval_required",
    "dual_operator_policy_approval_required",
    "future_hardware_safety_approval_required",
    "future_filesystem_scope_approval_required",
    "future_service_scope_approval_required",
})
BASE_AUTHORIZATION_GATES = (
    "execution_readiness_manifest_required",
    "effect_receipt_contract_required",
    "future_effect_receipt_schema_required",
    "postcondition_plan_required",
    "rollback_plan_required",
    "control_plane_admission_required_for_future_action",
    "operator_or_policy_approval_required_for_future_action",
    "audit_receipt_required_for_future_action",
    "rollback_receipt_required_for_future_action",
    "effect_receipt_required_for_future_action",
    "postcondition_check_required_for_future_action",
    "immutable_trace_required_for_future_action",
)
REQUIRED_AUTHORIZATION_GATES = frozenset(BASE_AUTHORIZATION_GATES + (
    "runtime_supervisor_observation_required",
    "panic_stop_required_for_future_action",
    "hardware_allowlist_required_for_future_action",
    "os_backend_declaration_required_for_future_action",
    "bounds_policy_required_for_future_action",
    "cooldown_policy_required_for_future_action",
    "dry_run_rehearsal_evidence_required_for_future_action",
    "filesystem_scope_required_for_future_action",
    "path_scope_labels_required_for_future_action",
    "service_scope_required_for_future_action",
))
BLOCKED_ACTION_LABELS = frozenset({
    "authorization_grant",
    "host_mutation",
    "fan_pwm_write",
    "thermal_actuation",
    "power_profile_mutation",
    "process_kill",
    "service_restart",
    "package_install",
    "driver_install",
    "file_cleanup",
    "file_delete",
    "provider_invocation",
    "network_egress",
    "prompt_assembly",
    "federation_transport",
    "remote_execution",
})

_EFFECT_TO_AUTH_DOMAIN: Mapping[str, str] = {
    "diagnostics_only": "diagnostics_authorization_review",
    "operator_review": "operator_review_authorization_review",
    "resource_pressure_review": "resource_pressure_authorization_review",
    "thermal_safety_review": "thermal_safety_authorization_review",
    "disk_safety_review": "disk_safety_authorization_review",
    "service_health_review": "service_health_authorization_review",
    "future_cooling_effect": "future_cooling_authorization_review",
    "future_power_effect": "future_power_authorization_review",
    "future_cleanup_effect": "future_cleanup_authorization_review",
    "future_service_effect": "future_service_authorization_review",
}
_DOMAIN_APPROVAL: Mapping[str, str] = {
    "diagnostics_authorization_review": "no_operator_action_required_for_diagnostics",
    "operator_review_authorization_review": "operator_explicit_approval_required",
    "resource_pressure_authorization_review": "operator_explicit_approval_required",
    "thermal_safety_authorization_review": "policy_explicit_approval_required",
    "disk_safety_authorization_review": "policy_explicit_approval_required",
    "service_health_authorization_review": "operator_explicit_approval_required",
    "future_cooling_authorization_review": "future_hardware_safety_approval_required",
    "future_power_authorization_review": "dual_operator_policy_approval_required",
    "future_cleanup_authorization_review": "future_filesystem_scope_approval_required",
    "future_service_authorization_review": "future_service_scope_approval_required",
}
_PROOF_TO_AUTH_GATE: Mapping[str, str] = {
    "control_plane_admission_required": "control_plane_admission_required_for_future_action",
    "operator_or_policy_approval_required": "operator_or_policy_approval_required_for_future_action",
    "audit_receipt_required": "audit_receipt_required_for_future_action",
    "rollback_receipt_required": "rollback_receipt_required_for_future_action",
    "effect_receipt_required": "effect_receipt_required_for_future_action",
    "postcondition_check_required": "postcondition_check_required_for_future_action",
    "panic_stop_required": "panic_stop_required_for_future_action",
    "immutable_trace_required": "immutable_trace_required_for_future_action",
    "runtime_supervisor_observation_required": "runtime_supervisor_observation_required",
    "rollback_plan_required": "rollback_plan_required",
    "hardware_allowlist_required": "hardware_allowlist_required_for_future_action",
    "os_backend_declaration_required": "os_backend_declaration_required_for_future_action",
    "bounds_policy_required": "bounds_policy_required_for_future_action",
    "cooldown_policy_required": "cooldown_policy_required_for_future_action",
    "dry_run_required": "dry_run_rehearsal_evidence_required_for_future_action",
    "rehearsal_required": "dry_run_rehearsal_evidence_required_for_future_action",
}
_DOMAIN_REQUIRED_GATES: Mapping[str, tuple[str, ...]] = {
    "diagnostics_authorization_review": (
        "execution_readiness_manifest_required", "effect_receipt_contract_required", "future_effect_receipt_schema_required", "postcondition_plan_required", "rollback_plan_required", "immutable_trace_required_for_future_action",
    ),
    "operator_review_authorization_review": BASE_AUTHORIZATION_GATES,
    "resource_pressure_authorization_review": BASE_AUTHORIZATION_GATES,
    "thermal_safety_authorization_review": BASE_AUTHORIZATION_GATES + ("runtime_supervisor_observation_required",),
    "disk_safety_authorization_review": BASE_AUTHORIZATION_GATES + ("dry_run_rehearsal_evidence_required_for_future_action",),
    "service_health_authorization_review": BASE_AUTHORIZATION_GATES + ("runtime_supervisor_observation_required",),
    "future_cooling_authorization_review": BASE_AUTHORIZATION_GATES + ("runtime_supervisor_observation_required", "panic_stop_required_for_future_action", "hardware_allowlist_required_for_future_action", "os_backend_declaration_required_for_future_action", "bounds_policy_required_for_future_action", "cooldown_policy_required_for_future_action"),
    "future_power_authorization_review": BASE_AUTHORIZATION_GATES + ("runtime_supervisor_observation_required", "panic_stop_required_for_future_action", "os_backend_declaration_required_for_future_action", "bounds_policy_required_for_future_action"),
    "future_cleanup_authorization_review": BASE_AUTHORIZATION_GATES + ("dry_run_rehearsal_evidence_required_for_future_action", "filesystem_scope_required_for_future_action", "path_scope_labels_required_for_future_action"),
    "future_service_authorization_review": BASE_AUTHORIZATION_GATES + ("runtime_supervisor_observation_required", "service_scope_required_for_future_action"),
}
_BLOCKED_ACTION_MAP: Mapping[str, str] = {
    "host_mutation_without_authorization": "host_mutation",
    "fan_pwm_write_without_allowlist": "fan_pwm_write",
    "thermal_actuation_without_policy": "thermal_actuation",
    "power_profile_mutation_without_policy": "power_profile_mutation",
    "process_kill_without_authorization": "process_kill",
    "service_restart_without_authorization": "service_restart",
    "package_install_without_authorization": "package_install",
    "driver_install_without_authorization": "driver_install",
    "file_cleanup_without_scope": "file_cleanup",
    "file_delete_without_scope": "file_delete",
    "provider_invocation": "provider_invocation",
    "network_egress": "network_egress",
    "prompt_assembly": "prompt_assembly",
    "federation_transport": "federation_transport",
    "remote_execution": "remote_execution",
}
_DOMAIN_BLOCKS: Mapping[str, tuple[str, ...]] = {
    "future_cooling_authorization_review": ("fan_pwm_write", "thermal_actuation"),
    "future_power_authorization_review": ("power_profile_mutation",),
    "future_cleanup_authorization_review": ("file_cleanup", "file_delete"),
    "future_service_authorization_review": ("service_restart", "process_kill"),
    "service_health_authorization_review": ("service_restart", "process_kill"),
}

@dataclass(frozen=True)
class AuthorizationReviewPolicy:
    policy_id: str
    domain_required_gates: Mapping[str, tuple[str, ...]]
    domain_approval_classes: Mapping[str, str]
    blocked_actions: tuple[str, ...]
    metadata_only: bool = True
    review_only: bool = True
    authorization_granted: bool = False

@dataclass(frozen=True)
class AuthorizationReviewPacket:
    packet_id: str
    source_execution_readiness_manifest_id: str
    source_execution_readiness_manifest_digest: str
    effect_contract_id: str
    future_effect_receipt_id: str
    postcondition_plan_id: str
    rollback_plan_id: str
    runtime_supervisor_report_id: str | None
    effect_domain: str
    backend_class: str
    readiness_status: str
    packet_status: str
    approval_class: str
    required_authorization_gates: tuple[str, ...]
    satisfied_authorization_gates: tuple[str, ...]
    missing_authorization_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    review_only: bool = True
    authorization_granted: bool = False
    fulfillment_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class AuthorizationReviewDecision:
    decision_id: str
    packet_id: str
    source_execution_readiness_manifest_id: str
    source_execution_readiness_manifest_digest: str
    authorization_domain: str
    approval_class: str
    decision_status: str
    reason_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    required_authorization_gates: tuple[str, ...]
    missing_authorization_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    metadata_only: bool = True
    review_only: bool = True
    authorization_granted: bool = False
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
class AuthorizationReviewReceipt:
    receipt_id: str
    decision_id: str
    packet_id: str
    source_execution_readiness_manifest_id: str
    source_execution_readiness_manifest_digest: str
    authorization_domain: str
    approval_class: str
    decision_status: str
    receipt_status: str
    evidence_summary: tuple[str, ...]
    required_authorization_gates: tuple[str, ...]
    missing_authorization_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    review_only: bool = True
    authorization_not_granted: bool = True
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    does_not_authorize_fulfillment: bool = True
    requires_future_authorization_grant: bool = True
    requires_control_plane_admission_for_future_action: bool = True
    requires_operator_or_policy_approval_for_future_action: bool = True
    requires_audit_receipt_for_future_action: bool = True
    requires_rollback_receipt_for_future_action: bool = True
    requires_effect_receipt_for_future_action: bool = True
    requires_postcondition_check_for_future_action: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class FutureAuthorizationGrantSchema:
    schema_id: str
    source_authorization_review_receipt_id: str
    source_authorization_review_receipt_digest: str
    authorization_domain: str
    approval_class: str
    schema_status: str
    required_authority_refs: tuple[str, ...]
    required_operator_identity_labels: tuple[str, ...]
    required_policy_labels: tuple[str, ...]
    required_scope_labels: tuple[str, ...]
    required_time_bounds: tuple[str, ...]
    required_revocation_labels: tuple[str, ...]
    required_audit_labels: tuple[str, ...]
    required_control_plane_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    schema_only: bool = True
    future_use_only: bool = True
    authorization_granted: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    does_not_authorize_fulfillment: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class AuthorizationReviewValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()

class AuthorizationReviewWingRecords(NamedTuple):
    packet: AuthorizationReviewPacket
    decision: AuthorizationReviewDecision
    receipt: AuthorizationReviewReceipt
    future_authorization_grant_schema: FutureAuthorizationGrantSchema


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest_payload(prefix: str, payload: Mapping[str, Any], length: int = 24) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:length]


def _record_digest(record: Any) -> str:
    payload = record.to_dict()
    if "digest" in payload:
        payload["digest"] = ""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def authorization_review_packet_digest(packet: AuthorizationReviewPacket) -> str: return _record_digest(packet)
def authorization_review_decision_digest(decision: AuthorizationReviewDecision) -> str: return _record_digest(decision)
def authorization_review_receipt_digest(receipt: AuthorizationReviewReceipt) -> str: return _record_digest(receipt)
def future_authorization_grant_schema_digest(schema: FutureAuthorizationGrantSchema) -> str: return _record_digest(schema)


def build_default_authorization_review_policy() -> AuthorizationReviewPolicy:
    return AuthorizationReviewPolicy(
        policy_id="sentientos-host-embodiment-authorization-review.v1",
        domain_required_gates={domain: tuple(sorted(gates)) for domain, gates in _DOMAIN_REQUIRED_GATES.items()},
        domain_approval_classes=dict(_DOMAIN_APPROVAL),
        blocked_actions=tuple(sorted(BLOCKED_ACTION_LABELS)),
    )


def _auth_domain_for_manifest(manifest: Any) -> str:
    return _EFFECT_TO_AUTH_DOMAIN.get(str(getattr(manifest, "effect_domain", "diagnostics_only")), "diagnostics_authorization_review")


def _blocked_actions_for_manifest(manifest: Any, authorization_domain: str) -> tuple[str, ...]:
    labels = {"authorization_grant", "host_mutation", "provider_invocation", "network_egress", "prompt_assembly", "federation_transport", "remote_execution"}
    labels.update(_DOMAIN_BLOCKS.get(authorization_domain, ()))
    for action in getattr(manifest, "blocked_actions", ()) or ():
        mapped = _BLOCKED_ACTION_MAP.get(str(action), str(action))
        if mapped in BLOCKED_ACTION_LABELS:
            labels.add(mapped)
    return tuple(sorted(labels & set(BLOCKED_ACTION_LABELS)))


def _source_contradictions(manifest: Any) -> tuple[str, ...]:
    findings: list[str] = []
    required_true = ("metadata_only", "readiness_only")
    for flag in required_true:
        if not getattr(manifest, flag, True):
            findings.append(f"source_manifest_missing_non_authority_flag:{flag}")
    forbidden_false = (
        "authorization_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed",
        "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed",
        "process_kill_performed", "service_restart_performed", "package_install_performed", "driver_install_performed",
        "file_cleanup_performed", "file_delete_performed", "provider_invocation_performed", "network_performed",
        "prompt_assembly_performed",
    )
    for flag in forbidden_false:
        if getattr(manifest, flag, False):
            findings.append(f"source_manifest_claims_forbidden_authority_or_effect:{flag}")
    if getattr(manifest, "readiness_status", "") not in EXECUTION_READINESS_STATUSES:
        findings.append("source_manifest_unknown_readiness_status")
    digest = str(getattr(manifest, "digest", "") or "")
    return tuple(findings)


def _satisfied_auth_gates(manifest: Any) -> tuple[str, ...]:
    gates = {
        "execution_readiness_manifest_required",
        "effect_receipt_contract_required" if getattr(manifest, "effect_contract_id", "") else "",
        "future_effect_receipt_schema_required" if getattr(manifest, "future_effect_receipt_id", "") else "",
        "postcondition_plan_required" if getattr(manifest, "postcondition_plan_id", "") else "",
        "rollback_plan_required" if getattr(manifest, "rollback_plan_id", "") else "",
    }
    for gate in getattr(manifest, "satisfied_proof_gates", ()) or ():
        mapped = _PROOF_TO_AUTH_GATE.get(str(gate))
        if mapped:
            gates.add(mapped)
    if getattr(manifest, "runtime_supervisor_report_id", None):
        gates.add("runtime_supervisor_observation_required")
    effect_domain = str(getattr(manifest, "effect_domain", ""))
    if effect_domain == "future_cleanup_effect":
        gates.update({"filesystem_scope_required_for_future_action", "path_scope_labels_required_for_future_action"})
    if effect_domain == "future_service_effect":
        gates.add("service_scope_required_for_future_action")
    return tuple(sorted(g for g in gates if g))


def _packet_status(readiness_status: str, contradictions: Sequence[str], missing: Sequence[str]) -> str:
    if contradictions or readiness_status.endswith("contradicted"):
        return "authorization_review_packet_contradicted"
    if readiness_status.endswith("incomplete"):
        return "authorization_review_packet_incomplete"
    if readiness_status.endswith("blocked"):
        return "authorization_review_packet_blocked"
    if missing:
        return "authorization_review_packet_incomplete"
    if readiness_status.endswith("with_conditions"):
        return "authorization_review_packet_ready_with_conditions"
    return "authorization_review_packet_ready"


def build_authorization_review_packet(manifest: ExecutionReadinessManifest, *, policy: AuthorizationReviewPolicy | None = None) -> AuthorizationReviewPacket:
    policy = policy or build_default_authorization_review_policy()
    authorization_domain = _auth_domain_for_manifest(manifest)
    required = tuple(sorted(policy.domain_required_gates.get(authorization_domain, BASE_AUTHORIZATION_GATES)))
    satisfied = _satisfied_auth_gates(manifest)
    missing = tuple(sorted(set(required) - set(satisfied)))
    contradictions = _source_contradictions(manifest)
    warnings = tuple(sorted(set(getattr(manifest, "warning_codes", ()) or ()) | set(contradictions)))
    blocked = _blocked_actions_for_manifest(manifest, authorization_domain)
    material = {"manifest": manifest.manifest_id, "digest": manifest.digest, "domain": authorization_domain, "required": required}
    return AuthorizationReviewPacket(
        packet_id=_digest_payload("arp_", material),
        source_execution_readiness_manifest_id=manifest.manifest_id,
        source_execution_readiness_manifest_digest=manifest.digest,
        effect_contract_id=manifest.effect_contract_id,
        future_effect_receipt_id=manifest.future_effect_receipt_id,
        postcondition_plan_id=manifest.postcondition_plan_id,
        rollback_plan_id=manifest.rollback_plan_id,
        runtime_supervisor_report_id=manifest.runtime_supervisor_report_id,
        effect_domain=manifest.effect_domain,
        backend_class=manifest.backend_class,
        readiness_status=manifest.readiness_status,
        packet_status=_packet_status(manifest.readiness_status, contradictions, missing),
        approval_class=policy.domain_approval_classes.get(authorization_domain, "operator_explicit_approval_required"),
        required_authorization_gates=required,
        satisfied_authorization_gates=satisfied,
        missing_authorization_gates=missing,
        blocked_actions=blocked,
        warning_codes=warnings,
        risk_codes=tuple(sorted(set(getattr(manifest, "risk_codes", ()) or ()))),
    )


def evaluate_authorization_review(packet: AuthorizationReviewPacket) -> AuthorizationReviewDecision:
    domain = _EFFECT_TO_AUTH_DOMAIN.get(packet.effect_domain, "diagnostics_authorization_review")
    reasons: list[str] = []
    if packet.packet_status.endswith("contradicted"):
        status = "authorization_review_contradicted"; reasons.append("source_readiness_or_packet_contradicted")
    elif packet.packet_status.endswith("incomplete"):
        status = "authorization_review_incomplete"; reasons.append("required_authorization_review_gates_missing")
    elif packet.packet_status.endswith("blocked"):
        status = "authorization_review_blocked"; reasons.append("source_readiness_blocked")
    elif packet.readiness_status.endswith("with_conditions") or packet.packet_status.endswith("with_conditions"):
        status = "authorization_review_eligible_with_conditions"; reasons.append("readiness_conditions_must_be_resolved_before_authorization")
    else:
        status = "authorization_review_eligible_for_operator_review"; reasons.append("ready_for_future_operator_policy_authorization_review")
    if packet.missing_authorization_gates and status.startswith("authorization_review_eligible"):
        status = "authorization_review_incomplete"
        reasons.append("missing_authorization_review_gates")
    material = {"packet": packet.packet_id, "status": status, "domain": domain, "missing": packet.missing_authorization_gates}
    return AuthorizationReviewDecision(
        decision_id=_digest_payload("ard_", material),
        packet_id=packet.packet_id,
        source_execution_readiness_manifest_id=packet.source_execution_readiness_manifest_id,
        source_execution_readiness_manifest_digest=packet.source_execution_readiness_manifest_digest,
        authorization_domain=domain,
        approval_class=packet.approval_class,
        decision_status=status,
        reason_codes=tuple(sorted(set(reasons))),
        warning_codes=packet.warning_codes,
        risk_codes=packet.risk_codes,
        required_authorization_gates=packet.required_authorization_gates,
        missing_authorization_gates=packet.missing_authorization_gates,
        blocked_actions=packet.blocked_actions,
    )


def _receipt_status(decision_status: str, warnings: Sequence[str]) -> str:
    if decision_status.endswith("contradicted"):
        return "authorization_review_receipt_contradicted"
    if decision_status.endswith("incomplete"):
        return "authorization_review_receipt_incomplete"
    if decision_status.endswith("blocked"):
        return "authorization_review_receipt_blocked"
    if warnings or decision_status.endswith("conditions"):
        return "authorization_review_receipt_recorded_with_warnings"
    return "authorization_review_receipt_recorded"


def build_authorization_review_receipt(decision: AuthorizationReviewDecision, *, created_at: str = "1970-01-01T00:00:00+00:00") -> AuthorizationReviewReceipt:
    evidence = (
        "authorization_review_only",
        "authorization_not_granted",
        "future_authorization_grant_required",
        "control_plane_admission_required_before_any_future_action",
    )
    provisional = AuthorizationReviewReceipt(
        receipt_id=_digest_payload("arr_", {"decision": decision.decision_id, "created_at": created_at}),
        decision_id=decision.decision_id,
        packet_id=decision.packet_id,
        source_execution_readiness_manifest_id=decision.source_execution_readiness_manifest_id,
        source_execution_readiness_manifest_digest=decision.source_execution_readiness_manifest_digest,
        authorization_domain=decision.authorization_domain,
        approval_class=decision.approval_class,
        decision_status=decision.decision_status,
        receipt_status=_receipt_status(decision.decision_status, decision.warning_codes),
        evidence_summary=evidence,
        required_authorization_gates=decision.required_authorization_gates,
        missing_authorization_gates=decision.missing_authorization_gates,
        blocked_actions=decision.blocked_actions,
        warning_codes=decision.warning_codes,
        risk_codes=decision.risk_codes,
        created_at=created_at,
        digest="",
    )
    return replace(provisional, digest=authorization_review_receipt_digest(provisional))


def _schema_status(receipt_status: str) -> str:
    if receipt_status.endswith("contradicted"):
        return "future_authorization_grant_schema_contradicted"
    if receipt_status.endswith("incomplete"):
        return "future_authorization_grant_schema_incomplete"
    if receipt_status.endswith("blocked"):
        return "future_authorization_grant_schema_blocked"
    if receipt_status.endswith("warnings"):
        return "future_authorization_grant_schema_ready_with_conditions"
    return "future_authorization_grant_schema_ready"


def build_future_authorization_grant_schema(receipt: AuthorizationReviewReceipt, *, created_at: str = "1970-01-01T00:00:00+00:00") -> FutureAuthorizationGrantSchema:
    domain = receipt.authorization_domain
    scope_labels = ["bounded_scope_required", domain]
    if domain == "future_cooling_authorization_review":
        scope_labels += ["hardware_allowlist_required", "cooling_bounds_required", "cooldown_policy_required"]
    if domain == "future_power_authorization_review":
        scope_labels += ["os_backend_required", "power_bounds_policy_required"]
    if domain == "future_cleanup_authorization_review":
        scope_labels += ["filesystem_scope_required", "path_scope_required", "dry_run_evidence_required"]
    if domain == "future_service_authorization_review":
        scope_labels += ["service_scope_required", "runtime_supervisor_observation_required"]
    provisional = FutureAuthorizationGrantSchema(
        schema_id=_digest_payload("fags_", {"receipt": receipt.receipt_id, "digest": receipt.digest, "created_at": created_at}),
        source_authorization_review_receipt_id=receipt.receipt_id,
        source_authorization_review_receipt_digest=receipt.digest,
        authorization_domain=domain,
        approval_class=receipt.approval_class,
        schema_status=_schema_status(receipt.receipt_status),
        required_authority_refs=("future_authorization_grant", "operator_or_policy_approval", "control_plane_admission"),
        required_operator_identity_labels=("operator_identity_required", "operator_presence_required"),
        required_policy_labels=("policy_label_required", receipt.approval_class),
        required_scope_labels=tuple(sorted(set(scope_labels))),
        required_time_bounds=("issued_at_required", "expires_at_required", "short_lived_authorization_required"),
        required_revocation_labels=("revocation_path_required", "panic_stop_required"),
        required_audit_labels=("audit_receipt_required", "immutable_trace_required"),
        required_control_plane_labels=("control_plane_admission_required", "admission_receipt_required"),
        blocked_actions=receipt.blocked_actions,
        warning_codes=receipt.warning_codes,
        risk_codes=receipt.risk_codes,
        created_at=created_at,
        digest="",
    )
    return replace(provisional, digest=future_authorization_grant_schema_digest(provisional))


def _validate_common(value: Any, prefix: str) -> list[str]:
    findings: list[str] = []
    forbidden_false = (
        "authorization_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed",
        "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed",
        "process_kill_performed", "service_restart_performed", "package_install_performed", "driver_install_performed",
        "file_cleanup_performed", "file_delete_performed", "provider_invocation_performed", "network_performed",
        "prompt_assembly_performed",
    )
    for flag in forbidden_false:
        if getattr(value, flag, False):
            findings.append(f"{prefix}_forbidden_flag:{flag}")
    for flag in ("metadata_only", "review_only", "schema_only", "future_use_only", "does_not_execute", "does_not_mutate_host", "does_not_authorize_fulfillment", "authorization_not_granted"):
        if hasattr(value, flag) and not getattr(value, flag):
            findings.append(f"{prefix}_missing_non_authority_flag:{flag}")
    return findings


def validate_authorization_review_packet(packet: AuthorizationReviewPacket) -> AuthorizationReviewValidationResult:
    findings = _validate_common(packet, "packet")
    if not packet.packet_id: findings.append("missing_packet_id")
    if packet.packet_status not in AUTHORIZATION_REVIEW_PACKET_STATUSES: findings.append("unknown_packet_status")
    if packet.approval_class not in APPROVAL_CLASSES: findings.append("unknown_approval_class")
    missing = tuple(sorted(set(packet.required_authorization_gates) - set(packet.satisfied_authorization_gates)))
    if missing != tuple(packet.missing_authorization_gates): findings.append("packet_missing_gate_mismatch")
    return AuthorizationReviewValidationResult(not findings, tuple(findings))


def validate_authorization_review_decision(decision: AuthorizationReviewDecision) -> AuthorizationReviewValidationResult:
    findings = _validate_common(decision, "decision")
    if decision.authorization_domain not in AUTHORIZATION_DOMAINS: findings.append("unknown_authorization_domain")
    if decision.approval_class not in APPROVAL_CLASSES: findings.append("unknown_approval_class")
    if decision.decision_status not in AUTHORIZATION_REVIEW_DECISION_STATUSES: findings.append("unknown_decision_status")
    return AuthorizationReviewValidationResult(not findings, tuple(findings))


def validate_authorization_review_receipt(receipt: AuthorizationReviewReceipt) -> AuthorizationReviewValidationResult:
    findings = _validate_common(receipt, "receipt")
    if receipt.receipt_status not in AUTHORIZATION_REVIEW_RECEIPT_STATUSES: findings.append("unknown_receipt_status")
    if not receipt.authorization_not_granted: findings.append("receipt_authorization_was_granted")
    if receipt.digest and receipt.digest != authorization_review_receipt_digest(receipt): findings.append("receipt_digest_mismatch")
    return AuthorizationReviewValidationResult(not findings, tuple(findings))


def validate_future_authorization_grant_schema(schema: FutureAuthorizationGrantSchema) -> AuthorizationReviewValidationResult:
    findings = _validate_common(schema, "future_schema")
    if schema.schema_status not in FUTURE_AUTHORIZATION_GRANT_SCHEMA_STATUSES: findings.append("unknown_schema_status")
    if not schema.schema_only or not schema.future_use_only: findings.append("future_schema_not_schema_only_future_use")
    if schema.digest and schema.digest != future_authorization_grant_schema_digest(schema): findings.append("future_schema_digest_mismatch")
    return AuthorizationReviewValidationResult(not findings, tuple(findings))


def summarize_authorization_review_packet(packet: AuthorizationReviewPacket) -> dict[str, Any]:
    return {"packet_id": packet.packet_id, "source_execution_readiness_manifest_id": packet.source_execution_readiness_manifest_id, "readiness_status": packet.readiness_status, "packet_status": packet.packet_status, "approval_class": packet.approval_class, "metadata_only": packet.metadata_only, "review_only": packet.review_only, "authorization_granted": packet.authorization_granted, "fulfillment_granted": packet.fulfillment_granted, "effect_performed": packet.effect_performed, "host_mutation_performed": packet.host_mutation_performed, "missing_authorization_gate_count": len(packet.missing_authorization_gates)}


def summarize_authorization_review_decision(decision: AuthorizationReviewDecision) -> dict[str, Any]:
    return {"decision_id": decision.decision_id, "packet_id": decision.packet_id, "authorization_domain": decision.authorization_domain, "approval_class": decision.approval_class, "decision_status": decision.decision_status, "metadata_only": decision.metadata_only, "review_only": decision.review_only, "authorization_granted": decision.authorization_granted, "fulfillment_granted": decision.fulfillment_granted, "effect_performed": decision.effect_performed, "host_mutation_performed": decision.host_mutation_performed, "missing_authorization_gate_count": len(decision.missing_authorization_gates)}


def summarize_authorization_review_receipt(receipt: AuthorizationReviewReceipt) -> dict[str, Any]:
    return {"receipt_id": receipt.receipt_id, "decision_id": receipt.decision_id, "authorization_domain": receipt.authorization_domain, "receipt_status": receipt.receipt_status, "review_only": receipt.review_only, "authorization_not_granted": receipt.authorization_not_granted, "does_not_execute": receipt.does_not_execute, "does_not_mutate_host": receipt.does_not_mutate_host, "does_not_authorize_fulfillment": receipt.does_not_authorize_fulfillment, "digest": receipt.digest}


def summarize_future_authorization_grant_schema(schema: FutureAuthorizationGrantSchema) -> dict[str, Any]:
    return {"schema_id": schema.schema_id, "source_authorization_review_receipt_id": schema.source_authorization_review_receipt_id, "authorization_domain": schema.authorization_domain, "schema_status": schema.schema_status, "schema_only": schema.schema_only, "future_use_only": schema.future_use_only, "authorization_granted": schema.authorization_granted, "does_not_execute": schema.does_not_execute, "does_not_mutate_host": schema.does_not_mutate_host, "does_not_authorize_fulfillment": schema.does_not_authorize_fulfillment, "digest": schema.digest}


def build_authorization_review_wing_for_execution_readiness(manifest: ExecutionReadinessManifest, *, policy: AuthorizationReviewPolicy | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> AuthorizationReviewWingRecords:
    packet = build_authorization_review_packet(manifest, policy=policy)
    decision = evaluate_authorization_review(packet)
    receipt = build_authorization_review_receipt(decision, created_at=created_at)
    schema = build_future_authorization_grant_schema(receipt, created_at=created_at)
    return AuthorizationReviewWingRecords(packet, decision, receipt, schema)
