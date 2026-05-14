"""Dry-run Actuation Fulfillment Layer scaffold for SentientOS Phase 5.

This module is metadata-only and rehearsal-only. It evaluates Phase 4 Privilege
Broker review receipts and produces deterministic fulfillment rehearsal plans
and rehearsal receipts. It never performs host actions, calls control-plane
admission/execution, mutates host state, writes fan/PWM controls, changes
thermal or power settings, kills processes, restarts services, installs packages
or drivers, removes files, performs network activity, invokes providers, or
assembles prompts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence

from sentientos.privilege_broker import (
    CLEANUP_POLICY_GATES,
    COOLING_POLICY_GATES,
    POWER_POLICY_GATES,
    SERVICE_HEALTH_GATES,
    PRIVILEGE_BROKER_ELIGIBILITY_STATUSES,
    privilege_broker_receipt_digest,
    validate_privilege_broker_review_receipt,
)

ACTUATION_FULFILLMENT_PLAN_STATUSES = frozenset(
    {
        "actuation_fulfillment_plan_rehearsal_ready",
        "actuation_fulfillment_plan_rehearsal_ready_with_conditions",
        "actuation_fulfillment_plan_blocked",
        "actuation_fulfillment_plan_incomplete",
        "actuation_fulfillment_plan_contradicted",
    }
)
ACTUATION_FULFILLMENT_REHEARSAL_STATUSES = frozenset(
    {
        "actuation_fulfillment_rehearsal_recorded",
        "actuation_fulfillment_rehearsal_recorded_with_warnings",
        "actuation_fulfillment_rehearsal_blocked",
        "actuation_fulfillment_rehearsal_incomplete",
        "actuation_fulfillment_rehearsal_contradicted",
    }
)
FULFILLMENT_DOMAINS = frozenset(
    {
        "diagnostics_only",
        "operator_review",
        "resource_pressure_review",
        "thermal_safety_review",
        "disk_safety_review",
        "service_health_review",
        "future_cooling_rehearsal",
        "future_power_rehearsal",
        "future_cleanup_rehearsal",
        "future_service_rehearsal",
    }
)
FULFILLMENT_BACKEND_CLASSES = frozenset(
    {
        "no_backend_required",
        "diagnostic_backend_future",
        "cooling_backend_future",
        "power_backend_future",
        "cleanup_backend_future",
        "service_backend_future",
        "operator_manual_backend_future",
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
    "dry_run_required",
    "effect_receipt_required",
    "postcondition_check_required",
)
BASE_REQUIRED_GATES = (
    "control_plane_admission_required",
    "operator_or_policy_approval_required",
    "audit_receipt_required",
    "rollback_receipt_required",
    "rehearsal_required",
    "dry_run_required",
    "effect_receipt_required",
    "postcondition_check_required",
)
_DOMAIN_GATES: Mapping[str, tuple[str, ...]] = {
    "future_cooling_policy_review": REQUIRED_FUTURE_GATES,
    "future_power_policy_review": (
        "control_plane_admission_required",
        "operator_or_policy_approval_required",
        "audit_receipt_required",
        "rollback_receipt_required",
        "panic_stop_required",
        "os_backend_declaration_required",
        "bounds_policy_required",
        "rehearsal_required",
        "dry_run_required",
        "effect_receipt_required",
        "postcondition_check_required",
    ),
    "future_cleanup_policy_review": BASE_REQUIRED_GATES + ("panic_stop_required",),
    "service_health_review": BASE_REQUIRED_GATES + ("panic_stop_required",),
}
_DOMAIN_BLOCKED_ACTIONS: Mapping[str, tuple[str, ...]] = {
    "future_cooling_policy_review": ("fan_pwm_write", "thermal_actuation"),
    "future_power_policy_review": ("power_profile_mutation",),
    "future_cleanup_policy_review": ("file_delete", "file_cleanup", "disk_cleanup_mutation"),
    "service_health_review": ("service_restart",),
}
_BROKER_CONDITION_GATES: Mapping[str, tuple[str, ...]] = {
    "future_cooling_policy_review": COOLING_POLICY_GATES,
    "future_power_policy_review": POWER_POLICY_GATES,
    "future_cleanup_policy_review": CLEANUP_POLICY_GATES,
    "service_health_review": SERVICE_HEALTH_GATES,
}

_DOMAIN_REHEARSAL: Mapping[str, tuple[str, str]] = {
    "diagnostics_only": ("diagnostics_only", "no_backend_required"),
    "operator_review": ("operator_review", "operator_manual_backend_future"),
    "resource_pressure_review": ("resource_pressure_review", "diagnostic_backend_future"),
    "thermal_safety_review": ("thermal_safety_review", "diagnostic_backend_future"),
    "disk_safety_review": ("disk_safety_review", "diagnostic_backend_future"),
    "service_health_review": ("service_health_review", "service_backend_future"),
    "future_cooling_policy_review": ("future_cooling_rehearsal", "cooling_backend_future"),
    "future_power_policy_review": ("future_power_rehearsal", "power_backend_future"),
    "future_cleanup_policy_review": ("future_cleanup_rehearsal", "cleanup_backend_future"),
    "future_actuation_fulfillment_review": ("operator_review", "operator_manual_backend_future"),
}
_BASE_BLOCKED_ACTIONS = (
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
)


@dataclass(frozen=True)
class ActuationFulfillmentPolicy:
    policy_id: str
    allowed_rehearsal_domains: tuple[str, ...]
    required_future_gates: tuple[str, ...] = REQUIRED_FUTURE_GATES
    blocked_actions: tuple[str, ...] = _BASE_BLOCKED_ACTIONS
    metadata_only: bool = True
    rehearsal_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActuationFulfillmentPlan:
    plan_id: str
    source_broker_receipt_id: str
    source_broker_receipt_digest: str
    source_eligibility_status: str
    privilege_domain: str
    fulfillment_domain: str
    backend_class: str
    plan_status: str
    reason_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    required_future_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    rehearsal_steps: tuple[str, ...]
    expected_postconditions: tuple[str, ...]
    rollback_requirements: tuple[str, ...]
    metadata_only: bool = True
    rehearsal_only: bool = True
    authorization_granted: bool = False
    fulfillment_granted: bool = False
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActuationFulfillmentRehearsalReceipt:
    receipt_id: str
    plan_id: str
    source_broker_receipt_id: str
    source_broker_receipt_digest: str
    fulfillment_domain: str
    backend_class: str
    plan_status: str
    rehearsal_status: str
    evidence_summary: tuple[str, ...]
    rehearsal_steps: tuple[str, ...]
    required_future_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    expected_postconditions: tuple[str, ...]
    rollback_requirements: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str = ""
    rehearsal_only: bool = True
    dry_run_only: bool = True
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    does_not_authorize_fulfillment: bool = True
    effect_not_performed: bool = True
    requires_control_plane_admission_for_future_action: bool = True
    requires_operator_or_policy_approval_for_future_action: bool = True
    requires_audit_receipt_for_future_action: bool = True
    requires_rollback_receipt_for_future_action: bool = True
    requires_effect_receipt_for_future_action: bool = True
    requires_postcondition_check_for_future_action: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActuationFulfillmentValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest_payload(prefix: str, payload: Mapping[str, Any], length: int = 24) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:length]


def _merge_unique(*groups: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({str(item) for group in groups for item in group}))


def _source_digest(receipt: Any) -> str:
    digest = str(getattr(receipt, "digest", "") or "")
    if digest:
        return digest
    try:
        return privilege_broker_receipt_digest(receipt)
    except Exception:  # defensive only for mapping-like test doubles; no host effect.
        value = getattr(receipt, "to_dict", lambda: dict(receipt))()
        return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def build_default_actuation_fulfillment_policy() -> ActuationFulfillmentPolicy:
    material = {"domains": tuple(sorted(FULFILLMENT_DOMAINS)), "gates": REQUIRED_FUTURE_GATES, "blocked_actions": _BASE_BLOCKED_ACTIONS}
    return ActuationFulfillmentPolicy(policy_id=_digest_payload("afp_", material), allowed_rehearsal_domains=tuple(sorted(FULFILLMENT_DOMAINS)))


def _source_claim_findings(receipt: Any) -> tuple[str, ...]:
    findings: list[str] = []
    required_true = {
        "review_only": getattr(receipt, "review_only", True),
        "eligibility_only": getattr(receipt, "eligibility_only", True),
        "does_not_execute": getattr(receipt, "does_not_execute", True),
        "does_not_mutate_host": getattr(receipt, "does_not_mutate_host", True),
        "does_not_authorize_fulfillment": getattr(receipt, "does_not_authorize_fulfillment", True),
    }
    for flag, value in required_true.items():
        if not value:
            findings.append(f"source_broker_receipt_claims_authority_or_effect:{flag}")
    forbidden_false = {
        "authorization_granted": getattr(receipt, "authorization_granted", False),
        "fulfillment_granted": getattr(receipt, "fulfillment_granted", False),
        "host_mutation_performed": getattr(receipt, "host_mutation_performed", False),
        "fan_pwm_write_performed": getattr(receipt, "fan_pwm_write_performed", False),
        "thermal_actuation_performed": getattr(receipt, "thermal_actuation_performed", False),
        "power_profile_mutation_performed": getattr(receipt, "power_profile_mutation_performed", False),
        "process_kill_performed": getattr(receipt, "process_kill_performed", False),
        "service_restart_performed": getattr(receipt, "service_restart_performed", False),
        "package_install_performed": getattr(receipt, "package_install_performed", False),
        "driver_install_performed": getattr(receipt, "driver_install_performed", False),
        "file_cleanup_performed": getattr(receipt, "file_cleanup_performed", False),
        "provider_invocation_performed": getattr(receipt, "provider_invocation_performed", False),
        "network_performed": getattr(receipt, "network_performed", False),
        "prompt_assembly_performed": getattr(receipt, "prompt_assembly_performed", False),
    }
    for flag, value in forbidden_false.items():
        if value:
            findings.append(f"source_broker_receipt_claims_forbidden_effect:{flag}")
    return tuple(findings)


def _receipt_validation_findings(receipt: Any) -> tuple[str, ...]:
    try:
        validation = validate_privilege_broker_review_receipt(receipt)
        return () if validation.ok else validation.findings
    except Exception:
        return ("source_broker_receipt_failed_validation",)


def _plan_status_for(eligibility_status: str, *, contradicted: bool, missing: Sequence[str], warnings: Sequence[str]) -> str:
    if contradicted or eligibility_status == "privilege_broker_contradicted":
        return "actuation_fulfillment_plan_contradicted"
    if eligibility_status == "privilege_broker_incomplete":
        return "actuation_fulfillment_plan_incomplete"
    if eligibility_status == "privilege_broker_blocked":
        return "actuation_fulfillment_plan_blocked"
    if missing:
        return "actuation_fulfillment_plan_incomplete"
    if eligibility_status == "privilege_broker_eligible_with_conditions":
        return "actuation_fulfillment_plan_rehearsal_ready_with_conditions"
    if warnings:
        return "actuation_fulfillment_plan_rehearsal_ready_with_conditions"
    return "actuation_fulfillment_plan_rehearsal_ready"


def _rehearsal_status_for(plan_status: str, warning_codes: Sequence[str]) -> str:
    if plan_status == "actuation_fulfillment_plan_contradicted":
        return "actuation_fulfillment_rehearsal_contradicted"
    if plan_status == "actuation_fulfillment_plan_incomplete":
        return "actuation_fulfillment_rehearsal_incomplete"
    if plan_status == "actuation_fulfillment_plan_blocked":
        return "actuation_fulfillment_rehearsal_blocked"
    if warning_codes or plan_status == "actuation_fulfillment_plan_rehearsal_ready_with_conditions":
        return "actuation_fulfillment_rehearsal_recorded_with_warnings"
    return "actuation_fulfillment_rehearsal_recorded"


def build_actuation_fulfillment_plan(receipt: Any, *, policy: ActuationFulfillmentPolicy | None = None) -> ActuationFulfillmentPlan:
    fulfillment_policy = policy or build_default_actuation_fulfillment_policy()
    source_id = str(getattr(receipt, "receipt_id", ""))
    source_digest = _source_digest(receipt)
    eligibility_status = str(getattr(receipt, "eligibility_status", ""))
    privilege_domain = str(getattr(receipt, "privilege_domain", "diagnostics_only") or "diagnostics_only")
    fulfillment_domain, backend_class = _DOMAIN_REHEARSAL.get(privilege_domain, ("diagnostics_only", "diagnostic_backend_future"))
    source_gates = tuple(str(gate) for gate in getattr(receipt, "required_future_gates", ()) or ())
    source_blocked = tuple(str(action) for action in getattr(receipt, "blocked_actions", ()) or ())
    warning_codes = set(str(code) for code in getattr(receipt, "warning_codes", ()) or ())
    risk_codes = set(str(code) for code in getattr(receipt, "risk_codes", ()) or ())
    reason_codes = {"fulfillment_rehearsal_only", "broker_eligibility_is_not_authorization", "broker_review_receipt_is_not_fulfillment"}
    missing = set(str(item) for item in getattr(receipt, "missing_prerequisites", ()) or ())
    claim_findings = _source_claim_findings(receipt)
    validation_findings = _receipt_validation_findings(receipt)
    expected_gates = _DOMAIN_GATES.get(privilege_domain, BASE_REQUIRED_GATES)
    if eligibility_status == "privilege_broker_eligible_with_conditions":
        missing.update(gate for gate in _BROKER_CONDITION_GATES.get(privilege_domain, expected_gates) if gate not in source_gates)
        if missing:
            reason_codes.add("broker_condition_gates_missing")
        else:
            reason_codes.add("broker_condition_gates_preserved")
    required_future_gates = _merge_unique(source_gates, expected_gates, BASE_REQUIRED_GATES)
    blocked_actions = _merge_unique(fulfillment_policy.blocked_actions, source_blocked, _DOMAIN_BLOCKED_ACTIONS.get(privilege_domain, ()))
    if eligibility_status not in PRIVILEGE_BROKER_ELIGIBILITY_STATUSES:
        missing.add("unknown_source_broker_eligibility_status")
    if claim_findings:
        reason_codes.add("source_broker_receipt_claims_forbidden_authority_or_effect")
        missing.update(claim_findings)
    if validation_findings:
        warning_codes.add("source_broker_receipt_validation_findings_preserved")
        missing.update(validation_findings)
    if privilege_domain == "future_cooling_policy_review":
        reason_codes.add("cooling_rehearsal_keeps_fan_pwm_and_thermal_actuation_blocked")
        risk_codes.add("cooling_backend_requires_future_allowlist_bounds_cooldown_and_panic_stop")
    if privilege_domain == "future_power_policy_review":
        reason_codes.add("power_rehearsal_keeps_power_profile_mutation_blocked")
        risk_codes.add("power_backend_requires_future_os_backend_and_bounds")
    if privilege_domain == "future_cleanup_policy_review":
        reason_codes.add("cleanup_rehearsal_keeps_file_cleanup_blocked")
        risk_codes.add("cleanup_backend_requires_future_path_scope_dry_run_and_rollback")
    if privilege_domain == "service_health_review":
        reason_codes.add("service_health_rehearsal_keeps_restart_blocked")
    plan_status = _plan_status_for(eligibility_status, contradicted=bool(claim_findings), missing=tuple(sorted(missing)), warnings=tuple(sorted(warning_codes)))
    rehearsal_steps = (
        "read_broker_review_receipt_metadata",
        "classify_fulfillment_rehearsal_domain",
        "preserve_required_future_gates",
        "preserve_blocked_actions",
        "record_expected_postconditions_without_effect",
    )
    expected_postconditions = (
        "no_host_mutation_performed",
        "no_effect_receipt_created_by_rehearsal",
        "future_action_requires_authorize_fulfill_audit_rollback_sequence",
    )
    rollback_requirements = (
        "future_real_fulfillment_must_define_rollback_receipt_before_effect",
        "rehearsal_has_no_runtime_state_to_rollback",
    )
    material = {
        "source_broker_receipt_id": source_id,
        "source_broker_receipt_digest": source_digest,
        "source_eligibility_status": eligibility_status,
        "privilege_domain": privilege_domain,
        "fulfillment_domain": fulfillment_domain,
        "backend_class": backend_class,
        "plan_status": plan_status,
        "required_future_gates": required_future_gates,
        "blocked_actions": blocked_actions,
        "missing_prerequisites": tuple(sorted(missing)),
    }
    return ActuationFulfillmentPlan(
        plan_id=_digest_payload("afpl_", material),
        source_broker_receipt_id=source_id,
        source_broker_receipt_digest=source_digest,
        source_eligibility_status=eligibility_status,
        privilege_domain=privilege_domain,
        fulfillment_domain=fulfillment_domain,
        backend_class=backend_class,
        plan_status=plan_status,
        reason_codes=tuple(sorted(reason_codes)),
        warning_codes=tuple(sorted(warning_codes)),
        risk_codes=tuple(sorted(risk_codes)),
        required_future_gates=required_future_gates,
        blocked_actions=blocked_actions,
        missing_prerequisites=tuple(sorted(missing)),
        rehearsal_steps=rehearsal_steps,
        expected_postconditions=expected_postconditions,
        rollback_requirements=rollback_requirements,
    )


def build_actuation_fulfillment_rehearsal_receipt(plan: ActuationFulfillmentPlan, *, created_at: str = "1970-01-01T00:00:00+00:00") -> ActuationFulfillmentRehearsalReceipt:
    rehearsal_status = _rehearsal_status_for(plan.plan_status, plan.warning_codes)
    evidence = (
        f"source_broker_receipt_id:{plan.source_broker_receipt_id}",
        f"source_eligibility_status:{plan.source_eligibility_status}",
        f"fulfillment_domain:{plan.fulfillment_domain}",
        "fulfillment_rehearsal_is_not_real_fulfillment",
        "rehearsal_receipt_is_not_effect_receipt",
        "no_host_mutation_occurs",
    )
    material = {
        "plan_id": plan.plan_id,
        "source_broker_receipt_id": plan.source_broker_receipt_id,
        "source_broker_receipt_digest": plan.source_broker_receipt_digest,
        "fulfillment_domain": plan.fulfillment_domain,
        "backend_class": plan.backend_class,
        "plan_status": plan.plan_status,
        "rehearsal_status": rehearsal_status,
        "created_at": created_at,
    }
    provisional = ActuationFulfillmentRehearsalReceipt(
        receipt_id=_digest_payload("afrr_", material),
        plan_id=plan.plan_id,
        source_broker_receipt_id=plan.source_broker_receipt_id,
        source_broker_receipt_digest=plan.source_broker_receipt_digest,
        fulfillment_domain=plan.fulfillment_domain,
        backend_class=plan.backend_class,
        plan_status=plan.plan_status,
        rehearsal_status=rehearsal_status,
        evidence_summary=evidence,
        rehearsal_steps=plan.rehearsal_steps,
        required_future_gates=plan.required_future_gates,
        blocked_actions=plan.blocked_actions,
        expected_postconditions=plan.expected_postconditions,
        rollback_requirements=plan.rollback_requirements,
        warning_codes=plan.warning_codes,
        risk_codes=plan.risk_codes,
        created_at=created_at,
    )
    return replace(provisional, digest=actuation_fulfillment_rehearsal_receipt_digest(provisional))


def actuation_fulfillment_plan_digest(plan: ActuationFulfillmentPlan) -> str:
    return hashlib.sha256(_canonical_json(plan.to_dict()).encode("utf-8")).hexdigest()


def actuation_fulfillment_rehearsal_receipt_digest(receipt: ActuationFulfillmentRehearsalReceipt) -> str:
    payload = receipt.to_dict()
    payload["digest"] = ""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _validate_common_flags(value: Any, prefix: str) -> list[str]:
    findings: list[str] = []
    required_false = {
        "authorization_granted": getattr(value, "authorization_granted", False),
        "fulfillment_granted": getattr(value, "fulfillment_granted", False),
        "host_mutation_performed": getattr(value, "host_mutation_performed", False),
        "fan_pwm_write_performed": getattr(value, "fan_pwm_write_performed", False),
        "thermal_actuation_performed": getattr(value, "thermal_actuation_performed", False),
        "power_profile_mutation_performed": getattr(value, "power_profile_mutation_performed", False),
        "process_kill_performed": getattr(value, "process_kill_performed", False),
        "service_restart_performed": getattr(value, "service_restart_performed", False),
        "package_install_performed": getattr(value, "package_install_performed", False),
        "driver_install_performed": getattr(value, "driver_install_performed", False),
        "file_cleanup_performed": getattr(value, "file_cleanup_performed", False),
        "provider_invocation_performed": getattr(value, "provider_invocation_performed", False),
        "network_performed": getattr(value, "network_performed", False),
        "prompt_assembly_performed": getattr(value, "prompt_assembly_performed", False),
    }
    for flag, flag_value in required_false.items():
        if flag_value:
            findings.append(f"{prefix}_forbidden_flag:{flag}")
    return findings


def validate_actuation_fulfillment_plan(plan: ActuationFulfillmentPlan) -> ActuationFulfillmentValidationResult:
    findings: list[str] = []
    if not plan.plan_id:
        findings.append("missing_plan_id")
    if not plan.source_broker_receipt_id:
        findings.append("missing_source_broker_receipt_id")
    if plan.source_eligibility_status not in PRIVILEGE_BROKER_ELIGIBILITY_STATUSES:
        findings.append("unknown_source_eligibility_status")
    if plan.fulfillment_domain not in FULFILLMENT_DOMAINS:
        findings.append("unknown_fulfillment_domain")
    if plan.backend_class not in FULFILLMENT_BACKEND_CLASSES:
        findings.append("unknown_backend_class")
    if plan.plan_status not in ACTUATION_FULFILLMENT_PLAN_STATUSES:
        findings.append("unknown_plan_status")
    if not plan.metadata_only or not plan.rehearsal_only:
        findings.append("plan_not_metadata_rehearsal_only")
    findings.extend(_validate_common_flags(plan, "plan"))
    for gate in BASE_REQUIRED_GATES:
        if gate not in plan.required_future_gates:
            findings.append(f"plan_missing_base_future_gate:{gate}")
    if plan.fulfillment_domain == "future_cooling_rehearsal":
        for action in ("fan_pwm_write", "thermal_actuation"):
            if action not in plan.blocked_actions:
                findings.append(f"future_cooling_missing_blocked_action:{action}")
    if plan.fulfillment_domain == "future_power_rehearsal" and "power_profile_mutation" not in plan.blocked_actions:
        findings.append("future_power_missing_power_profile_mutation_block")
    if plan.fulfillment_domain == "future_cleanup_rehearsal" and not {"file_cleanup", "file_delete"}.intersection(plan.blocked_actions):
        findings.append("future_cleanup_missing_file_cleanup_block")
    if plan.fulfillment_domain in {"service_health_review", "future_service_rehearsal"} and "service_restart" not in plan.blocked_actions:
        findings.append("service_health_missing_restart_block")
    return ActuationFulfillmentValidationResult(ok=not findings, findings=tuple(findings))


def validate_actuation_fulfillment_rehearsal_receipt(receipt: ActuationFulfillmentRehearsalReceipt) -> ActuationFulfillmentValidationResult:
    findings: list[str] = []
    if not receipt.receipt_id:
        findings.append("missing_receipt_id")
    if not receipt.plan_id:
        findings.append("missing_plan_id")
    if receipt.fulfillment_domain not in FULFILLMENT_DOMAINS:
        findings.append("unknown_fulfillment_domain")
    if receipt.backend_class not in FULFILLMENT_BACKEND_CLASSES:
        findings.append("unknown_backend_class")
    if receipt.plan_status not in ACTUATION_FULFILLMENT_PLAN_STATUSES:
        findings.append("unknown_plan_status")
    if receipt.rehearsal_status not in ACTUATION_FULFILLMENT_REHEARSAL_STATUSES:
        findings.append("unknown_rehearsal_status")
    if receipt.digest and receipt.digest != actuation_fulfillment_rehearsal_receipt_digest(receipt):
        findings.append("receipt_digest_mismatch")
    required_true = {
        "rehearsal_only": receipt.rehearsal_only,
        "dry_run_only": receipt.dry_run_only,
        "does_not_execute": receipt.does_not_execute,
        "does_not_mutate_host": receipt.does_not_mutate_host,
        "does_not_authorize_fulfillment": receipt.does_not_authorize_fulfillment,
        "effect_not_performed": receipt.effect_not_performed,
        "requires_control_plane_admission_for_future_action": receipt.requires_control_plane_admission_for_future_action,
        "requires_operator_or_policy_approval_for_future_action": receipt.requires_operator_or_policy_approval_for_future_action,
        "requires_audit_receipt_for_future_action": receipt.requires_audit_receipt_for_future_action,
        "requires_rollback_receipt_for_future_action": receipt.requires_rollback_receipt_for_future_action,
        "requires_effect_receipt_for_future_action": receipt.requires_effect_receipt_for_future_action,
        "requires_postcondition_check_for_future_action": receipt.requires_postcondition_check_for_future_action,
    }
    for flag, value in required_true.items():
        if not value:
            findings.append(f"receipt_claims_effect_or_missing_gate:{flag}")
    return ActuationFulfillmentValidationResult(ok=not findings, findings=tuple(findings))


def summarize_actuation_fulfillment_plan(plan: ActuationFulfillmentPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "source_broker_receipt_id": plan.source_broker_receipt_id,
        "source_eligibility_status": plan.source_eligibility_status,
        "privilege_domain": plan.privilege_domain,
        "fulfillment_domain": plan.fulfillment_domain,
        "backend_class": plan.backend_class,
        "plan_status": plan.plan_status,
        "future_gate_count": len(plan.required_future_gates),
        "blocked_action_count": len(plan.blocked_actions),
        "metadata_only": plan.metadata_only,
        "rehearsal_only": plan.rehearsal_only,
        "authorization_granted": plan.authorization_granted,
        "fulfillment_granted": plan.fulfillment_granted,
        "host_mutation_performed": plan.host_mutation_performed,
        "fan_pwm_write_performed": plan.fan_pwm_write_performed,
        "thermal_actuation_performed": plan.thermal_actuation_performed,
        "power_profile_mutation_performed": plan.power_profile_mutation_performed,
        "service_restart_performed": plan.service_restart_performed,
        "file_cleanup_performed": plan.file_cleanup_performed,
        "network_performed": plan.network_performed,
        "digest": actuation_fulfillment_plan_digest(plan),
    }


def summarize_actuation_fulfillment_rehearsal_receipt(receipt: ActuationFulfillmentRehearsalReceipt) -> dict[str, Any]:
    return {
        "receipt_id": receipt.receipt_id,
        "plan_id": receipt.plan_id,
        "fulfillment_domain": receipt.fulfillment_domain,
        "backend_class": receipt.backend_class,
        "plan_status": receipt.plan_status,
        "rehearsal_status": receipt.rehearsal_status,
        "future_gate_count": len(receipt.required_future_gates),
        "blocked_action_count": len(receipt.blocked_actions),
        "rehearsal_only": receipt.rehearsal_only,
        "dry_run_only": receipt.dry_run_only,
        "does_not_execute": receipt.does_not_execute,
        "does_not_mutate_host": receipt.does_not_mutate_host,
        "does_not_authorize_fulfillment": receipt.does_not_authorize_fulfillment,
        "effect_not_performed": receipt.effect_not_performed,
        "digest": receipt.digest or actuation_fulfillment_rehearsal_receipt_digest(receipt),
    }


def build_actuation_rehearsals_for_broker_receipts(
    receipts: Sequence[Any],
    *,
    created_at: str = "1970-01-01T00:00:00+00:00",
    policy: ActuationFulfillmentPolicy | None = None,
) -> tuple[tuple[ActuationFulfillmentPlan, ...], tuple[ActuationFulfillmentRehearsalReceipt, ...]]:
    """Build Phase 5 rehearsal plans/receipts from Phase 4 broker receipts.

    This helper is an additive pipeline convenience. It returns metadata-only
    dry-run plans and rehearsal receipts; it does not authorize or fulfill.
    """

    plans = tuple(build_actuation_fulfillment_plan(receipt, policy=policy) for receipt in receipts)
    rehearsal_receipts = tuple(build_actuation_fulfillment_rehearsal_receipt(plan, created_at=created_at) for plan in plans)
    return plans, rehearsal_receipts
