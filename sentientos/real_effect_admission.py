"""Metadata-only real effect capability admission records.

This wing follows dry-run audit closure and decides whether future real-effect
capability domains may enter implementation planning. It does not implement,
load, invoke, execute, fulfill, mutate host state, write fan/PWM controls,
change thermal or power settings, kill processes, restart services, install
packages or drivers, delete or clean files, perform network calls, invoke
providers, assemble prompts, spawn subprocess execution, run shell execution,
invoke OS backends, or call control-plane admission/execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.dry_run_audit_closure import DryRunClosureBundle

ADMISSION_STATUSES = frozenset({
    "real_effect_admission_eligible_for_planning",
    "real_effect_admission_eligible_with_conditions",
    "real_effect_admission_blocked",
    "real_effect_admission_incomplete",
    "real_effect_admission_contradicted",
})
CANDIDATE_STATUSES = frozenset({
    "real_effect_candidate_recorded",
    "real_effect_candidate_recorded_with_warnings",
    "real_effect_candidate_blocked",
    "real_effect_candidate_incomplete",
    "real_effect_candidate_contradicted",
})
PLAN_STATUSES = frozenset({
    "real_effect_implementation_plan_scaffold_ready",
    "real_effect_implementation_plan_scaffold_ready_with_conditions",
    "real_effect_implementation_plan_scaffold_blocked",
    "real_effect_implementation_plan_scaffold_incomplete",
    "real_effect_implementation_plan_scaffold_contradicted",
})
BLOCK_RECEIPT_STATUSES = frozenset({
    "real_effect_block_receipt_recorded",
    "real_effect_block_receipt_recorded_with_warnings",
    "real_effect_block_receipt_incomplete",
    "real_effect_block_receipt_contradicted",
})
ADMISSION_DOMAINS = frozenset({
    "diagnostics_real_effect_candidate",
    "operator_review_real_effect_candidate",
    "resource_pressure_real_effect_candidate",
    "thermal_safety_real_effect_candidate",
    "future_cleanup_real_effect_candidate",
    "future_service_real_effect_candidate",
    "future_power_real_effect_candidate",
    "future_cooling_real_effect_candidate",
})
IMPLEMENTATION_TIERS = frozenset({
    "tier0_observation_only",
    "tier1_metadata_only",
    "tier2_dry_run_only",
    "tier3_local_low_risk_effect_future",
    "tier4_privileged_host_effect_future",
    "tier5_hardware_control_effect_future",
})
REQUIRED_PLANNING_LABELS = (
    "dry_run_closure_bundle_required",
    "dry_run_effect_verification_required",
    "dry_run_postcondition_verification_required",
    "dry_run_rollback_rehearsal_required",
    "dry_run_audit_closure_required",
    "safety_gate_satisfaction_required",
    "local_authorization_required",
    "fulfillment_authorization_consumption_required",
    "executor_contract_readiness_required",
    "implementation_scope_required",
    "backend_design_required",
    "effect_receipt_design_required",
    "postcondition_check_design_required",
    "rollback_design_required",
    "production_audit_design_required",
    "operator_review_required",
    "security_review_required",
)
BLOCKED_ACTION_LABELS = (
    "real_fulfillment_execution",
    "real_effect_execution",
    "real_effect_receipt_creation",
    "real_postcondition_check",
    "real_rollback_execution",
    "production_audit_receipt",
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
    "subprocess_execution",
    "shell_execution",
    "os_backend_invocation",
    "control_plane_admission_execution",
)
_LOW_RISK_DOMAINS = frozenset({
    "diagnostics_real_effect_candidate",
    "operator_review_real_effect_candidate",
    "resource_pressure_real_effect_candidate",
})
_CONDITIONAL_DOMAINS = frozenset({"thermal_safety_real_effect_candidate"})
_DEFAULT_BLOCKED_DOMAINS = frozenset({
    "future_cleanup_real_effect_candidate",
    "future_service_real_effect_candidate",
    "future_power_real_effect_candidate",
    "future_cooling_real_effect_candidate",
})
_DOMAIN_BLOCKS = {
    "future_cooling_real_effect_candidate": ("fan_pwm_write", "thermal_actuation"),
    "thermal_safety_real_effect_candidate": ("thermal_actuation",),
    "future_power_real_effect_candidate": ("power_profile_mutation",),
    "future_cleanup_real_effect_candidate": ("file_cleanup", "file_delete"),
    "future_service_real_effect_candidate": ("service_restart", "process_kill"),
}
_CLOSURE_TO_ADMISSION_DOMAIN = {
    "diagnostics_dry_run_closure": "diagnostics_real_effect_candidate",
    "operator_review_dry_run_closure": "operator_review_real_effect_candidate",
    "resource_pressure_dry_run_closure": "resource_pressure_real_effect_candidate",
    "thermal_safety_dry_run_closure": "thermal_safety_real_effect_candidate",
    "future_cleanup_dry_run_closure": "future_cleanup_real_effect_candidate",
    "future_service_dry_run_closure": "future_service_real_effect_candidate",
    "future_power_dry_run_closure": "future_power_real_effect_candidate",
    "future_cooling_dry_run_closure": "future_cooling_real_effect_candidate",
}
_FORBIDDEN_TRUE_FLAGS = (
    "authorizes_implementation",
    "authorizes_execution",
    "real_backend_implemented",
    "backend_loaded",
    "backend_invoked",
    "real_fulfillment_performed",
    "real_effect_performed",
    "host_mutation_performed",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "power_profile_mutation_performed",
    "process_kill_performed",
    "service_restart_performed",
    "package_install_performed",
    "driver_install_performed",
    "file_cleanup_performed",
    "file_delete_performed",
    "network_performed",
    "provider_invocation_performed",
    "prompt_assembly_performed",
    "subprocess_execution_performed",
    "shell_execution_performed",
    "os_backend_invoked",
    "control_plane_admission_execution_performed",
    "real_effect_receipt_created",
    "real_postcondition_check_performed",
    "real_rollback_performed",
    "production_audit_receipt_created",
)


@dataclass(frozen=True)
class RealEffectAdmissionPolicy:
    policy_id: str
    supported_admission_domains: tuple[str, ...]
    eligible_for_planning_domains: tuple[str, ...]
    conditional_domains: tuple[str, ...]
    default_blocked_domains: tuple[str, ...]
    low_risk_max_tier: str
    conditional_max_tier: str
    required_planning_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ("real_effect_admission_is_not_implementation",)
    metadata_only: bool = True
    admission_policy_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealEffectCapabilityCandidate:
    candidate_id: str
    source_dry_run_closure_bundle_id: str
    source_dry_run_closure_bundle_digest: str
    admission_domain: str
    requested_implementation_tier: str
    candidate_status: str
    candidate_scope_labels: tuple[str, ...]
    required_planning_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    candidate_only: bool = True
    implementation_not_started: bool = True
    real_backend_implemented: bool = False
    real_fulfillment_performed: bool = False
    real_effect_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealEffectCapabilityAdmissionDecision:
    decision_id: str
    candidate_id: str
    source_dry_run_closure_bundle_id: str
    admission_domain: str
    implementation_tier: str
    admission_status: str
    satisfied_planning_labels: tuple[str, ...]
    missing_planning_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    reason_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    admission_only: bool = True
    authorizes_implementation: bool = False
    authorizes_execution: bool = False
    real_backend_implemented: bool = False
    real_fulfillment_performed: bool = False
    real_effect_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealEffectImplementationPlanScaffold:
    plan_id: str
    decision_id: str
    candidate_id: str
    admission_domain: str
    implementation_tier: str
    plan_status: str
    proposed_backend_labels: tuple[str, ...]
    proposed_effect_receipt_labels: tuple[str, ...]
    proposed_postcondition_labels: tuple[str, ...]
    proposed_rollback_labels: tuple[str, ...]
    proposed_audit_labels: tuple[str, ...]
    proposed_security_review_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    plan_scaffold_only: bool = True
    implementation_not_started: bool = True
    backend_loaded: bool = False
    backend_invoked: bool = False
    real_fulfillment_performed: bool = False
    real_effect_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealEffectCapabilityBlockReceipt:
    receipt_id: str
    candidate_id: str
    decision_id: str | None
    admission_domain: str
    block_status: str
    block_reason_codes: tuple[str, ...]
    missing_planning_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    block_receipt_only: bool = True
    implementation_not_started: bool = True
    real_backend_implemented: bool = False
    real_fulfillment_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealEffectAdmissionBundle:
    bundle_id: str
    candidate_id: str
    decision_id: str
    plan_id: str | None
    block_receipt_id: str | None
    admission_domain: str
    bundle_status: str
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    admission_bundle_only: bool = True
    implementation_not_started: bool = True
    authorizes_implementation: bool = False
    authorizes_execution: bool = False
    real_backend_implemented: bool = False
    real_fulfillment_performed: bool = False
    real_effect_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealEffectAdmissionValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


class RealEffectAdmissionWingRecords(NamedTuple):
    candidate: RealEffectCapabilityCandidate
    decision: RealEffectCapabilityAdmissionDecision
    plan_or_block_receipt: RealEffectImplementationPlanScaffold | RealEffectCapabilityBlockReceipt
    admission_bundle: RealEffectAdmissionBundle


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


def real_effect_admission_digest(record_or_payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(_payload(record_or_payload)).encode("utf-8")).hexdigest()


real_effect_capability_candidate_digest = real_effect_admission_digest
real_effect_capability_admission_decision_digest = real_effect_admission_digest
real_effect_implementation_plan_scaffold_digest = real_effect_admission_digest
real_effect_capability_block_receipt_digest = real_effect_admission_digest
real_effect_admission_bundle_digest = real_effect_admission_digest


def _digest_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]


def _blocked_actions(domain: str, extra: Sequence[str] | None = None) -> tuple[str, ...]:
    return tuple(sorted(set(BLOCKED_ACTION_LABELS) | set(_DOMAIN_BLOCKS.get(domain, ())) | set(_tuple(extra))))


def _domain_from_closure(closure: Mapping[str, Any], override: str | None) -> str:
    if override:
        return override if override in ADMISSION_DOMAINS else "operator_review_real_effect_candidate"
    closure_domain = str(closure.get("closure_domain", ""))
    return _CLOSURE_TO_ADMISSION_DOMAIN.get(closure_domain, "operator_review_real_effect_candidate")


def _closure_base_status(closure: Mapping[str, Any]) -> str:
    if any(closure.get(flag, False) for flag in _FORBIDDEN_TRUE_FLAGS if flag in closure):
        return "contradicted"
    status = str(closure.get("bundle_status", ""))
    if status == "dry_run_closure_bundle_ready":
        return "ready"
    if status == "dry_run_closure_bundle_ready_with_warnings":
        return "ready_with_warnings"
    if status == "dry_run_closure_bundle_blocked":
        return "blocked"
    if status == "dry_run_closure_bundle_incomplete":
        return "incomplete"
    if status == "dry_run_closure_bundle_contradicted":
        return "contradicted"
    return "incomplete"


def build_default_real_effect_admission_policy() -> RealEffectAdmissionPolicy:
    return RealEffectAdmissionPolicy(
        policy_id="real-effect-admission-policy-v1",
        supported_admission_domains=tuple(sorted(ADMISSION_DOMAINS)),
        eligible_for_planning_domains=tuple(sorted(_LOW_RISK_DOMAINS)),
        conditional_domains=tuple(sorted(_CONDITIONAL_DOMAINS)),
        default_blocked_domains=tuple(sorted(_DEFAULT_BLOCKED_DOMAINS)),
        low_risk_max_tier="tier3_local_low_risk_effect_future",
        conditional_max_tier="tier2_dry_run_only",
        required_planning_labels=REQUIRED_PLANNING_LABELS,
        blocked_actions=BLOCKED_ACTION_LABELS,
    )


def build_real_effect_capability_candidate(
    dry_run_closure_bundle: DryRunClosureBundle | Mapping[str, Any],
    *,
    admission_domain: str | None = None,
    requested_implementation_tier: str | None = None,
    policy: RealEffectAdmissionPolicy | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> RealEffectCapabilityCandidate:
    closure = _source_payload(dry_run_closure_bundle)
    policy = policy or build_default_real_effect_admission_policy()
    domain = _domain_from_closure(closure, admission_domain)
    tier = requested_implementation_tier or "tier1_metadata_only"
    if tier not in IMPLEMENTATION_TIERS:
        tier = "tier1_metadata_only"
    base = _closure_base_status(closure)
    warnings = _tuple(closure.get("warning_codes"))
    if base == "ready":
        status = "real_effect_candidate_recorded"
    elif base == "ready_with_warnings":
        status = "real_effect_candidate_recorded_with_warnings"
    elif base == "blocked":
        status = "real_effect_candidate_blocked"
    elif base == "contradicted":
        status = "real_effect_candidate_contradicted"
    else:
        status = "real_effect_candidate_incomplete"
    risks = tuple(sorted(set(_tuple(closure.get("risk_codes"))) | set(policy.risk_codes) | {"dry_run_closure_does_not_authorize_real_effects"}))
    provisional = RealEffectCapabilityCandidate(
        _digest_id("real-effect-candidate-", {"bundle": closure.get("bundle_id"), "domain": domain, "tier": tier, "status": status}),
        str(closure.get("bundle_id", "")),
        str(closure.get("digest", "")),
        domain,
        tier,
        status,
        ("metadata_only_admission_candidate", domain, tier),
        policy.required_planning_labels,
        _blocked_actions(domain, closure.get("blocked_actions")),
        warnings,
        risks,
        created_at,
        "",
    )
    return replace(provisional, digest=real_effect_capability_candidate_digest(provisional))


def evaluate_real_effect_capability_admission(
    candidate: RealEffectCapabilityCandidate | Mapping[str, Any],
    *,
    policy: RealEffectAdmissionPolicy | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> RealEffectCapabilityAdmissionDecision:
    c = _source_payload(candidate)
    policy = policy or build_default_real_effect_admission_policy()
    domain = str(c.get("admission_domain", ""))
    tier = str(c.get("requested_implementation_tier", "tier1_metadata_only"))
    candidate_status = str(c.get("candidate_status", ""))
    missing = tuple(label for label in policy.required_planning_labels if label not in ("dry_run_closure_bundle_required", "dry_run_effect_verification_required", "dry_run_postcondition_verification_required", "dry_run_rollback_rehearsal_required", "dry_run_audit_closure_required"))
    satisfied = tuple(label for label in policy.required_planning_labels if label not in missing)
    reasons: tuple[str, ...]
    if candidate_status.endswith("contradicted"):
        status = "real_effect_admission_contradicted"
        reasons = ("dry_run_closure_or_candidate_contradicted",)
    elif candidate_status.endswith("incomplete"):
        status = "real_effect_admission_incomplete"
        reasons = ("dry_run_closure_or_candidate_incomplete",)
    elif candidate_status.endswith("blocked"):
        status = "real_effect_admission_blocked"
        reasons = ("dry_run_closure_or_candidate_blocked",)
    elif domain in _DEFAULT_BLOCKED_DOMAINS or tier == "tier5_hardware_control_effect_future":
        status = "real_effect_admission_blocked"
        reasons = ("domain_blocked_by_default_for_real_effect_planning",)
    elif domain in _CONDITIONAL_DOMAINS or tier == "tier4_privileged_host_effect_future":
        status = "real_effect_admission_eligible_with_conditions"
        reasons = ("eligible_only_with_unmet_real_effect_planning_conditions",)
    elif domain in _LOW_RISK_DOMAINS:
        status = "real_effect_admission_eligible_for_planning"
        reasons = ("lower_risk_domain_eligible_for_implementation_planning_only",)
    else:
        status = "real_effect_admission_incomplete"
        reasons = ("unknown_or_unsupported_admission_domain",)
    if status == "real_effect_admission_eligible_for_planning":
        missing = ()
    warnings = _tuple(c.get("warning_codes"))
    risks = tuple(sorted(set(_tuple(c.get("risk_codes"))) | {"admission_decision_does_not_authorize_implementation_or_execution"}))
    provisional = RealEffectCapabilityAdmissionDecision(
        _digest_id("real-effect-admission-decision-", {"candidate": c.get("candidate_id"), "status": status}),
        str(c.get("candidate_id", "")),
        str(c.get("source_dry_run_closure_bundle_id", "")),
        domain,
        tier,
        status,
        satisfied,
        missing,
        _blocked_actions(domain, c.get("blocked_actions")),
        reasons,
        warnings,
        risks,
        created_at,
        "",
    )
    return replace(provisional, digest=real_effect_capability_admission_decision_digest(provisional))


def build_real_effect_implementation_plan_scaffold(
    decision: RealEffectCapabilityAdmissionDecision | Mapping[str, Any],
    *,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> RealEffectImplementationPlanScaffold:
    d = _source_payload(decision)
    status_map = {
        "real_effect_admission_eligible_for_planning": "real_effect_implementation_plan_scaffold_ready",
        "real_effect_admission_eligible_with_conditions": "real_effect_implementation_plan_scaffold_ready_with_conditions",
        "real_effect_admission_blocked": "real_effect_implementation_plan_scaffold_blocked",
        "real_effect_admission_incomplete": "real_effect_implementation_plan_scaffold_incomplete",
        "real_effect_admission_contradicted": "real_effect_implementation_plan_scaffold_contradicted",
    }
    domain = str(d.get("admission_domain", ""))
    provisional = RealEffectImplementationPlanScaffold(
        _digest_id("real-effect-plan-scaffold-", {"decision": d.get("decision_id"), "status": d.get("admission_status")}),
        str(d.get("decision_id", "")),
        str(d.get("candidate_id", "")),
        domain,
        str(d.get("implementation_tier", "")),
        status_map.get(str(d.get("admission_status")), "real_effect_implementation_plan_scaffold_incomplete"),
        ("backend_design_required_before_implementation", "no_backend_loaded"),
        ("effect_receipt_design_required", "real_effect_receipt_creation_blocked"),
        ("postcondition_check_design_required", "real_postcondition_check_blocked"),
        ("rollback_design_required", "real_rollback_execution_blocked"),
        ("production_audit_design_required", "production_audit_receipt_blocked"),
        ("operator_review_required", "security_review_required"),
        _blocked_actions(domain, d.get("blocked_actions")),
        _tuple(d.get("warning_codes")),
        tuple(sorted(set(_tuple(d.get("risk_codes"))) | {"plan_scaffold_does_not_start_implementation"})),
        created_at,
        "",
    )
    return replace(provisional, digest=real_effect_implementation_plan_scaffold_digest(provisional))


def build_real_effect_capability_block_receipt(
    candidate: RealEffectCapabilityCandidate | Mapping[str, Any],
    decision: RealEffectCapabilityAdmissionDecision | Mapping[str, Any] | None = None,
    *,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> RealEffectCapabilityBlockReceipt:
    c = _source_payload(candidate)
    d = _source_payload(decision) if decision is not None else {}
    domain = str(d.get("admission_domain", c.get("admission_domain", "")))
    admission_status = str(d.get("admission_status", "real_effect_admission_blocked"))
    if admission_status == "real_effect_admission_contradicted":
        block_status = "real_effect_block_receipt_contradicted"
    elif admission_status == "real_effect_admission_incomplete":
        block_status = "real_effect_block_receipt_incomplete"
    elif d.get("warning_codes") or c.get("warning_codes"):
        block_status = "real_effect_block_receipt_recorded_with_warnings"
    else:
        block_status = "real_effect_block_receipt_recorded"
    provisional = RealEffectCapabilityBlockReceipt(
        _digest_id("real-effect-block-receipt-", {"candidate": c.get("candidate_id"), "decision": d.get("decision_id"), "status": block_status}),
        str(c.get("candidate_id", "")),
        str(d.get("decision_id")) if d.get("decision_id") is not None else None,
        domain,
        block_status,
        _tuple(d.get("reason_codes")) or ("real_effect_capability_deferred_or_blocked",),
        _tuple(d.get("missing_planning_labels")) or _tuple(c.get("required_planning_labels")),
        _blocked_actions(domain, d.get("blocked_actions") or c.get("blocked_actions")),
        tuple(sorted(set(_tuple(c.get("warning_codes"))) | set(_tuple(d.get("warning_codes"))))),
        tuple(sorted(set(_tuple(c.get("risk_codes"))) | set(_tuple(d.get("risk_codes"))) | {"block_receipt_does_not_mutate_host"})),
        created_at,
        "",
    )
    return replace(provisional, digest=real_effect_capability_block_receipt_digest(provisional))


def build_real_effect_admission_bundle(
    candidate: RealEffectCapabilityCandidate | Mapping[str, Any],
    decision: RealEffectCapabilityAdmissionDecision | Mapping[str, Any],
    plan_or_block_receipt: RealEffectImplementationPlanScaffold | RealEffectCapabilityBlockReceipt | Mapping[str, Any],
    *,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> RealEffectAdmissionBundle:
    c = _source_payload(candidate)
    d = _source_payload(decision)
    p = _source_payload(plan_or_block_receipt)
    admission_status = str(d.get("admission_status", ""))
    if admission_status.endswith("contradicted"):
        status = "real_effect_admission_contradicted"
    elif admission_status.endswith("incomplete"):
        status = "real_effect_admission_incomplete"
    elif admission_status.endswith("blocked"):
        status = "real_effect_admission_blocked"
    else:
        status = admission_status
    plan_id = p.get("plan_id") if "plan_id" in p else None
    block_id = p.get("receipt_id") if "receipt_id" in p else None
    domain = str(d.get("admission_domain", c.get("admission_domain", "")))
    provisional = RealEffectAdmissionBundle(
        _digest_id("real-effect-admission-bundle-", {"candidate": c.get("candidate_id"), "decision": d.get("decision_id"), "posture": status}),
        str(c.get("candidate_id", "")),
        str(d.get("decision_id", "")),
        str(plan_id) if plan_id is not None else None,
        str(block_id) if block_id is not None else None,
        domain,
        status,
        _blocked_actions(domain, d.get("blocked_actions")),
        tuple(sorted(set(_tuple(c.get("warning_codes"))) | set(_tuple(d.get("warning_codes"))) | set(_tuple(p.get("warning_codes"))))),
        tuple(sorted(set(_tuple(c.get("risk_codes"))) | set(_tuple(d.get("risk_codes"))) | set(_tuple(p.get("risk_codes"))) | {"real_effect_admission_bundle_is_not_implementation"})),
        created_at,
        "",
    )
    return replace(provisional, digest=real_effect_admission_bundle_digest(provisional))


def _validate_common(payload: Mapping[str, Any], *, prefix: str, status_field: str, statuses: frozenset[str], only_field: str, digest_fn: Any) -> list[str]:
    findings: list[str] = []
    if not payload.get("metadata_only", False):
        findings.append(prefix + "not_metadata_only")
    if not payload.get(only_field, False):
        findings.append(prefix + f"missing_{only_field}")
    if payload.get(status_field) not in statuses:
        findings.append(prefix + f"unknown_{status_field}")
    for flag in _FORBIDDEN_TRUE_FLAGS:
        if payload.get(flag, False):
            findings.append(prefix + f"forbidden_flag:{flag}")
    if payload.get("implementation_not_started") is False:
        findings.append(prefix + "implementation_started")
    if payload.get("digest") and payload.get("digest") != digest_fn(payload):
        findings.append(prefix + "digest_mismatch")
    return findings


def validate_real_effect_capability_candidate(record: RealEffectCapabilityCandidate | Mapping[str, Any]) -> RealEffectAdmissionValidationResult:
    p = _source_payload(record)
    f = _validate_common(p, prefix="candidate:", status_field="candidate_status", statuses=CANDIDATE_STATUSES, only_field="candidate_only", digest_fn=real_effect_capability_candidate_digest)
    if p.get("admission_domain") not in ADMISSION_DOMAINS:
        f.append("candidate:unknown_admission_domain")
    if p.get("requested_implementation_tier") not in IMPLEMENTATION_TIERS:
        f.append("candidate:unknown_requested_implementation_tier")
    return RealEffectAdmissionValidationResult(not f, tuple(f))


def validate_real_effect_capability_admission_decision(record: RealEffectCapabilityAdmissionDecision | Mapping[str, Any]) -> RealEffectAdmissionValidationResult:
    p = _source_payload(record)
    f = _validate_common(p, prefix="decision:", status_field="admission_status", statuses=ADMISSION_STATUSES, only_field="admission_only", digest_fn=real_effect_capability_admission_decision_digest)
    if p.get("admission_domain") not in ADMISSION_DOMAINS:
        f.append("decision:unknown_admission_domain")
    return RealEffectAdmissionValidationResult(not f, tuple(f))


def validate_real_effect_implementation_plan_scaffold(record: RealEffectImplementationPlanScaffold | Mapping[str, Any]) -> RealEffectAdmissionValidationResult:
    p = _source_payload(record)
    f = _validate_common(p, prefix="plan_scaffold:", status_field="plan_status", statuses=PLAN_STATUSES, only_field="plan_scaffold_only", digest_fn=real_effect_implementation_plan_scaffold_digest)
    if p.get("admission_domain") not in ADMISSION_DOMAINS:
        f.append("plan_scaffold:unknown_admission_domain")
    return RealEffectAdmissionValidationResult(not f, tuple(f))


def validate_real_effect_capability_block_receipt(record: RealEffectCapabilityBlockReceipt | Mapping[str, Any]) -> RealEffectAdmissionValidationResult:
    p = _source_payload(record)
    f = _validate_common(p, prefix="block_receipt:", status_field="block_status", statuses=BLOCK_RECEIPT_STATUSES, only_field="block_receipt_only", digest_fn=real_effect_capability_block_receipt_digest)
    if p.get("admission_domain") not in ADMISSION_DOMAINS:
        f.append("block_receipt:unknown_admission_domain")
    return RealEffectAdmissionValidationResult(not f, tuple(f))


def validate_real_effect_admission_bundle(record: RealEffectAdmissionBundle | Mapping[str, Any]) -> RealEffectAdmissionValidationResult:
    p = _source_payload(record)
    f = _validate_common(p, prefix="admission_bundle:", status_field="bundle_status", statuses=ADMISSION_STATUSES, only_field="admission_bundle_only", digest_fn=real_effect_admission_bundle_digest)
    if p.get("admission_domain") not in ADMISSION_DOMAINS:
        f.append("admission_bundle:unknown_admission_domain")
    return RealEffectAdmissionValidationResult(not f, tuple(f))


def summarize_real_effect_capability_candidate(record: RealEffectCapabilityCandidate | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("candidate_id", "source_dry_run_closure_bundle_id", "admission_domain", "requested_implementation_tier", "candidate_status", "metadata_only", "candidate_only", "implementation_not_started", "real_backend_implemented", "real_fulfillment_performed", "real_effect_performed", "host_mutation_performed", "digest")}


def summarize_real_effect_capability_admission_decision(record: RealEffectCapabilityAdmissionDecision | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("decision_id", "candidate_id", "admission_domain", "implementation_tier", "admission_status", "missing_planning_labels", "metadata_only", "admission_only", "authorizes_implementation", "authorizes_execution", "real_backend_implemented", "real_fulfillment_performed", "real_effect_performed", "host_mutation_performed", "digest")}


def summarize_real_effect_implementation_plan_scaffold(record: RealEffectImplementationPlanScaffold | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("plan_id", "decision_id", "candidate_id", "admission_domain", "implementation_tier", "plan_status", "metadata_only", "plan_scaffold_only", "implementation_not_started", "backend_loaded", "backend_invoked", "real_fulfillment_performed", "real_effect_performed", "host_mutation_performed", "digest")}


def summarize_real_effect_capability_block_receipt(record: RealEffectCapabilityBlockReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("receipt_id", "candidate_id", "decision_id", "admission_domain", "block_status", "metadata_only", "block_receipt_only", "implementation_not_started", "real_backend_implemented", "real_fulfillment_performed", "host_mutation_performed", "digest")}


def summarize_real_effect_admission_bundle(record: RealEffectAdmissionBundle | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(record)
    return {k: p.get(k) for k in ("bundle_id", "candidate_id", "decision_id", "plan_id", "block_receipt_id", "admission_domain", "bundle_status", "metadata_only", "admission_bundle_only", "implementation_not_started", "authorizes_implementation", "authorizes_execution", "real_backend_implemented", "real_fulfillment_performed", "real_effect_performed", "host_mutation_performed", "digest")}


def build_real_effect_admission_wing(
    dry_run_closure_bundle: DryRunClosureBundle | Mapping[str, Any],
    *,
    admission_domain: str | None = None,
    requested_implementation_tier: str | None = None,
    policy: RealEffectAdmissionPolicy | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> RealEffectAdmissionWingRecords:
    policy = policy or build_default_real_effect_admission_policy()
    candidate = build_real_effect_capability_candidate(
        dry_run_closure_bundle,
        admission_domain=admission_domain,
        requested_implementation_tier=requested_implementation_tier,
        policy=policy,
        created_at=created_at,
    )
    decision = evaluate_real_effect_capability_admission(candidate, policy=policy, created_at=created_at)
    if decision.admission_status in {"real_effect_admission_eligible_for_planning", "real_effect_admission_eligible_with_conditions"}:
        plan_or_block = build_real_effect_implementation_plan_scaffold(decision, created_at=created_at)
    else:
        plan_or_block = build_real_effect_capability_block_receipt(candidate, decision, created_at=created_at)
    bundle = build_real_effect_admission_bundle(candidate, decision, plan_or_block, created_at=created_at)
    return RealEffectAdmissionWingRecords(candidate, decision, plan_or_block, bundle)
