"""Execution proof scaffolding for future SentientOS host effects.

This module is metadata-only/proof-only. It defines contracts for future effect
receipts, postcondition checks, rollback evidence, and execution readiness. It
never performs host actions, mutates host state, writes fan/PWM controls, changes
thermal or power settings, kills processes, restarts services, installs packages
or drivers, removes files, performs network activity, invokes providers, or
assembles prompts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.actuation_fulfillment import ACTUATION_FULFILLMENT_REHEARSAL_STATUSES, actuation_fulfillment_rehearsal_receipt_digest

EFFECT_RECEIPT_CONTRACT_STATUSES = frozenset({"effect_receipt_contract_ready", "effect_receipt_contract_ready_with_conditions", "effect_receipt_contract_blocked", "effect_receipt_contract_incomplete", "effect_receipt_contract_contradicted"})
FUTURE_EFFECT_RECEIPT_STATUSES = frozenset({"future_effect_receipt_schema_ready", "future_effect_receipt_schema_ready_with_conditions", "future_effect_receipt_blocked", "future_effect_receipt_incomplete", "future_effect_receipt_contradicted"})
POSTCONDITION_STATUSES = frozenset({"postcondition_plan_ready", "postcondition_plan_ready_with_conditions", "postcondition_plan_blocked", "postcondition_plan_incomplete", "postcondition_plan_contradicted", "postcondition_receipt_recorded", "postcondition_receipt_recorded_with_warnings", "postcondition_receipt_blocked", "postcondition_receipt_incomplete", "postcondition_receipt_contradicted"})
ROLLBACK_STATUSES = frozenset({"rollback_plan_ready", "rollback_plan_ready_with_conditions", "rollback_plan_blocked", "rollback_plan_incomplete", "rollback_plan_contradicted", "rollback_receipt_recorded", "rollback_receipt_recorded_with_warnings", "rollback_receipt_blocked", "rollback_receipt_incomplete", "rollback_receipt_contradicted"})
EXECUTION_READINESS_STATUSES = frozenset({"execution_readiness_for_authorization_review", "execution_readiness_for_authorization_review_with_conditions", "execution_readiness_blocked", "execution_readiness_incomplete", "execution_readiness_contradicted"})
EFFECT_DOMAINS = frozenset({"diagnostics_only", "operator_review", "resource_pressure_review", "thermal_safety_review", "disk_safety_review", "service_health_review", "future_cooling_effect", "future_power_effect", "future_cleanup_effect", "future_service_effect"})
EFFECT_BACKEND_CLASSES = frozenset({"no_backend_required", "diagnostic_backend_future", "cooling_backend_future", "power_backend_future", "cleanup_backend_future", "service_backend_future", "operator_manual_backend_future"})
REQUIRED_PROOF_GATES = frozenset({"control_plane_admission_required", "operator_or_policy_approval_required", "audit_receipt_required", "rollback_receipt_required", "rollback_plan_required", "panic_stop_required", "hardware_allowlist_required", "os_backend_declaration_required", "bounds_policy_required", "cooldown_policy_required", "rehearsal_required", "dry_run_required", "effect_receipt_required", "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required"})
BASE_PROOF_GATES = ("control_plane_admission_required", "operator_or_policy_approval_required", "audit_receipt_required", "rollback_receipt_required", "rollback_plan_required", "rehearsal_required", "dry_run_required", "effect_receipt_required", "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required")
BLOCKED_ACTION_LABELS = frozenset({"host_mutation_without_authorization", "fan_pwm_write_without_allowlist", "thermal_actuation_without_policy", "power_profile_mutation_without_policy", "process_kill_without_authorization", "service_restart_without_authorization", "package_install_without_authorization", "driver_install_without_authorization", "file_cleanup_without_scope", "file_delete_without_scope", "provider_invocation", "network_egress", "prompt_assembly", "federation_transport", "remote_execution"})

_DOMAIN_EFFECT: Mapping[str, str] = {
    "future_cooling_rehearsal": "future_cooling_effect",
    "future_power_rehearsal": "future_power_effect",
    "future_cleanup_rehearsal": "future_cleanup_effect",
    "future_service_rehearsal": "future_service_effect",
}
_ACTION_LABELS: Mapping[str, str] = {
    "host_mutation": "host_mutation_without_authorization",
    "fan_pwm_write": "fan_pwm_write_without_allowlist",
    "thermal_actuation": "thermal_actuation_without_policy",
    "power_profile_mutation": "power_profile_mutation_without_policy",
    "process_kill": "process_kill_without_authorization",
    "service_restart": "service_restart_without_authorization",
    "package_install": "package_install_without_authorization",
    "driver_install": "driver_install_without_authorization",
    "file_cleanup": "file_cleanup_without_scope",
    "file_delete": "file_delete_without_scope",
    "disk_cleanup_mutation": "file_cleanup_without_scope",
    "provider_invocation": "provider_invocation",
    "network_egress": "network_egress",
    "prompt_assembly": "prompt_assembly",
}
_DOMAIN_REQUIRED_GATES: Mapping[str, tuple[str, ...]] = {
    "future_cooling_effect": tuple(sorted(REQUIRED_PROOF_GATES)),
    "future_power_effect": ("control_plane_admission_required", "operator_or_policy_approval_required", "audit_receipt_required", "rollback_receipt_required", "rollback_plan_required", "panic_stop_required", "os_backend_declaration_required", "bounds_policy_required", "rehearsal_required", "dry_run_required", "effect_receipt_required", "postcondition_check_required", "runtime_supervisor_observation_required", "immutable_trace_required"),
    "future_cleanup_effect": BASE_PROOF_GATES + ("panic_stop_required",),
    "future_service_effect": BASE_PROOF_GATES + ("panic_stop_required",),
}
_DOMAIN_EXTRA_AUTHORITY: Mapping[str, tuple[str, ...]] = {
    "future_cleanup_effect": ("path_or_file_scope_required",),
    "future_service_effect": ("service_scope_required",),
}
_DOMAIN_REQUIRED_BLOCKS: Mapping[str, tuple[str, ...]] = {
    "future_cooling_effect": ("fan_pwm_write_without_allowlist", "thermal_actuation_without_policy"),
    "future_power_effect": ("power_profile_mutation_without_policy",),
    "future_cleanup_effect": ("file_cleanup_without_scope", "file_delete_without_scope"),
    "future_service_effect": ("service_restart_without_authorization", "process_kill_without_authorization"),
}

@dataclass(frozen=True)
class EffectProofValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()

@dataclass(frozen=True)
class EffectReceiptContract:
    contract_id: str
    source_rehearsal_receipt_id: str
    source_rehearsal_receipt_digest: str
    fulfillment_domain: str
    backend_class: str
    effect_domain: str
    required_proof_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    required_authority_refs: tuple[str, ...]
    required_precondition_labels: tuple[str, ...]
    required_postcondition_labels: tuple[str, ...]
    required_rollback_labels: tuple[str, ...]
    required_audit_labels: tuple[str, ...]
    required_supervisor_labels: tuple[str, ...]
    status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    contract_only: bool = True
    effect_performed: bool = False
    host_mutation_performed: bool = False
    authorization_granted: bool = False
    fulfillment_granted: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class FutureEffectReceipt:
    receipt_id: str
    contract_id: str
    source_rehearsal_receipt_id: str
    source_rehearsal_receipt_digest: str
    planned_effect_domain: str
    backend_class: str
    status: str
    required_authority_refs: tuple[str, ...]
    required_precondition_labels: tuple[str, ...]
    required_postcondition_labels: tuple[str, ...]
    required_rollback_labels: tuple[str, ...]
    required_audit_labels: tuple[str, ...]
    required_supervisor_labels: tuple[str, ...]
    expected_effect_summary: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    schema_only: bool = True
    future_use_only: bool = True
    effect_performed: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    does_not_authorize_fulfillment: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class PostconditionCheckPlan:
    plan_id: str
    contract_id: str
    source_rehearsal_receipt_id: str
    effect_domain: str
    postcondition_labels: tuple[str, ...]
    observation_sources: tuple[str, ...]
    expected_state_labels: tuple[str, ...]
    forbidden_state_labels: tuple[str, ...]
    required_evidence_labels: tuple[str, ...]
    status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    plan_only: bool = True
    check_performed: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class PostconditionCheckReceipt:
    receipt_id: str
    plan_id: str
    contract_id: str
    source_effect_receipt_id_or_placeholder: str
    observed_postcondition_labels: tuple[str, ...]
    missing_postcondition_labels: tuple[str, ...]
    contradicted_postcondition_labels: tuple[str, ...]
    status: str
    evidence_summary: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    receipt_only: bool = True
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    check_is_schema_or_rehearsal_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class RollbackPlan:
    plan_id: str
    contract_id: str
    effect_domain: str
    rollback_strategy_labels: tuple[str, ...]
    rollback_preconditions: tuple[str, ...]
    rollback_steps: tuple[str, ...]
    rollback_postconditions: tuple[str, ...]
    rollback_blocked_actions: tuple[str, ...]
    status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    plan_only: bool = True
    rollback_performed: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class RollbackReceipt:
    receipt_id: str
    plan_id: str
    contract_id: str
    source_effect_receipt_id_or_placeholder: str
    rollback_status: str
    rollback_evidence_summary: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    receipt_only: bool = True
    rollback_performed: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    rollback_is_schema_or_rehearsal_only: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class ExecutionReadinessManifest:
    manifest_id: str
    source_rehearsal_receipt_id: str
    source_rehearsal_receipt_digest: str
    effect_contract_id: str
    future_effect_receipt_id: str
    postcondition_plan_id: str
    rollback_plan_id: str
    runtime_supervisor_report_id: str | None
    readiness_status: str
    effect_domain: str
    backend_class: str
    required_proof_gates: tuple[str, ...]
    satisfied_proof_gates: tuple[str, ...]
    missing_proof_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    readiness_only: bool = True
    authorization_granted: bool = False
    fulfillment_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

class ExecutionProofWingRecords(NamedTuple):
    effect_contract: EffectReceiptContract
    future_effect_receipt: FutureEffectReceipt
    postcondition_plan: PostconditionCheckPlan
    rollback_plan: RollbackPlan
    execution_readiness_manifest: ExecutionReadinessManifest

def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)

def _digest_payload(prefix: str, payload: Mapping[str, Any], length: int = 24) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:length]

def _record_digest(record: Any) -> str:
    payload = record.to_dict()
    if "digest" in payload:
        payload["digest"] = ""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

def _source_digest(receipt: Any) -> str:
    digest = str(getattr(receipt, "digest", "") or "")
    return digest or actuation_fulfillment_rehearsal_receipt_digest(receipt)

def _effect_domain(receipt: Any) -> str:
    domain = str(getattr(receipt, "fulfillment_domain", "diagnostics_only") or "diagnostics_only")
    return _DOMAIN_EFFECT.get(domain, domain if domain in EFFECT_DOMAINS else "diagnostics_only")

def _blocked_actions(source_actions: Sequence[str], effect_domain: str) -> tuple[str, ...]:
    labels = {_ACTION_LABELS.get(str(action), str(action)) for action in source_actions}
    labels.update({"host_mutation_without_authorization", "provider_invocation", "network_egress", "prompt_assembly", "federation_transport", "remote_execution"})
    labels.update(_DOMAIN_REQUIRED_BLOCKS.get(effect_domain, ()))
    return tuple(sorted(label for label in labels if label in BLOCKED_ACTION_LABELS))

def _source_findings(receipt: Any) -> tuple[str, ...]:
    findings: list[str] = []
    if str(getattr(receipt, "rehearsal_status", "")) not in ACTUATION_FULFILLMENT_REHEARSAL_STATUSES:
        findings.append("source_rehearsal_unknown_status")
    required_true = {"rehearsal_only": True, "dry_run_only": True, "does_not_execute": True, "does_not_mutate_host": True, "does_not_authorize_fulfillment": True, "effect_not_performed": True}
    for flag in required_true:
        if not getattr(receipt, flag, True):
            findings.append(f"source_rehearsal_claims_authority_or_effect:{flag}")
    forbidden_false = ("effect_performed", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "file_delete_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed")
    for flag in forbidden_false:
        if getattr(receipt, flag, False):
            findings.append(f"source_rehearsal_claims_forbidden_effect:{flag}")
    return tuple(findings)

def _status_kind(rehearsal_status: str, findings: Sequence[str], warnings: Sequence[str]) -> str:
    if findings or rehearsal_status.endswith("contradicted"):
        return "contradicted"
    if rehearsal_status.endswith("incomplete"):
        return "incomplete"
    if rehearsal_status.endswith("blocked"):
        return "blocked"
    if warnings or rehearsal_status.endswith("with_warnings"):
        return "conditions"
    return "ready"

def _contract_status(kind: str) -> str:
    return {"contradicted":"effect_receipt_contract_contradicted","incomplete":"effect_receipt_contract_incomplete","blocked":"effect_receipt_contract_blocked","conditions":"effect_receipt_contract_ready_with_conditions"}.get(kind, "effect_receipt_contract_ready")

def _future_status(kind: str) -> str:
    return {"contradicted":"future_effect_receipt_contradicted","incomplete":"future_effect_receipt_incomplete","blocked":"future_effect_receipt_blocked","conditions":"future_effect_receipt_schema_ready_with_conditions"}.get(kind, "future_effect_receipt_schema_ready")

def _plan_status(kind: str, prefix: str) -> str:
    suffix = {"contradicted":"contradicted","incomplete":"incomplete","blocked":"blocked","conditions":"ready_with_conditions"}.get(kind, "ready")
    return f"{prefix}_{suffix}"

def _readiness_status(kind: str) -> str:
    return {"contradicted":"execution_readiness_contradicted","incomplete":"execution_readiness_incomplete","blocked":"execution_readiness_blocked","conditions":"execution_readiness_for_authorization_review_with_conditions"}.get(kind, "execution_readiness_for_authorization_review")

def build_effect_receipt_contract(receipt: Any) -> EffectReceiptContract:
    source_id = str(getattr(receipt, "receipt_id", ""))
    source_digest = _source_digest(receipt)
    effect_domain = _effect_domain(receipt)
    gates = tuple(sorted(set(getattr(receipt, "required_future_gates", ()) or ()) | set(_DOMAIN_REQUIRED_GATES.get(effect_domain, BASE_PROOF_GATES))))
    blocked = _blocked_actions(tuple(getattr(receipt, "blocked_actions", ()) or ()), effect_domain)
    warnings = tuple(sorted(set(getattr(receipt, "warning_codes", ()) or ())))
    risks = tuple(sorted(set(getattr(receipt, "risk_codes", ()) or ())))
    findings = _source_findings(receipt)
    kind = _status_kind(str(getattr(receipt, "rehearsal_status", "")), findings, warnings)
    if not gates:
        kind = "incomplete"
    material = {"source": source_id, "digest": source_digest, "effect_domain": effect_domain, "gates": gates, "blocked": blocked}
    postconditions = tuple(getattr(receipt, "expected_postconditions", ()) or ("future_effect_postconditions_declared",))
    rollback = tuple(getattr(receipt, "rollback_requirements", ()) or ("rollback_plan_required",))
    return EffectReceiptContract(
        contract_id=_digest_payload("erc_", material), source_rehearsal_receipt_id=source_id, source_rehearsal_receipt_digest=source_digest,
        fulfillment_domain=str(getattr(receipt, "fulfillment_domain", "diagnostics_only")), backend_class=str(getattr(receipt, "backend_class", "no_backend_required")), effect_domain=effect_domain,
        required_proof_gates=gates, blocked_actions=blocked, required_authority_refs=tuple(sorted(("control_plane_admission", "operator_or_policy_approval") + _DOMAIN_EXTRA_AUTHORITY.get(effect_domain, ()))),
        required_precondition_labels=tuple(sorted(("dry_run_rehearsal_receipt", "source_rehearsal_integrity") + _DOMAIN_EXTRA_AUTHORITY.get(effect_domain, ()))),
        required_postcondition_labels=postconditions, required_rollback_labels=rollback, required_audit_labels=("audit_receipt_required", "immutable_trace_required"), required_supervisor_labels=("runtime_supervisor_observation_required",),
        status=_contract_status(kind), warning_codes=tuple(sorted(set(warnings + findings))), risk_codes=risks,
    )

def build_future_effect_receipt_schema(contract: EffectReceiptContract, *, created_at: str = "1970-01-01T00:00:00+00:00") -> FutureEffectReceipt:
    kind = "ready"
    if contract.status.endswith("contradicted"): kind = "contradicted"
    elif contract.status.endswith("incomplete"): kind = "incomplete"
    elif contract.status.endswith("blocked"): kind = "blocked"
    elif contract.status.endswith("conditions"): kind = "conditions"
    material = {"contract": contract.contract_id, "domain": contract.effect_domain, "created_at": created_at}
    provisional = FutureEffectReceipt(_digest_payload("fers_", material), contract.contract_id, contract.source_rehearsal_receipt_id, contract.source_rehearsal_receipt_digest, contract.effect_domain, contract.backend_class, _future_status(kind), contract.required_authority_refs, contract.required_precondition_labels, contract.required_postcondition_labels, contract.required_rollback_labels, contract.required_audit_labels, contract.required_supervisor_labels, ("schema_placeholder_only", "not_proof_that_effect_occurred"), contract.blocked_actions, contract.warning_codes, contract.risk_codes, created_at, "")
    return replace(provisional, digest=future_effect_receipt_digest(provisional))

def build_postcondition_check_plan(contract: EffectReceiptContract) -> PostconditionCheckPlan:
    kind = "contradicted" if contract.status.endswith("contradicted") else "incomplete" if contract.status.endswith("incomplete") else "blocked" if contract.status.endswith("blocked") else "conditions" if contract.status.endswith("conditions") else "ready"
    labels = contract.required_postcondition_labels or ("future_state_observed",)
    material = {"contract": contract.contract_id, "labels": labels}
    return PostconditionCheckPlan(_digest_payload("pcp_", material), contract.contract_id, contract.source_rehearsal_receipt_id, contract.effect_domain, labels, ("runtime_supervisor_snapshot", "effect_receipt", "audit_trace"), tuple(f"expected:{label}" for label in labels), contract.blocked_actions, ("postcondition_evidence_summary", "immutable_trace"), _plan_status(kind, "postcondition_plan"), contract.warning_codes, contract.risk_codes)

def build_postcondition_check_receipt(plan: PostconditionCheckPlan, *, observed_postcondition_labels: Sequence[str] = (), source_effect_receipt_id_or_placeholder: str = "future-effect-receipt-placeholder", created_at: str = "1970-01-01T00:00:00+00:00") -> PostconditionCheckReceipt:
    observed = tuple(sorted(str(x) for x in observed_postcondition_labels))
    missing = tuple(label for label in plan.postcondition_labels if label not in observed)
    status = "postcondition_receipt_recorded" if not missing else "postcondition_receipt_recorded_with_warnings"
    provisional = PostconditionCheckReceipt(_digest_payload("pcr_", {"plan": plan.plan_id, "observed": observed, "created_at": created_at}), plan.plan_id, plan.contract_id, source_effect_receipt_id_or_placeholder, observed, missing, (), status, ("schema_or_rehearsal_only", "no_effect_verified"), plan.warning_codes, plan.risk_codes, created_at, "")
    return replace(provisional, digest=postcondition_check_receipt_digest(provisional))

def build_rollback_plan(contract: EffectReceiptContract) -> RollbackPlan:
    kind = "contradicted" if contract.status.endswith("contradicted") else "incomplete" if contract.status.endswith("incomplete") else "blocked" if contract.status.endswith("blocked") else "conditions" if contract.status.endswith("conditions") else "ready"
    steps = contract.required_rollback_labels or ("future_rollback_steps_declared",)
    material = {"contract": contract.contract_id, "steps": steps}
    return RollbackPlan(_digest_payload("rbp_", material), contract.contract_id, contract.effect_domain, ("restore_prior_state", "operator_review_before_rollback"), ("rollback_authority_required", "effect_receipt_required"), steps, ("rollback_postconditions_checked",), contract.blocked_actions, _plan_status(kind, "rollback_plan"), contract.warning_codes, contract.risk_codes)

def build_rollback_receipt(plan: RollbackPlan, *, source_effect_receipt_id_or_placeholder: str = "future-effect-receipt-placeholder", created_at: str = "1970-01-01T00:00:00+00:00") -> RollbackReceipt:
    provisional = RollbackReceipt(_digest_payload("rbr_", {"plan": plan.plan_id, "created_at": created_at}), plan.plan_id, plan.contract_id, source_effect_receipt_id_or_placeholder, "rollback_receipt_recorded", ("schema_or_rehearsal_only", "rollback_not_performed"), plan.warning_codes, plan.risk_codes, created_at, "")
    return replace(provisional, digest=rollback_receipt_digest(provisional))

def build_execution_readiness_manifest(contract: EffectReceiptContract, future_receipt: FutureEffectReceipt, postcondition_plan: PostconditionCheckPlan, rollback_plan: RollbackPlan, *, runtime_supervisor_report: Any | None = None, satisfied_proof_gates: Sequence[str] | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> ExecutionReadinessManifest:
    supplied = set(str(gate) for gate in (satisfied_proof_gates if satisfied_proof_gates is not None else contract.required_proof_gates))
    if runtime_supervisor_report is not None:
        supplied.add("runtime_supervisor_observation_required")
    missing = tuple(sorted(set(contract.required_proof_gates) - supplied))
    kind = "ready"
    if contract.status.endswith("contradicted") or future_receipt.status.endswith("contradicted") or postcondition_plan.status.endswith("contradicted") or rollback_plan.status.endswith("contradicted"):
        kind = "contradicted"
    elif missing or contract.status.endswith("incomplete"):
        kind = "incomplete"
    elif contract.status.endswith("blocked"):
        kind = "blocked"
    elif contract.status.endswith("conditions") or future_receipt.status.endswith("conditions"):
        kind = "conditions"
    material = {"contract": contract.contract_id, "future": future_receipt.receipt_id, "post": postcondition_plan.plan_id, "rollback": rollback_plan.plan_id, "supervisor": getattr(runtime_supervisor_report, "report_id", None), "created_at": created_at}
    provisional = ExecutionReadinessManifest(_digest_payload("erm_", material), contract.source_rehearsal_receipt_id, contract.source_rehearsal_receipt_digest, contract.contract_id, future_receipt.receipt_id, postcondition_plan.plan_id, rollback_plan.plan_id, getattr(runtime_supervisor_report, "report_id", None), _readiness_status(kind), contract.effect_domain, contract.backend_class, contract.required_proof_gates, tuple(sorted(supplied & set(contract.required_proof_gates))), missing, contract.blocked_actions, tuple(sorted(set(contract.warning_codes + getattr(runtime_supervisor_report, "warning_codes", ()) ))), tuple(sorted(set(contract.risk_codes + getattr(runtime_supervisor_report, "risk_codes", ())))), created_at, "")
    return replace(provisional, digest=execution_readiness_manifest_digest(provisional))

def build_execution_proof_wing_for_rehearsal_receipt(receipt: Any, *, runtime_supervisor_report: Any | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> ExecutionProofWingRecords:
    contract = build_effect_receipt_contract(receipt)
    future_receipt = build_future_effect_receipt_schema(contract, created_at=created_at)
    postcondition_plan = build_postcondition_check_plan(contract)
    rollback_plan = build_rollback_plan(contract)
    manifest = build_execution_readiness_manifest(contract, future_receipt, postcondition_plan, rollback_plan, runtime_supervisor_report=runtime_supervisor_report, created_at=created_at)
    return ExecutionProofWingRecords(contract, future_receipt, postcondition_plan, rollback_plan, manifest)

# Digest helpers
def effect_receipt_contract_digest(contract: EffectReceiptContract) -> str: return _record_digest(contract)
def future_effect_receipt_digest(receipt: FutureEffectReceipt) -> str: return _record_digest(receipt)
def postcondition_check_plan_digest(plan: PostconditionCheckPlan) -> str: return _record_digest(plan)
def postcondition_check_receipt_digest(receipt: PostconditionCheckReceipt) -> str: return _record_digest(receipt)
def rollback_plan_digest(plan: RollbackPlan) -> str: return _record_digest(plan)
def rollback_receipt_digest(receipt: RollbackReceipt) -> str: return _record_digest(receipt)
def execution_readiness_manifest_digest(manifest: ExecutionReadinessManifest) -> str: return _record_digest(manifest)

def _validate_common(value: Any, prefix: str) -> list[str]:
    findings: list[str] = []
    required_false = ("authorization_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "process_kill_performed", "service_restart_performed", "package_install_performed", "driver_install_performed", "file_cleanup_performed", "file_delete_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed")
    for flag in required_false:
        if getattr(value, flag, False):
            findings.append(f"{prefix}_forbidden_flag:{flag}")
    for flag in ("metadata_only", "readiness_only", "schema_only", "future_use_only", "does_not_execute", "does_not_mutate_host", "does_not_authorize_fulfillment", "contract_only", "plan_only", "receipt_only"):
        if hasattr(value, flag) and not getattr(value, flag):
            findings.append(f"{prefix}_missing_non_effect_flag:{flag}")
    return findings

def validate_effect_receipt_contract(contract: EffectReceiptContract) -> EffectProofValidationResult:
    findings = _validate_common(contract, "contract")
    if not contract.contract_id: findings.append("missing_contract_id")
    if contract.effect_domain not in EFFECT_DOMAINS: findings.append("unknown_effect_domain")
    if contract.backend_class not in EFFECT_BACKEND_CLASSES: findings.append("unknown_backend_class")
    if contract.status not in EFFECT_RECEIPT_CONTRACT_STATUSES: findings.append("unknown_contract_status")
    for gate in BASE_PROOF_GATES:
        if gate not in contract.required_proof_gates: findings.append(f"contract_missing_base_gate:{gate}")
    for label in _DOMAIN_REQUIRED_BLOCKS.get(contract.effect_domain, ()):
        if label not in contract.blocked_actions: findings.append(f"contract_missing_blocked_action:{label}")
    return EffectProofValidationResult(not findings, tuple(findings))

def validate_future_effect_receipt_schema(receipt: FutureEffectReceipt) -> EffectProofValidationResult:
    findings = _validate_common(receipt, "future_receipt")
    if receipt.status not in FUTURE_EFFECT_RECEIPT_STATUSES: findings.append("unknown_future_receipt_status")
    if receipt.digest and receipt.digest != future_effect_receipt_digest(receipt): findings.append("future_receipt_digest_mismatch")
    return EffectProofValidationResult(not findings, tuple(findings))

def validate_postcondition_check_plan(plan: PostconditionCheckPlan) -> EffectProofValidationResult:
    findings = _validate_common(plan, "postcondition_plan")
    if plan.status not in POSTCONDITION_STATUSES: findings.append("unknown_postcondition_plan_status")
    if not plan.postcondition_labels: findings.append("missing_postcondition_labels")
    return EffectProofValidationResult(not findings, tuple(findings))

def validate_postcondition_check_receipt(receipt: PostconditionCheckReceipt) -> EffectProofValidationResult:
    findings = _validate_common(receipt, "postcondition_receipt")
    if receipt.status not in POSTCONDITION_STATUSES: findings.append("unknown_postcondition_receipt_status")
    if receipt.digest and receipt.digest != postcondition_check_receipt_digest(receipt): findings.append("postcondition_receipt_digest_mismatch")
    return EffectProofValidationResult(not findings, tuple(findings))

def validate_rollback_plan(plan: RollbackPlan) -> EffectProofValidationResult:
    findings = _validate_common(plan, "rollback_plan")
    if plan.status not in ROLLBACK_STATUSES: findings.append("unknown_rollback_plan_status")
    if not plan.rollback_steps: findings.append("missing_rollback_steps")
    return EffectProofValidationResult(not findings, tuple(findings))

def validate_rollback_receipt(receipt: RollbackReceipt) -> EffectProofValidationResult:
    findings = _validate_common(receipt, "rollback_receipt")
    if receipt.rollback_status not in ROLLBACK_STATUSES: findings.append("unknown_rollback_receipt_status")
    if receipt.digest and receipt.digest != rollback_receipt_digest(receipt): findings.append("rollback_receipt_digest_mismatch")
    return EffectProofValidationResult(not findings, tuple(findings))

def validate_execution_readiness_manifest(manifest: ExecutionReadinessManifest) -> EffectProofValidationResult:
    findings = _validate_common(manifest, "readiness_manifest")
    if manifest.readiness_status not in EXECUTION_READINESS_STATUSES: findings.append("unknown_readiness_status")
    if manifest.digest and manifest.digest != execution_readiness_manifest_digest(manifest): findings.append("readiness_digest_mismatch")
    missing = tuple(sorted(set(manifest.required_proof_gates) - set(manifest.satisfied_proof_gates)))
    if tuple(manifest.missing_proof_gates) != missing: findings.append("readiness_missing_gate_mismatch")
    if missing and manifest.readiness_status not in {"execution_readiness_incomplete", "execution_readiness_blocked", "execution_readiness_contradicted"}: findings.append("readiness_missing_gates_not_blocked_or_incomplete")
    return EffectProofValidationResult(not findings, tuple(findings))

def summarize_effect_receipt_contract(contract: EffectReceiptContract) -> dict[str, Any]: return {"contract_id": contract.contract_id, "effect_domain": contract.effect_domain, "backend_class": contract.backend_class, "status": contract.status, "proof_gate_count": len(contract.required_proof_gates), "blocked_action_count": len(contract.blocked_actions), "metadata_only": contract.metadata_only, "contract_only": contract.contract_only, "effect_performed": contract.effect_performed, "host_mutation_performed": contract.host_mutation_performed, "authorization_granted": contract.authorization_granted, "fulfillment_granted": contract.fulfillment_granted}
def summarize_future_effect_receipt_schema(receipt: FutureEffectReceipt) -> dict[str, Any]: return {"receipt_id": receipt.receipt_id, "contract_id": receipt.contract_id, "planned_effect_domain": receipt.planned_effect_domain, "status": receipt.status, "schema_only": receipt.schema_only, "future_use_only": receipt.future_use_only, "effect_performed": receipt.effect_performed, "does_not_execute": receipt.does_not_execute, "does_not_mutate_host": receipt.does_not_mutate_host, "does_not_authorize_fulfillment": receipt.does_not_authorize_fulfillment}
def summarize_postcondition_check_plan(plan: PostconditionCheckPlan) -> dict[str, Any]: return {"plan_id": plan.plan_id, "contract_id": plan.contract_id, "effect_domain": plan.effect_domain, "status": plan.status, "metadata_only": plan.metadata_only, "plan_only": plan.plan_only, "check_performed": plan.check_performed, "host_mutation_performed": plan.host_mutation_performed}
def summarize_postcondition_check_receipt(receipt: PostconditionCheckReceipt) -> dict[str, Any]: return {"receipt_id": receipt.receipt_id, "plan_id": receipt.plan_id, "status": receipt.status, "receipt_only": receipt.receipt_only, "does_not_execute": receipt.does_not_execute, "does_not_mutate_host": receipt.does_not_mutate_host, "check_is_schema_or_rehearsal_only": receipt.check_is_schema_or_rehearsal_only}
def summarize_rollback_plan(plan: RollbackPlan) -> dict[str, Any]: return {"plan_id": plan.plan_id, "contract_id": plan.contract_id, "effect_domain": plan.effect_domain, "status": plan.status, "metadata_only": plan.metadata_only, "plan_only": plan.plan_only, "rollback_performed": plan.rollback_performed, "host_mutation_performed": plan.host_mutation_performed}
def summarize_rollback_receipt(receipt: RollbackReceipt) -> dict[str, Any]: return {"receipt_id": receipt.receipt_id, "plan_id": receipt.plan_id, "rollback_status": receipt.rollback_status, "receipt_only": receipt.receipt_only, "rollback_performed": receipt.rollback_performed, "does_not_execute": receipt.does_not_execute, "does_not_mutate_host": receipt.does_not_mutate_host, "rollback_is_schema_or_rehearsal_only": receipt.rollback_is_schema_or_rehearsal_only}
def summarize_execution_readiness_manifest(manifest: ExecutionReadinessManifest) -> dict[str, Any]: return {"manifest_id": manifest.manifest_id, "effect_contract_id": manifest.effect_contract_id, "future_effect_receipt_id": manifest.future_effect_receipt_id, "readiness_status": manifest.readiness_status, "effect_domain": manifest.effect_domain, "metadata_only": manifest.metadata_only, "readiness_only": manifest.readiness_only, "authorization_granted": manifest.authorization_granted, "fulfillment_granted": manifest.fulfillment_granted, "effect_performed": manifest.effect_performed, "host_mutation_performed": manifest.host_mutation_performed, "missing_proof_gate_count": len(manifest.missing_proof_gates)}
