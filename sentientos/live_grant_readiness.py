"""Metadata-only live-grant readiness/preflight records.

This wing evaluates whether future live authorization prerequisites are
structurally present after controlled authorization contracts and host actuation
safety gates. It never issues a grant, authorizes fulfillment, executes host
actions, opens network egress, invokes providers, assembles prompts, or mutates
host state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, NamedTuple, Sequence

READINESS_STATUSES = frozenset({
    "live_grant_readiness_ready_for_operator_policy_review",
    "live_grant_readiness_ready_with_conditions",
    "live_grant_readiness_blocked",
    "live_grant_readiness_incomplete",
    "live_grant_readiness_contradicted",
})
PREREQUISITE_STATUSES = frozenset({
    "prerequisite_satisfied",
    "prerequisite_satisfied_with_conditions",
    "prerequisite_missing",
    "prerequisite_blocked",
    "prerequisite_contradicted",
})
APPROVAL_PACKET_STATUSES = frozenset({
    "operator_policy_approval_packet_ready",
    "operator_policy_approval_packet_ready_with_conditions",
    "operator_policy_approval_packet_blocked",
    "operator_policy_approval_packet_incomplete",
    "operator_policy_approval_packet_contradicted",
})
PREFLIGHT_STATUSES = frozenset({
    "grant_issue_preflight_recorded",
    "grant_issue_preflight_recorded_with_warnings",
    "grant_issue_preflight_blocked",
    "grant_issue_preflight_incomplete",
    "grant_issue_preflight_contradicted",
})
DENIAL_DEFERRAL_STATUSES = frozenset({
    "grant_denial_deferral_recorded",
    "grant_denial_deferral_blocked",
    "grant_denial_deferral_incomplete",
    "grant_denial_deferral_contradicted",
})
READINESS_DOMAINS = frozenset({
    "diagnostics_live_grant_review",
    "operator_review_live_grant_review",
    "resource_pressure_live_grant_review",
    "thermal_safety_live_grant_review",
    "future_cooling_live_grant_review",
    "future_power_live_grant_review",
    "future_cleanup_live_grant_review",
    "future_service_live_grant_review",
})
REQUIRED_PREREQUISITE_LABELS = frozenset({
    "controlled_authorization_contract_present",
    "future_grant_schema_present",
    "controlled_grant_record_schema_present",
    "revocation_record_schema_present",
    "authorization_ledger_present",
    "safety_gate_satisfaction_manifest_present",
    "hardware_allowlist_present",
    "os_backend_declaration_present",
    "bounds_policy_present",
    "cooldown_policy_present",
    "panic_stop_contract_present",
    "scope_manifest_present",
    "operator_identity_labels_present",
    "policy_labels_present",
    "time_bounds_present",
    "expiry_present",
    "revocation_path_present",
    "control_plane_admission_required",
    "audit_receipt_required",
    "rollback_plan_required",
    "rollback_receipt_required",
    "effect_receipt_required",
    "postcondition_check_required",
    "runtime_supervisor_observation_required",
    "immutable_trace_required",
    "reviewer_proof_bundle_present",
})
BLOCKED_ACTION_LABELS = frozenset({
    "live_authorization_grant",
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

_GATE_TO_PREREQUISITE: Mapping[str, str] = {
    "hardware_allowlist_required": "hardware_allowlist_present",
    "hardware_allowlist_declared": "hardware_allowlist_present",
    "os_backend_declaration_required": "os_backend_declaration_present",
    "os_backend_declared": "os_backend_declaration_present",
    "bounds_policy_required": "bounds_policy_present",
    "bounds_policy_declared": "bounds_policy_present",
    "cooldown_policy_required": "cooldown_policy_present",
    "cooldown_policy_declared": "cooldown_policy_present",
    "panic_stop_required": "panic_stop_contract_present",
    "panic_stop_declared": "panic_stop_contract_present",
    "operator_identity_required": "operator_identity_labels_present",
    "policy_identity_required": "policy_labels_present",
    "explicit_scope_required": "scope_manifest_present",
    "target_scope_declared": "scope_manifest_present",
    "time_bounds_required": "time_bounds_present",
    "expiry_required": "expiry_present",
    "revocation_path_required": "revocation_path_present",
    "control_plane_admission_required": "control_plane_admission_required",
    "audit_receipt_required": "audit_receipt_required",
    "rollback_plan_required": "rollback_plan_required",
    "rollback_receipt_required": "rollback_receipt_required",
    "effect_receipt_required": "effect_receipt_required",
    "postcondition_check_required": "postcondition_check_required",
    "runtime_supervisor_observation_required": "runtime_supervisor_observation_required",
    "immutable_trace_required": "immutable_trace_required",
}
_COMMON_FUTURE = tuple(sorted(REQUIRED_PREREQUISITE_LABELS))
_DOMAIN_REQUIRED: Mapping[str, tuple[str, ...]] = {
    "diagnostics_live_grant_review": ("authorization_ledger_present", "safety_gate_satisfaction_manifest_present", "operator_identity_labels_present", "policy_labels_present", "audit_receipt_required", "immutable_trace_required"),
    "operator_review_live_grant_review": ("authorization_ledger_present", "safety_gate_satisfaction_manifest_present", "scope_manifest_present", "operator_identity_labels_present", "policy_labels_present", "audit_receipt_required", "immutable_trace_required", "reviewer_proof_bundle_present"),
    "resource_pressure_live_grant_review": ("authorization_ledger_present", "safety_gate_satisfaction_manifest_present", "bounds_policy_present", "operator_identity_labels_present", "policy_labels_present", "audit_receipt_required", "runtime_supervisor_observation_required", "immutable_trace_required", "reviewer_proof_bundle_present"),
    "thermal_safety_live_grant_review": ("authorization_ledger_present", "safety_gate_satisfaction_manifest_present", "os_backend_declaration_present", "bounds_policy_present", "panic_stop_contract_present", "operator_identity_labels_present", "policy_labels_present", "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required", "reviewer_proof_bundle_present"),
    "future_cooling_live_grant_review": _COMMON_FUTURE,
    "future_power_live_grant_review": tuple(label for label in _COMMON_FUTURE if label != "hardware_allowlist_present"),
    "future_cleanup_live_grant_review": tuple(label for label in _COMMON_FUTURE if label not in {"hardware_allowlist_present", "os_backend_declaration_present", "cooldown_policy_present", "runtime_supervisor_observation_required"}),
    "future_service_live_grant_review": tuple(label for label in _COMMON_FUTURE if label not in {"hardware_allowlist_present", "bounds_policy_present", "cooldown_policy_present"}),
}
_DOMAIN_BLOCKS: Mapping[str, tuple[str, ...]] = {
    "future_cooling_live_grant_review": ("fan_pwm_write", "thermal_actuation"),
    "future_power_live_grant_review": ("power_profile_mutation",),
    "future_cleanup_live_grant_review": ("file_cleanup", "file_delete"),
    "future_service_live_grant_review": ("service_restart", "process_kill"),
}
_FORBIDDEN_SOURCE_FLAGS = (
    "live_authorization_granted", "grants_live_authorization", "grants_control_authority",
    "fulfillment_granted", "effect_performed", "host_mutation_performed",
    "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed",
    "process_kill_performed", "service_restart_performed", "file_cleanup_performed",
    "file_delete_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed",
    "control_authority_granted", "does_execute", "does_mutate_host",
)

@dataclass(frozen=True)
class LiveGrantReadinessPolicy:
    policy_id: str
    domain_required_prerequisites: Mapping[str, tuple[str, ...]]
    blocked_actions: tuple[str, ...]
    proof_bundle_required: bool = True
    metadata_only: bool = True
    readiness_only: bool = True
    grants_live_authorization: bool = False

@dataclass(frozen=True)
class LiveGrantPrerequisite:
    prerequisite_id: str
    label: str
    status: str
    evidence_labels: tuple[str, ...]
    missing_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    prerequisite_only: bool = True
    grants_live_authorization: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class LiveGrantPrerequisiteMatrix:
    matrix_id: str
    source_controlled_authorization_ledger_id: str | None
    source_safety_gate_manifest_id: str | None
    source_reviewer_proof_bundle_manifest_id: str | None
    readiness_domain: str
    prerequisites: tuple[LiveGrantPrerequisite, ...]
    satisfied_labels: tuple[str, ...]
    missing_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    matrix_only: bool = True
    grants_live_authorization: bool = False
    fulfillment_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class OperatorPolicyApprovalPacket:
    packet_id: str
    source_prerequisite_matrix_id: str
    readiness_domain: str
    approval_packet_status: str
    required_operator_labels: tuple[str, ...]
    required_policy_labels: tuple[str, ...]
    required_scope_labels: tuple[str, ...]
    required_time_bounds: tuple[str, ...]
    required_expiry_labels: tuple[str, ...]
    required_revocation_labels: tuple[str, ...]
    required_audit_labels: tuple[str, ...]
    required_control_plane_labels: tuple[str, ...]
    missing_approval_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    approval_packet_only: bool = True
    approval_not_granted: bool = True
    grants_live_authorization: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class GrantIssuePreflightReceipt:
    receipt_id: str
    source_prerequisite_matrix_id: str
    source_approval_packet_id: str
    readiness_domain: str
    readiness_status: str
    preflight_status: str
    evidence_summary: Mapping[str, Any]
    satisfied_prerequisites: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    preflight_only: bool = True
    grant_not_issued: bool = True
    live_authorization_granted: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class GrantDenialDeferralReceipt:
    receipt_id: str
    source_preflight_receipt_id: str
    readiness_domain: str
    denial_deferral_status: str
    denial_reason_codes: tuple[str, ...]
    deferral_reason_codes: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    denial_deferral_only: bool = True
    grant_not_issued: bool = True
    live_authorization_granted: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class LiveGrantReadinessValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()

class LiveGrantReadinessWingRecords(NamedTuple):
    prerequisite_matrix: LiveGrantPrerequisiteMatrix
    approval_packet: OperatorPolicyApprovalPacket
    preflight_receipt: GrantIssuePreflightReceipt
    denial_deferral_receipt: GrantDenialDeferralReceipt

def _tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))

def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)

def _payload(record_or_payload: Any) -> dict[str, Any]:
    payload = record_or_payload.to_dict() if hasattr(record_or_payload, "to_dict") else dict(record_or_payload)
    payload["digest"] = ""
    return payload

def live_grant_readiness_digest(record_or_payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(_payload(record_or_payload)).encode("utf-8")).hexdigest()

def live_grant_prerequisite_digest(record_or_payload: Any) -> str:
    return live_grant_readiness_digest(record_or_payload)

def live_grant_prerequisite_matrix_digest(record_or_payload: Any) -> str:
    return live_grant_readiness_digest(record_or_payload)

def operator_policy_approval_packet_digest(record_or_payload: Any) -> str:
    return live_grant_readiness_digest(record_or_payload)

def grant_issue_preflight_receipt_digest(record_or_payload: Any) -> str:
    return live_grant_readiness_digest(record_or_payload)

def grant_denial_deferral_receipt_digest(record_or_payload: Any) -> str:
    return live_grant_readiness_digest(record_or_payload)

def build_default_live_grant_readiness_policy() -> LiveGrantReadinessPolicy:
    return LiveGrantReadinessPolicy(
        policy_id="live-grant-readiness-policy-v1",
        domain_required_prerequisites=_DOMAIN_REQUIRED,
        blocked_actions=tuple(sorted(BLOCKED_ACTION_LABELS)),
    )

def _source_payload(source: Any | None) -> Mapping[str, Any]:
    if source is None:
        return {}
    return source.to_dict() if hasattr(source, "to_dict") else dict(source)

def _source_contradictions(*sources: Any | None) -> tuple[str, ...]:
    findings: list[str] = []
    for name, source in zip(("controlled_authorization_ledger", "safety_gate_manifest", "reviewer_proof_bundle_manifest"), sources):
        payload = _source_payload(source)
        for flag in _FORBIDDEN_SOURCE_FLAGS:
            if payload.get(flag, False):
                findings.append(f"{name}_forbidden_flag:{flag}")
    return tuple(findings)

def _evidence_from_sources(controlled_authorization_ledger: Any | None, safety_gate_manifest: Any | None, reviewer_proof_bundle_manifest: Any | None) -> set[str]:
    evidence: set[str] = set()
    ledger = _source_payload(controlled_authorization_ledger)
    if ledger:
        evidence.add("authorization_ledger_present")
        if ledger.get("grant_records"):
            evidence.update({"controlled_authorization_contract_present", "future_grant_schema_present", "controlled_grant_record_schema_present"})
        if ledger.get("revocation_records"):
            evidence.add("revocation_record_schema_present")
    manifest = _source_payload(safety_gate_manifest)
    if manifest:
        evidence.add("safety_gate_satisfaction_manifest_present")
        if manifest.get("hardware_allowlist_manifest_id"): evidence.add("hardware_allowlist_present")
        if manifest.get("os_backend_declaration_id"): evidence.add("os_backend_declaration_present")
        if manifest.get("bounds_policy_id"): evidence.add("bounds_policy_present")
        if manifest.get("cooldown_policy_id"): evidence.add("cooldown_policy_present")
        if manifest.get("panic_stop_contract_id"): evidence.add("panic_stop_contract_present")
        if manifest.get("host_action_scope_manifest_id"): evidence.add("scope_manifest_present")
        for gate in tuple(manifest.get("satisfied_gate_labels", ()) or ()): evidence.add(_GATE_TO_PREREQUISITE.get(str(gate), str(gate)))
    if reviewer_proof_bundle_manifest is not None:
        evidence.add("reviewer_proof_bundle_present")
    return evidence

def _blocked_actions_for_domain(domain: str, safety_gate_manifest: Any | None = None) -> tuple[str, ...]:
    blocked = set(BLOCKED_ACTION_LABELS)
    blocked.update(_DOMAIN_BLOCKS.get(domain, ()))
    blocked.update(tuple(_source_payload(safety_gate_manifest).get("blocked_actions", ()) or ()))
    return tuple(sorted(blocked))

def _build_prerequisite(label: str, evidence: set[str], contradicted: bool, *, created_at: str) -> LiveGrantPrerequisite:
    status = "prerequisite_contradicted" if contradicted else "prerequisite_satisfied" if label in evidence else "prerequisite_missing"
    provisional = LiveGrantPrerequisite(
        prerequisite_id=f"live-grant-prerequisite-{label}",
        label=label,
        status=status,
        evidence_labels=(label,) if label in evidence else (),
        missing_labels=() if label in evidence else (label,),
        warning_codes=(),
        risk_codes=("live_grant_readiness_is_not_authorization",),
    )
    return replace(provisional, prerequisite_id="lgp_" + hashlib.sha256((label + status + created_at).encode("utf-8")).hexdigest()[:16])

def build_live_grant_prerequisite_matrix(
    readiness_domain: str,
    *,
    controlled_authorization_ledger: Any | None = None,
    safety_gate_manifest: Any | None = None,
    reviewer_proof_bundle_manifest: Any | None = None,
    policy: LiveGrantReadinessPolicy | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> LiveGrantPrerequisiteMatrix:
    if readiness_domain not in READINESS_DOMAINS:
        raise ValueError(f"unknown readiness domain: {readiness_domain}")
    policy = policy or build_default_live_grant_readiness_policy()
    required = tuple(policy.domain_required_prerequisites.get(readiness_domain, ()))
    evidence = _evidence_from_sources(controlled_authorization_ledger, safety_gate_manifest, reviewer_proof_bundle_manifest)
    contradictions = _source_contradictions(controlled_authorization_ledger, safety_gate_manifest, reviewer_proof_bundle_manifest)
    prereqs = tuple(_build_prerequisite(label, evidence, bool(contradictions), created_at=created_at) for label in required)
    missing = tuple(sorted({label for prereq in prereqs for label in prereq.missing_labels}))
    satisfied = tuple(sorted({prereq.label for prereq in prereqs if prereq.status.startswith("prerequisite_satisfied")}))
    warnings = tuple(sorted(set(_tuple(_source_payload(controlled_authorization_ledger).get("warning_codes")) + _tuple(_source_payload(safety_gate_manifest).get("warning_codes")) + _tuple(_source_payload(reviewer_proof_bundle_manifest).get("warning_codes")))))
    risks = tuple(sorted(set(_tuple(_source_payload(controlled_authorization_ledger).get("risk_codes")) + _tuple(_source_payload(safety_gate_manifest).get("risk_codes")) + _tuple(_source_payload(reviewer_proof_bundle_manifest).get("risk_codes")) + contradictions + ("live_grant_readiness_preflight_only",))))
    if reviewer_proof_bundle_manifest is None and policy.proof_bundle_required and "reviewer_proof_bundle_present" in required:
        warnings = tuple(sorted(set(warnings) | {"reviewer_proof_bundle_manifest_missing"}))
    provisional = LiveGrantPrerequisiteMatrix(
        matrix_id="",
        source_controlled_authorization_ledger_id=_source_payload(controlled_authorization_ledger).get("ledger_id"),
        source_safety_gate_manifest_id=_source_payload(safety_gate_manifest).get("manifest_id"),
        source_reviewer_proof_bundle_manifest_id=_source_payload(reviewer_proof_bundle_manifest).get("manifest_id"),
        readiness_domain=readiness_domain,
        prerequisites=prereqs,
        satisfied_labels=satisfied,
        missing_labels=missing,
        blocked_actions=_blocked_actions_for_domain(readiness_domain, safety_gate_manifest),
        warning_codes=warnings,
        risk_codes=risks,
        created_at=created_at,
        digest="",
    )
    with_id = replace(provisional, matrix_id="lgrm_" + hashlib.sha256(_canonical_json(_payload(provisional)).encode("utf-8")).hexdigest()[:16])
    return replace(with_id, digest=live_grant_prerequisite_matrix_digest(with_id))

def build_operator_policy_approval_packet(matrix: LiveGrantPrerequisiteMatrix, *, created_at: str | None = None) -> OperatorPolicyApprovalPacket:
    missing = set(matrix.missing_labels)
    if any("forbidden_flag" in risk for risk in matrix.risk_codes): status = "operator_policy_approval_packet_contradicted"
    elif missing: status = "operator_policy_approval_packet_incomplete"
    elif matrix.warning_codes: status = "operator_policy_approval_packet_ready_with_conditions"
    else: status = "operator_policy_approval_packet_ready"
    provisional = OperatorPolicyApprovalPacket(
        packet_id="",
        source_prerequisite_matrix_id=matrix.matrix_id,
        readiness_domain=matrix.readiness_domain,
        approval_packet_status=status,
        required_operator_labels=("operator_identity_labels_present",),
        required_policy_labels=("policy_labels_present",),
        required_scope_labels=("scope_manifest_present",),
        required_time_bounds=("time_bounds_present",),
        required_expiry_labels=("expiry_present",),
        required_revocation_labels=("revocation_path_present",),
        required_audit_labels=("audit_receipt_required", "immutable_trace_required"),
        required_control_plane_labels=("control_plane_admission_required",),
        missing_approval_labels=tuple(sorted(label for label in missing if label in {"operator_identity_labels_present", "policy_labels_present", "scope_manifest_present", "time_bounds_present", "expiry_present", "revocation_path_present", "audit_receipt_required", "immutable_trace_required", "control_plane_admission_required"})),
        blocked_actions=matrix.blocked_actions,
        warning_codes=matrix.warning_codes,
        risk_codes=tuple(sorted(set(matrix.risk_codes) | {"approval_packet_is_not_approval"})),
        created_at=created_at or matrix.created_at,
        digest="",
    )
    with_id = replace(provisional, packet_id="lgap_" + hashlib.sha256(_canonical_json(_payload(provisional)).encode("utf-8")).hexdigest()[:16])
    return replace(with_id, digest=operator_policy_approval_packet_digest(with_id))

def _readiness_status(matrix: LiveGrantPrerequisiteMatrix) -> str:
    if any("forbidden_flag" in risk for risk in matrix.risk_codes): return "live_grant_readiness_contradicted"
    if any(prereq.status == "prerequisite_blocked" for prereq in matrix.prerequisites): return "live_grant_readiness_blocked"
    if matrix.missing_labels: return "live_grant_readiness_incomplete"
    if matrix.warning_codes: return "live_grant_readiness_ready_with_conditions"
    return "live_grant_readiness_ready_for_operator_policy_review"

def build_grant_issue_preflight_receipt(matrix: LiveGrantPrerequisiteMatrix, approval_packet: OperatorPolicyApprovalPacket, *, created_at: str | None = None) -> GrantIssuePreflightReceipt:
    readiness = _readiness_status(matrix)
    preflight = {
        "live_grant_readiness_ready_for_operator_policy_review": "grant_issue_preflight_recorded",
        "live_grant_readiness_ready_with_conditions": "grant_issue_preflight_recorded_with_warnings",
        "live_grant_readiness_blocked": "grant_issue_preflight_blocked",
        "live_grant_readiness_incomplete": "grant_issue_preflight_incomplete",
        "live_grant_readiness_contradicted": "grant_issue_preflight_contradicted",
    }[readiness]
    provisional = GrantIssuePreflightReceipt(
        receipt_id="",
        source_prerequisite_matrix_id=matrix.matrix_id,
        source_approval_packet_id=approval_packet.packet_id,
        readiness_domain=matrix.readiness_domain,
        readiness_status=readiness,
        preflight_status=preflight,
        evidence_summary={"satisfied_count": len(matrix.satisfied_labels), "missing_count": len(matrix.missing_labels), "metadata_only": True, "grant_not_issued": True},
        satisfied_prerequisites=matrix.satisfied_labels,
        missing_prerequisites=matrix.missing_labels,
        blocked_actions=matrix.blocked_actions,
        warning_codes=matrix.warning_codes,
        risk_codes=tuple(sorted(set(matrix.risk_codes) | {"preflight_receipt_does_not_issue_grant"})),
        created_at=created_at or matrix.created_at,
        digest="",
    )
    with_id = replace(provisional, receipt_id="lgpr_" + hashlib.sha256(_canonical_json(_payload(provisional)).encode("utf-8")).hexdigest()[:16])
    return replace(with_id, digest=grant_issue_preflight_receipt_digest(with_id))

def build_grant_denial_deferral_receipt(preflight_receipt: GrantIssuePreflightReceipt, *, created_at: str | None = None) -> GrantDenialDeferralReceipt:
    if preflight_receipt.preflight_status.endswith("contradicted"):
        status = "grant_denial_deferral_contradicted"
    elif preflight_receipt.preflight_status.endswith("blocked"):
        status = "grant_denial_deferral_blocked"
    elif preflight_receipt.missing_prerequisites:
        status = "grant_denial_deferral_incomplete"
    else:
        status = "grant_denial_deferral_recorded"
    denial = ("live_grant_not_issued_by_readiness_wing",)
    deferral = tuple(sorted(set(preflight_receipt.missing_prerequisites) | {"future_authorization_review_required"}))
    provisional = GrantDenialDeferralReceipt(
        receipt_id="",
        source_preflight_receipt_id=preflight_receipt.receipt_id,
        readiness_domain=preflight_receipt.readiness_domain,
        denial_deferral_status=status,
        denial_reason_codes=denial,
        deferral_reason_codes=deferral,
        missing_prerequisites=preflight_receipt.missing_prerequisites,
        blocked_actions=preflight_receipt.blocked_actions,
        warning_codes=preflight_receipt.warning_codes,
        risk_codes=tuple(sorted(set(preflight_receipt.risk_codes) | {"denial_deferral_receipt_does_not_mutate_host"})),
        created_at=created_at or preflight_receipt.created_at,
        digest="",
    )
    with_id = replace(provisional, receipt_id="lgdd_" + hashlib.sha256(_canonical_json(_payload(provisional)).encode("utf-8")).hexdigest()[:16])
    return replace(with_id, digest=grant_denial_deferral_receipt_digest(with_id))

def _validate_record_flags(payload: Mapping[str, Any], prefix: str) -> list[str]:
    findings: list[str] = []
    for flag in ("grants_live_authorization", "live_authorization_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed"):
        if payload.get(flag, False): findings.append(f"{prefix}forbidden_flag:{flag}")
    for flag in ("metadata_only", "does_not_execute", "does_not_mutate_host", "grant_not_issued", "approval_not_granted"):
        if flag in payload and not payload.get(flag): findings.append(f"{prefix}missing_non_authority_flag:{flag}")
    blocked = set(payload.get("blocked_actions", ()) or ())
    if "blocked_actions" in payload and not {"live_authorization_grant", "host_mutation", "provider_invocation", "network_egress", "prompt_assembly"}.issubset(blocked):
        findings.append(f"{prefix}missing_core_blocked_actions")
    return findings

def validate_live_grant_prerequisite(prerequisite: LiveGrantPrerequisite | Mapping[str, Any]) -> LiveGrantReadinessValidationResult:
    payload = prerequisite.to_dict() if isinstance(prerequisite, LiveGrantPrerequisite) else dict(prerequisite)
    findings = _validate_record_flags(payload, "prerequisite:")
    if payload.get("status") not in PREREQUISITE_STATUSES: findings.append("prerequisite:unknown_status")
    if not payload.get("prerequisite_only", False): findings.append("prerequisite:not_prerequisite_only")
    return LiveGrantReadinessValidationResult(not findings, tuple(findings))

def validate_live_grant_prerequisite_matrix(matrix: LiveGrantPrerequisiteMatrix | Mapping[str, Any]) -> LiveGrantReadinessValidationResult:
    payload = matrix.to_dict() if isinstance(matrix, LiveGrantPrerequisiteMatrix) else dict(matrix)
    findings = _validate_record_flags(payload, "matrix:")
    if payload.get("readiness_domain") not in READINESS_DOMAINS: findings.append("matrix:unknown_readiness_domain")
    if not payload.get("matrix_only", False): findings.append("matrix:not_matrix_only")
    for prereq in payload.get("prerequisites", ()) or ():
        findings.extend(f"matrix:{finding}" for finding in validate_live_grant_prerequisite(prereq).findings)
    if payload.get("digest") and payload.get("digest") != live_grant_prerequisite_matrix_digest(payload): findings.append("matrix:digest_mismatch")
    return LiveGrantReadinessValidationResult(not findings, tuple(findings))

def validate_operator_policy_approval_packet(packet: OperatorPolicyApprovalPacket | Mapping[str, Any]) -> LiveGrantReadinessValidationResult:
    payload = packet.to_dict() if isinstance(packet, OperatorPolicyApprovalPacket) else dict(packet)
    findings = _validate_record_flags(payload, "approval_packet:")
    if payload.get("approval_packet_status") not in APPROVAL_PACKET_STATUSES: findings.append("approval_packet:unknown_status")
    if not payload.get("approval_packet_only", False): findings.append("approval_packet:not_packet_only")
    if not payload.get("approval_not_granted", False): findings.append("approval_packet:approval_was_granted")
    if payload.get("digest") and payload.get("digest") != operator_policy_approval_packet_digest(payload): findings.append("approval_packet:digest_mismatch")
    return LiveGrantReadinessValidationResult(not findings, tuple(findings))

def validate_grant_issue_preflight_receipt(receipt: GrantIssuePreflightReceipt | Mapping[str, Any]) -> LiveGrantReadinessValidationResult:
    payload = receipt.to_dict() if isinstance(receipt, GrantIssuePreflightReceipt) else dict(receipt)
    findings = _validate_record_flags(payload, "preflight_receipt:")
    if payload.get("readiness_status") not in READINESS_STATUSES: findings.append("preflight_receipt:unknown_readiness_status")
    if payload.get("preflight_status") not in PREFLIGHT_STATUSES: findings.append("preflight_receipt:unknown_preflight_status")
    if not payload.get("preflight_only", False): findings.append("preflight_receipt:not_preflight_only")
    if not payload.get("grant_not_issued", False): findings.append("preflight_receipt:grant_was_issued")
    if payload.get("digest") and payload.get("digest") != grant_issue_preflight_receipt_digest(payload): findings.append("preflight_receipt:digest_mismatch")
    return LiveGrantReadinessValidationResult(not findings, tuple(findings))

def validate_grant_denial_deferral_receipt(receipt: GrantDenialDeferralReceipt | Mapping[str, Any]) -> LiveGrantReadinessValidationResult:
    payload = receipt.to_dict() if isinstance(receipt, GrantDenialDeferralReceipt) else dict(receipt)
    findings = _validate_record_flags(payload, "denial_deferral_receipt:")
    if payload.get("denial_deferral_status") not in DENIAL_DEFERRAL_STATUSES: findings.append("denial_deferral_receipt:unknown_status")
    if not payload.get("denial_deferral_only", False): findings.append("denial_deferral_receipt:not_denial_deferral_only")
    if not payload.get("grant_not_issued", False): findings.append("denial_deferral_receipt:grant_was_issued")
    if payload.get("digest") and payload.get("digest") != grant_denial_deferral_receipt_digest(payload): findings.append("denial_deferral_receipt:digest_mismatch")
    return LiveGrantReadinessValidationResult(not findings, tuple(findings))

def summarize_live_grant_prerequisite_matrix(matrix: LiveGrantPrerequisiteMatrix | Mapping[str, Any]) -> dict[str, Any]:
    p = matrix.to_dict() if isinstance(matrix, LiveGrantPrerequisiteMatrix) else dict(matrix)
    return {"matrix_id": p.get("matrix_id"), "readiness_domain": p.get("readiness_domain"), "satisfied_count": len(p.get("satisfied_labels", ()) or ()), "missing_count": len(p.get("missing_labels", ()) or ()), "blocked_actions": tuple(p.get("blocked_actions", ()) or ()), "metadata_only": p.get("metadata_only"), "matrix_only": p.get("matrix_only"), "grants_live_authorization": p.get("grants_live_authorization"), "fulfillment_granted": p.get("fulfillment_granted"), "effect_performed": p.get("effect_performed"), "host_mutation_performed": p.get("host_mutation_performed"), "digest": p.get("digest")}

def summarize_operator_policy_approval_packet(packet: OperatorPolicyApprovalPacket | Mapping[str, Any]) -> dict[str, Any]:
    p = packet.to_dict() if isinstance(packet, OperatorPolicyApprovalPacket) else dict(packet)
    return {"packet_id": p.get("packet_id"), "readiness_domain": p.get("readiness_domain"), "approval_packet_status": p.get("approval_packet_status"), "missing_approval_labels": tuple(p.get("missing_approval_labels", ()) or ()), "metadata_only": p.get("metadata_only"), "approval_packet_only": p.get("approval_packet_only"), "approval_not_granted": p.get("approval_not_granted"), "grants_live_authorization": p.get("grants_live_authorization"), "does_not_execute": p.get("does_not_execute"), "does_not_mutate_host": p.get("does_not_mutate_host"), "digest": p.get("digest")}

def summarize_grant_issue_preflight_receipt(receipt: GrantIssuePreflightReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = receipt.to_dict() if isinstance(receipt, GrantIssuePreflightReceipt) else dict(receipt)
    return {"receipt_id": p.get("receipt_id"), "readiness_domain": p.get("readiness_domain"), "readiness_status": p.get("readiness_status"), "preflight_status": p.get("preflight_status"), "missing_count": len(p.get("missing_prerequisites", ()) or ()), "metadata_only": p.get("metadata_only"), "preflight_only": p.get("preflight_only"), "grant_not_issued": p.get("grant_not_issued"), "live_authorization_granted": p.get("live_authorization_granted"), "does_not_execute": p.get("does_not_execute"), "does_not_mutate_host": p.get("does_not_mutate_host"), "digest": p.get("digest")}

def summarize_grant_denial_deferral_receipt(receipt: GrantDenialDeferralReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = receipt.to_dict() if isinstance(receipt, GrantDenialDeferralReceipt) else dict(receipt)
    return {"receipt_id": p.get("receipt_id"), "readiness_domain": p.get("readiness_domain"), "denial_deferral_status": p.get("denial_deferral_status"), "missing_count": len(p.get("missing_prerequisites", ()) or ()), "metadata_only": p.get("metadata_only"), "denial_deferral_only": p.get("denial_deferral_only"), "grant_not_issued": p.get("grant_not_issued"), "live_authorization_granted": p.get("live_authorization_granted"), "does_not_execute": p.get("does_not_execute"), "does_not_mutate_host": p.get("does_not_mutate_host"), "digest": p.get("digest")}

def build_live_grant_readiness_wing(
    controlled_authorization_ledger: Any | None,
    safety_gate_satisfaction_manifest: Any | None,
    reviewer_proof_bundle_manifest: Any | None = None,
    *,
    readiness_domain: str = "future_cooling_live_grant_review",
    policy: LiveGrantReadinessPolicy | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> LiveGrantReadinessWingRecords:
    matrix = build_live_grant_prerequisite_matrix(readiness_domain, controlled_authorization_ledger=controlled_authorization_ledger, safety_gate_manifest=safety_gate_satisfaction_manifest, reviewer_proof_bundle_manifest=reviewer_proof_bundle_manifest, policy=policy, created_at=created_at)
    packet = build_operator_policy_approval_packet(matrix, created_at=created_at)
    preflight = build_grant_issue_preflight_receipt(matrix, packet, created_at=created_at)
    denial = build_grant_denial_deferral_receipt(preflight, created_at=created_at)
    return LiveGrantReadinessWingRecords(matrix, packet, preflight, denial)
