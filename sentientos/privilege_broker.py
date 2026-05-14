"""Eligibility-only Privilege Broker for SentientOS host embodiment Phase 4.

This module classifies proposal receipts for future privileged-action review. It
is metadata-only: it never admits, authorizes, fulfills, executes, mutates host
state, writes fan/PWM controls, changes thermal or power settings, kills
processes, restarts services, installs packages or drivers, performs network
activity, invokes providers, or assembles prompts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence

from sentientos.host_resource_policy import (
    BLOCKED_HOST_ACTIONS,
    FUTURE_ACTION_GATES,
    HOST_RESOURCE_PROPOSAL_STATUSES,
    host_resource_proposal_receipt_digest,
    validate_host_resource_proposal_receipt,
)

PRIVILEGE_BROKER_ELIGIBILITY_STATUSES = frozenset(
    {
        "privilege_broker_eligible_for_future_review",
        "privilege_broker_eligible_with_conditions",
        "privilege_broker_blocked",
        "privilege_broker_incomplete",
        "privilege_broker_contradicted",
    }
)
PRIVILEGE_BROKER_REVIEW_STATUSES = frozenset(
    {
        "privilege_broker_receipt_recorded",
        "privilege_broker_receipt_recorded_with_warnings",
        "privilege_broker_receipt_blocked",
        "privilege_broker_receipt_incomplete",
        "privilege_broker_receipt_contradicted",
    }
)
PRIVILEGE_DOMAINS = frozenset(
    {
        "diagnostics_only",
        "operator_review",
        "resource_pressure_review",
        "service_health_review",
        "thermal_safety_review",
        "disk_safety_review",
        "future_power_policy_review",
        "future_cooling_policy_review",
        "future_cleanup_policy_review",
        "future_actuation_fulfillment_review",
    }
)
REQUIRED_FUTURE_GATES = (
    "control_plane_admission_required",
    "operator_or_policy_approval_required",
    "audit_receipt_required",
    "rollback_receipt_required",
    "panic_stop_required",
    "hardware_allowlist_required",
    "os_backend_declaration_required",
    "bounds_policy_required",
    "cooldown_policy_required",
    "rehearsal_required",
    "fulfillment_layer_required",
)
BASE_FUTURE_GATES = (
    "control_plane_admission_required",
    "operator_or_policy_approval_required",
    "audit_receipt_required",
    "rollback_receipt_required",
)
REHEARSAL_FULFILLMENT_GATES = BASE_FUTURE_GATES + ("rehearsal_required", "fulfillment_layer_required")
COOLING_POLICY_GATES = (
    "hardware_allowlist_required",
    "os_backend_declaration_required",
    "bounds_policy_required",
    "cooldown_policy_required",
    "panic_stop_required",
    "control_plane_admission_required",
    "operator_or_policy_approval_required",
    "audit_receipt_required",
    "rollback_receipt_required",
    "rehearsal_required",
    "fulfillment_layer_required",
)
POWER_POLICY_GATES = (
    "os_backend_declaration_required",
    "bounds_policy_required",
    "operator_or_policy_approval_required",
    "control_plane_admission_required",
    "audit_receipt_required",
    "rollback_receipt_required",
    "rehearsal_required",
    "fulfillment_layer_required",
)
CLEANUP_POLICY_GATES = (
    "rehearsal_required",
    "file_path_scope_declaration_required",
    "operator_or_policy_approval_required",
    "audit_receipt_required",
    "rollback_receipt_required",
    "fulfillment_layer_required",
)
SERVICE_HEALTH_GATES = BASE_FUTURE_GATES + ("rehearsal_required", "fulfillment_layer_required")

_KIND_TO_DOMAIN: Mapping[str, str] = {
    "inspect_cpu_pressure_candidate": "resource_pressure_review",
    "inspect_memory_pressure_candidate": "resource_pressure_review",
    "inspect_gpu_pressure_candidate": "resource_pressure_review",
    "inspect_disk_pressure_candidate": "disk_safety_review",
    "inspect_thermal_state_candidate": "thermal_safety_review",
    "inspect_service_health_candidate": "service_health_review",
    "request_operator_review_candidate": "operator_review",
    "reduce_model_load_candidate": "resource_pressure_review",
    "defer_heavy_task_candidate": "resource_pressure_review",
    "future_cooling_policy_candidate": "future_cooling_policy_review",
    "future_power_policy_candidate": "future_power_policy_review",
    "future_cleanup_policy_candidate": "future_cleanup_policy_review",
}
_KIND_TO_GATES: Mapping[str, tuple[str, ...]] = {
    "future_cooling_policy_candidate": COOLING_POLICY_GATES,
    "future_power_policy_candidate": POWER_POLICY_GATES,
    "future_cleanup_policy_candidate": CLEANUP_POLICY_GATES,
    "inspect_service_health_candidate": SERVICE_HEALTH_GATES,
}
_KIND_TO_BLOCKED_ACTIONS: Mapping[str, tuple[str, ...]] = {
    "future_cooling_policy_candidate": ("fan_pwm_write", "thermal_actuation", "power_profile_mutation"),
    "future_power_policy_candidate": ("power_profile_mutation",),
    "future_cleanup_policy_candidate": ("file_delete", "disk_cleanup_mutation"),
    "inspect_service_health_candidate": ("service_restart",),
}
_CONTRADICTORY_RECEIPT_STATUSES = frozenset({"host_resource_proposal_contradicted"})
_INCOMPLETE_RECEIPT_STATUSES = frozenset({"host_resource_proposal_incomplete"})
_BLOCKED_RECEIPT_STATUSES = frozenset({"host_resource_proposal_blocked"})
_RECORDED_RECEIPT_STATUSES = frozenset({"host_resource_proposal_recorded", "host_resource_proposal_recorded_with_warnings"})


@dataclass(frozen=True)
class PrivilegeBrokerPolicy:
    policy_id: str
    inspect_kinds_eligible: tuple[str, ...]
    conditional_future_kinds: tuple[str, ...]
    required_receipt_gates: tuple[str, ...] = FUTURE_ACTION_GATES
    required_blocked_actions: tuple[str, ...] = BLOCKED_HOST_ACTIONS
    metadata_only: bool = True
    eligibility_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PrivilegeBrokerEligibilityDecision:
    decision_id: str
    source_receipt_id: str
    source_receipt_digest: str
    source_proposal_kind: str
    proposal_status: str
    proposal_scope: str
    pressure_labels: tuple[str, ...]
    privilege_domain: str
    eligibility_status: str
    reason_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    required_future_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    metadata_only: bool = True
    eligibility_only: bool = True
    authorization_granted: bool = False
    fulfillment_granted: bool = False
    host_mutation_performed: bool = False
    fan_pwm_write_performed: bool = False
    thermal_actuation_performed: bool = False
    process_kill_performed: bool = False
    service_restart_performed: bool = False
    package_install_performed: bool = False
    driver_install_performed: bool = False
    provider_invocation_performed: bool = False
    network_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PrivilegeBrokerReviewReceipt:
    receipt_id: str
    decision_id: str
    source_receipt_id: str
    source_receipt_digest: str
    privilege_domain: str
    eligibility_status: str
    review_status: str
    evidence_summary: tuple[str, ...]
    required_future_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str = ""
    review_only: bool = True
    eligibility_only: bool = True
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    does_not_authorize_fulfillment: bool = True
    requires_control_plane_admission_for_future_action: bool = True
    requires_operator_or_policy_approval_for_future_action: bool = True
    requires_audit_receipt_for_future_action: bool = True
    requires_rollback_receipt_for_future_action: bool = True
    requires_actuation_fulfillment_layer_for_future_action: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PrivilegeBrokerValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest_payload(prefix: str, payload: Mapping[str, Any], length: int = 24) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:length]


def _tuple_str(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _merge_unique(*groups: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({str(item) for group in groups for item in group}))


def build_default_privilege_broker_policy() -> PrivilegeBrokerPolicy:
    inspect = tuple(sorted(kind for kind in _KIND_TO_DOMAIN if kind.startswith("inspect_") or kind in {"request_operator_review_candidate", "reduce_model_load_candidate", "defer_heavy_task_candidate"}))
    conditional = ("future_cleanup_policy_candidate", "future_cooling_policy_candidate", "future_power_policy_candidate")
    material = {"inspect": inspect, "conditional": conditional, "required_receipt_gates": FUTURE_ACTION_GATES}
    return PrivilegeBrokerPolicy(policy_id=_digest_payload("pbp_", material), inspect_kinds_eligible=inspect, conditional_future_kinds=conditional)


def _source_digest(receipt: Any) -> str:
    digest = str(getattr(receipt, "digest", "") or "")
    if digest:
        return digest
    try:
        return host_resource_proposal_receipt_digest(receipt)
    except Exception:  # defensive for mapping-like test doubles; no host effect.
        return hashlib.sha256(_canonical_json(getattr(receipt, "to_dict", lambda: dict(receipt))()).encode("utf-8")).hexdigest()


def _source_claim_findings(receipt: Any) -> tuple[str, ...]:
    findings: list[str] = []
    required_true = {
        "proposal_only": getattr(receipt, "proposal_only", True),
        "does_not_execute": getattr(receipt, "does_not_execute", True),
        "does_not_mutate_host": getattr(receipt, "does_not_mutate_host", True),
        "not_authorized_for_fulfillment": getattr(receipt, "not_authorized_for_fulfillment", True),
        "requires_privilege_broker_for_future_action": getattr(receipt, "requires_privilege_broker_for_future_action", True),
        "requires_control_plane_admission_for_future_action": getattr(receipt, "requires_control_plane_admission_for_future_action", True),
        "requires_operator_or_policy_approval_for_future_action": getattr(receipt, "requires_operator_or_policy_approval_for_future_action", True),
        "requires_audit_receipt_for_future_action": getattr(receipt, "requires_audit_receipt_for_future_action", True),
        "requires_rollback_receipt_for_future_action": getattr(receipt, "requires_rollback_receipt_for_future_action", True),
    }
    for flag, value in required_true.items():
        if not value:
            findings.append(f"source_receipt_claims_execution_or_authority:{flag}")
    if getattr(receipt, "host_mutation_performed", False):
        findings.append("source_receipt_claims_host_mutation")
    missing_gates = [gate for gate in FUTURE_ACTION_GATES if gate not in tuple(getattr(receipt, "required_future_gates", ()) or ())]
    if missing_gates:
        findings.append("source_receipt_missing_future_gates")
    missing_blocks = [action for action in BLOCKED_HOST_ACTIONS if action not in tuple(getattr(receipt, "blocked_actions", ()) or ())]
    if missing_blocks:
        findings.append("source_receipt_missing_blocked_actions")
    return tuple(findings)


def evaluate_privilege_broker_eligibility(receipt: Any, *, policy: PrivilegeBrokerPolicy | None = None) -> PrivilegeBrokerEligibilityDecision:
    broker_policy = policy or build_default_privilege_broker_policy()
    source_receipt_id = str(getattr(receipt, "receipt_id", ""))
    source_digest = _source_digest(receipt)
    proposal_kind = str(getattr(receipt, "proposal_kind", ""))
    proposal_status = str(getattr(receipt, "proposal_status", ""))
    proposal_scope = str(getattr(receipt, "proposal_scope", ""))
    pressure_labels = tuple(sorted(str(label) for label in getattr(receipt, "pressure_labels", ()) or ()))
    domain = _KIND_TO_DOMAIN.get(proposal_kind, "diagnostics_only")
    warnings = set(_tuple_str(getattr(receipt, "warning_codes", ()) or ()))
    risks = set(_tuple_str(getattr(receipt, "risk_codes", ()) or ()))
    reasons: set[str] = {"broker_classification_only", "eligibility_is_not_authorization", "broker_decision_is_not_fulfillment"}
    missing: set[str] = set()
    blocked_actions = set(BLOCKED_HOST_ACTIONS)
    blocked_actions.update(_KIND_TO_BLOCKED_ACTIONS.get(proposal_kind, ()))
    validation = validate_host_resource_proposal_receipt(receipt)
    source_claim_findings = _source_claim_findings(receipt)
    required_gates = _KIND_TO_GATES.get(proposal_kind, BASE_FUTURE_GATES)

    if proposal_kind in broker_policy.conditional_future_kinds:
        required_gates = _KIND_TO_GATES[proposal_kind]
        missing.update(required_gates)
        reasons.add("future_privileged_action_requires_unimplemented_future_gates")
    elif proposal_kind == "inspect_service_health_candidate":
        reasons.add("service_restart_remains_blocked_deferred")
    elif proposal_kind.startswith("inspect_") or proposal_kind in broker_policy.inspect_kinds_eligible:
        reasons.add("inspect_or_review_candidate_is_metadata_only")
    else:
        warnings.add("unknown_or_noncanonical_proposal_kind")
        reasons.add("noncanonical_kind_requires_operator_review")

    if proposal_kind == "future_cooling_policy_candidate":
        risks.add("cooling_control_requires_hardware_and_os_bounds")
        blocked_actions.update(("fan_pwm_write", "thermal_actuation"))
    if proposal_kind == "future_power_policy_candidate":
        risks.add("power_policy_mutation_requires_backend_and_bounds")
    if proposal_kind == "future_cleanup_policy_candidate":
        risks.add("cleanup_requires_dry_run_path_scope_and_rollback")
    if proposal_kind == "inspect_service_health_candidate":
        blocked_actions.add("service_restart")

    if proposal_status in _CONTRADICTORY_RECEIPT_STATUSES:
        eligibility_status = "privilege_broker_contradicted"
        reasons.add("source_proposal_receipt_contradicted")
    elif proposal_status in _INCOMPLETE_RECEIPT_STATUSES:
        eligibility_status = "privilege_broker_incomplete"
        reasons.add("source_proposal_receipt_incomplete")
    elif source_claim_findings:
        if any("claims" in finding for finding in source_claim_findings):
            eligibility_status = "privilege_broker_contradicted"
            reasons.add("source_receipt_claims_forbidden_effect")
        else:
            eligibility_status = "privilege_broker_blocked"
            reasons.add("source_receipt_missing_required_non_effect_evidence")
        missing.update(source_claim_findings)
    elif proposal_status in _BLOCKED_RECEIPT_STATUSES:
        eligibility_status = "privilege_broker_blocked"
        reasons.add("source_proposal_receipt_blocked")
    elif not validation.ok:
        eligibility_status = "privilege_broker_contradicted" if any("claim" in finding or "digest" in finding for finding in validation.findings) else "privilege_broker_blocked"
        missing.update(validation.findings)
        reasons.add("source_proposal_receipt_failed_validation")
    elif proposal_status in _RECORDED_RECEIPT_STATUSES and proposal_kind in broker_policy.conditional_future_kinds:
        eligibility_status = "privilege_broker_eligible_with_conditions"
        warnings.add("future_action_still_requires_authorization_and_fulfillment")
    elif proposal_status in _RECORDED_RECEIPT_STATUSES:
        eligibility_status = "privilege_broker_eligible_for_future_review"
    elif proposal_status not in HOST_RESOURCE_PROPOSAL_STATUSES:
        eligibility_status = "privilege_broker_incomplete"
        missing.add("unknown_source_proposal_status")
    else:
        eligibility_status = "privilege_broker_blocked"

    material = {
        "source_receipt_id": source_receipt_id,
        "source_receipt_digest": source_digest,
        "source_proposal_kind": proposal_kind,
        "proposal_status": proposal_status,
        "proposal_scope": proposal_scope,
        "pressure_labels": pressure_labels,
        "privilege_domain": domain,
        "eligibility_status": eligibility_status,
        "required_future_gates": required_gates,
        "blocked_actions": tuple(sorted(blocked_actions)),
        "missing_prerequisites": tuple(sorted(missing)),
        "policy_id": broker_policy.policy_id,
    }
    return PrivilegeBrokerEligibilityDecision(
        decision_id=_digest_payload("pbd_", material),
        source_receipt_id=source_receipt_id,
        source_receipt_digest=source_digest,
        source_proposal_kind=proposal_kind,
        proposal_status=proposal_status,
        proposal_scope=proposal_scope,
        pressure_labels=pressure_labels,
        privilege_domain=domain,
        eligibility_status=eligibility_status,
        reason_codes=tuple(sorted(reasons)),
        warning_codes=tuple(sorted(warnings)),
        risk_codes=tuple(sorted(risks)),
        required_future_gates=tuple(required_gates),
        blocked_actions=tuple(sorted(blocked_actions)),
        missing_prerequisites=tuple(sorted(missing)),
    )


def _review_status_for(decision: PrivilegeBrokerEligibilityDecision) -> str:
    if decision.eligibility_status == "privilege_broker_contradicted":
        return "privilege_broker_receipt_contradicted"
    if decision.eligibility_status == "privilege_broker_incomplete":
        return "privilege_broker_receipt_incomplete"
    if decision.eligibility_status == "privilege_broker_blocked":
        return "privilege_broker_receipt_blocked"
    if decision.warning_codes or decision.eligibility_status == "privilege_broker_eligible_with_conditions":
        return "privilege_broker_receipt_recorded_with_warnings"
    return "privilege_broker_receipt_recorded"


def build_privilege_broker_review_receipt(
    decision: PrivilegeBrokerEligibilityDecision,
    *,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> PrivilegeBrokerReviewReceipt:
    evidence = (
        f"source_proposal_kind:{decision.source_proposal_kind}",
        f"eligibility_status:{decision.eligibility_status}",
        "eligibility_is_not_authorization",
        "broker_receipt_is_not_fulfillment",
        "future_action_requires_control_plane_operator_audit_rollback_and_fulfillment",
    )
    review_status = _review_status_for(decision)
    material = {
        "decision_id": decision.decision_id,
        "source_receipt_id": decision.source_receipt_id,
        "source_receipt_digest": decision.source_receipt_digest,
        "privilege_domain": decision.privilege_domain,
        "eligibility_status": decision.eligibility_status,
        "review_status": review_status,
        "required_future_gates": decision.required_future_gates,
        "blocked_actions": decision.blocked_actions,
        "created_at": created_at,
    }
    provisional = PrivilegeBrokerReviewReceipt(
        receipt_id=_digest_payload("pbr_", material),
        decision_id=decision.decision_id,
        source_receipt_id=decision.source_receipt_id,
        source_receipt_digest=decision.source_receipt_digest,
        privilege_domain=decision.privilege_domain,
        eligibility_status=decision.eligibility_status,
        review_status=review_status,
        evidence_summary=evidence,
        required_future_gates=decision.required_future_gates,
        blocked_actions=decision.blocked_actions,
        warning_codes=decision.warning_codes,
        risk_codes=decision.risk_codes,
        created_at=created_at,
    )
    return replace(provisional, digest=privilege_broker_receipt_digest(provisional))


def privilege_broker_decision_digest(decision: PrivilegeBrokerEligibilityDecision) -> str:
    return hashlib.sha256(_canonical_json(decision.to_dict()).encode("utf-8")).hexdigest()


def privilege_broker_receipt_digest(receipt: PrivilegeBrokerReviewReceipt) -> str:
    payload = receipt.to_dict()
    payload["digest"] = ""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def validate_privilege_broker_eligibility_decision(decision: PrivilegeBrokerEligibilityDecision) -> PrivilegeBrokerValidationResult:
    findings: list[str] = []
    if not decision.decision_id:
        findings.append("missing_decision_id")
    if not decision.source_receipt_id:
        findings.append("missing_source_receipt_id")
    if decision.privilege_domain not in PRIVILEGE_DOMAINS:
        findings.append("unknown_privilege_domain")
    if decision.eligibility_status not in PRIVILEGE_BROKER_ELIGIBILITY_STATUSES:
        findings.append("unknown_eligibility_status")
    if not decision.metadata_only or not decision.eligibility_only:
        findings.append("decision_not_metadata_eligibility_only")
    forbidden_false = {
        "authorization_granted": decision.authorization_granted,
        "fulfillment_granted": decision.fulfillment_granted,
        "host_mutation_performed": decision.host_mutation_performed,
        "fan_pwm_write_performed": decision.fan_pwm_write_performed,
        "thermal_actuation_performed": decision.thermal_actuation_performed,
        "process_kill_performed": decision.process_kill_performed,
        "service_restart_performed": decision.service_restart_performed,
        "package_install_performed": decision.package_install_performed,
        "driver_install_performed": decision.driver_install_performed,
        "provider_invocation_performed": decision.provider_invocation_performed,
        "network_performed": decision.network_performed,
        "prompt_assembly_performed": decision.prompt_assembly_performed,
    }
    for flag, value in forbidden_false.items():
        if value:
            findings.append(f"forbidden_decision_flag:{flag}")
    if decision.source_proposal_kind == "future_cooling_policy_candidate" and decision.eligibility_status == "privilege_broker_eligible_for_future_review":
        findings.append("future_cooling_cannot_be_directly_eligible")
    if decision.source_proposal_kind == "inspect_service_health_candidate" and "service_restart" not in decision.blocked_actions:
        findings.append("service_health_missing_restart_block")
    if decision.source_proposal_kind == "future_cooling_policy_candidate":
        for gate in COOLING_POLICY_GATES:
            if gate not in decision.required_future_gates:
                findings.append(f"future_cooling_missing_gate:{gate}")
    return PrivilegeBrokerValidationResult(ok=not findings, findings=tuple(findings))


def validate_privilege_broker_review_receipt(receipt: PrivilegeBrokerReviewReceipt) -> PrivilegeBrokerValidationResult:
    findings: list[str] = []
    if not receipt.receipt_id:
        findings.append("missing_receipt_id")
    if not receipt.decision_id:
        findings.append("missing_decision_id")
    if receipt.privilege_domain not in PRIVILEGE_DOMAINS:
        findings.append("unknown_privilege_domain")
    if receipt.eligibility_status not in PRIVILEGE_BROKER_ELIGIBILITY_STATUSES:
        findings.append("unknown_eligibility_status")
    if receipt.review_status not in PRIVILEGE_BROKER_REVIEW_STATUSES:
        findings.append("unknown_review_status")
    if receipt.digest and receipt.digest != privilege_broker_receipt_digest(receipt):
        findings.append("receipt_digest_mismatch")
    required_true = {
        "review_only": receipt.review_only,
        "eligibility_only": receipt.eligibility_only,
        "does_not_execute": receipt.does_not_execute,
        "does_not_mutate_host": receipt.does_not_mutate_host,
        "does_not_authorize_fulfillment": receipt.does_not_authorize_fulfillment,
        "requires_control_plane_admission_for_future_action": receipt.requires_control_plane_admission_for_future_action,
        "requires_operator_or_policy_approval_for_future_action": receipt.requires_operator_or_policy_approval_for_future_action,
        "requires_audit_receipt_for_future_action": receipt.requires_audit_receipt_for_future_action,
        "requires_rollback_receipt_for_future_action": receipt.requires_rollback_receipt_for_future_action,
        "requires_actuation_fulfillment_layer_for_future_action": receipt.requires_actuation_fulfillment_layer_for_future_action,
    }
    for flag, value in required_true.items():
        if not value:
            findings.append(f"receipt_claims_execution_or_authority:{flag}")
    return PrivilegeBrokerValidationResult(ok=not findings, findings=tuple(findings))


def summarize_privilege_broker_eligibility_decision(decision: PrivilegeBrokerEligibilityDecision) -> dict[str, Any]:
    return {
        "decision_id": decision.decision_id,
        "source_receipt_id": decision.source_receipt_id,
        "source_proposal_kind": decision.source_proposal_kind,
        "privilege_domain": decision.privilege_domain,
        "eligibility_status": decision.eligibility_status,
        "future_gate_count": len(decision.required_future_gates),
        "blocked_action_count": len(decision.blocked_actions),
        "missing_prerequisite_count": len(decision.missing_prerequisites),
        "metadata_only": decision.metadata_only,
        "eligibility_only": decision.eligibility_only,
        "authorization_granted": decision.authorization_granted,
        "fulfillment_granted": decision.fulfillment_granted,
        "host_mutation_performed": decision.host_mutation_performed,
        "fan_pwm_write_performed": decision.fan_pwm_write_performed,
        "thermal_actuation_performed": decision.thermal_actuation_performed,
        "network_performed": decision.network_performed,
        "digest": privilege_broker_decision_digest(decision),
    }


def summarize_privilege_broker_review_receipt(receipt: PrivilegeBrokerReviewReceipt) -> dict[str, Any]:
    return {
        "receipt_id": receipt.receipt_id,
        "decision_id": receipt.decision_id,
        "source_receipt_id": receipt.source_receipt_id,
        "privilege_domain": receipt.privilege_domain,
        "eligibility_status": receipt.eligibility_status,
        "review_status": receipt.review_status,
        "future_gate_count": len(receipt.required_future_gates),
        "blocked_action_count": len(receipt.blocked_actions),
        "warning_count": len(receipt.warning_codes),
        "risk_count": len(receipt.risk_codes),
        "review_only": receipt.review_only,
        "eligibility_only": receipt.eligibility_only,
        "does_not_execute": receipt.does_not_execute,
        "does_not_mutate_host": receipt.does_not_mutate_host,
        "does_not_authorize_fulfillment": receipt.does_not_authorize_fulfillment,
        "digest": receipt.digest,
    }
