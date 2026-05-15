"""Metadata-only fulfillment executor contract readiness records.

This wing follows fulfillment authorization consumption and defines the proof a
future host fulfillment executor would have to provide before a real backend can
exist. It is strictly contract/readiness-only: it does not execute or fulfill
host actions, mutate host state, load or invoke backends, write fan/PWM controls,
change thermal or power settings, restart services, clean files, make network
calls, invoke providers, assemble prompts, or call control-plane admission.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.fulfillment_authorization import FulfillmentAuthorizationConsumptionReceipt

CONTRACT_STATUSES = frozenset({
    "fulfillment_executor_contract_ready",
    "fulfillment_executor_contract_ready_with_conditions",
    "fulfillment_executor_contract_blocked",
    "fulfillment_executor_contract_incomplete",
    "fulfillment_executor_contract_contradicted",
})
BACKEND_DECLARATION_STATUSES = frozenset({
    "executor_backend_declared",
    "executor_backend_declared_with_warnings",
    "executor_backend_blocked",
    "executor_backend_incomplete",
    "executor_backend_contradicted",
})
PRECONDITION_STATUSES = frozenset({
    "executor_preconditions_ready",
    "executor_preconditions_ready_with_conditions",
    "executor_preconditions_blocked",
    "executor_preconditions_incomplete",
    "executor_preconditions_contradicted",
})
DRY_RUN_PLAN_STATUSES = frozenset({
    "executor_dry_run_plan_ready",
    "executor_dry_run_plan_ready_with_conditions",
    "executor_dry_run_plan_blocked",
    "executor_dry_run_plan_incomplete",
    "executor_dry_run_plan_contradicted",
})
ADMISSION_PACKET_STATUSES = frozenset({
    "executor_admission_packet_ready",
    "executor_admission_packet_ready_with_conditions",
    "executor_admission_packet_blocked",
    "executor_admission_packet_incomplete",
    "executor_admission_packet_contradicted",
})
READINESS_RECEIPT_STATUSES = frozenset({
    "executor_contract_readiness_recorded",
    "executor_contract_readiness_recorded_with_warnings",
    "executor_contract_readiness_blocked",
    "executor_contract_readiness_incomplete",
    "executor_contract_readiness_contradicted",
})
EXECUTOR_DOMAINS = frozenset({
    "diagnostics_executor_contract",
    "operator_review_executor_contract",
    "resource_pressure_executor_contract",
    "thermal_safety_executor_contract",
    "future_cooling_executor_contract",
    "future_power_executor_contract",
    "future_cleanup_executor_contract",
    "future_service_executor_contract",
})
BACKEND_CLASSES = frozenset({
    "diagnostic_backend_future",
    "operator_manual_backend_future",
    "cooling_backend_future",
    "power_backend_future",
    "cleanup_backend_future",
    "service_backend_future",
})
REQUIRED_EXECUTOR_LABELS = frozenset({
    "fulfillment_authorization_consumption_required",
    "local_authorization_grant_required",
    "scope_match_required",
    "grant_not_expired_required",
    "grant_not_revoked_required",
    "backend_declaration_required",
    "executor_identity_required",
    "dry_run_plan_required",
    "precondition_manifest_required",
    "control_plane_admission_required_for_future_execution",
    "effect_receipt_required_for_future_execution",
    "postcondition_check_required_for_future_execution",
    "rollback_receipt_required_for_future_execution",
    "audit_receipt_required_for_future_execution",
    "runtime_supervisor_observation_required",
    "immutable_trace_required",
    "panic_stop_required",
    "safety_gates_required",
})
BLOCKED_ACTION_LABELS = frozenset({
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
_DOMAIN_TO_EXECUTOR = {
    "diagnostics_fulfillment_authorization": "diagnostics_executor_contract",
    "operator_review_fulfillment_authorization": "operator_review_executor_contract",
    "resource_pressure_fulfillment_authorization": "resource_pressure_executor_contract",
    "thermal_safety_fulfillment_authorization": "thermal_safety_executor_contract",
    "future_cooling_fulfillment_authorization": "future_cooling_executor_contract",
    "future_power_fulfillment_authorization": "future_power_executor_contract",
    "future_cleanup_fulfillment_authorization": "future_cleanup_executor_contract",
    "future_service_fulfillment_authorization": "future_service_executor_contract",
}
_EXECUTOR_TO_BACKEND = {
    "diagnostics_executor_contract": "diagnostic_backend_future",
    "operator_review_executor_contract": "operator_manual_backend_future",
    "resource_pressure_executor_contract": "diagnostic_backend_future",
    "thermal_safety_executor_contract": "diagnostic_backend_future",
    "future_cooling_executor_contract": "cooling_backend_future",
    "future_power_executor_contract": "power_backend_future",
    "future_cleanup_executor_contract": "cleanup_backend_future",
    "future_service_executor_contract": "service_backend_future",
}
_DOMAIN_BLOCKS = {
    "future_cooling_executor_contract": ("fan_pwm_write", "thermal_actuation"),
    "future_power_executor_contract": ("power_profile_mutation",),
    "future_cleanup_executor_contract": ("file_cleanup", "file_delete"),
    "future_service_executor_contract": ("service_restart", "process_kill"),
}
_CONSUMPTION_STATUS_MAP = {
    "fulfillment_authorization_consumption_recorded": ("fulfillment_executor_contract_ready", "executor_backend_declared", "executor_preconditions_ready", "executor_dry_run_plan_ready", "executor_admission_packet_ready", "executor_contract_readiness_recorded"),
    "fulfillment_authorization_consumption_recorded_with_warnings": ("fulfillment_executor_contract_ready_with_conditions", "executor_backend_declared_with_warnings", "executor_preconditions_ready_with_conditions", "executor_dry_run_plan_ready_with_conditions", "executor_admission_packet_ready_with_conditions", "executor_contract_readiness_recorded_with_warnings"),
    "fulfillment_authorization_consumption_blocked": ("fulfillment_executor_contract_blocked", "executor_backend_blocked", "executor_preconditions_blocked", "executor_dry_run_plan_blocked", "executor_admission_packet_blocked", "executor_contract_readiness_blocked"),
    "fulfillment_authorization_consumption_expired": ("fulfillment_executor_contract_blocked", "executor_backend_blocked", "executor_preconditions_blocked", "executor_dry_run_plan_blocked", "executor_admission_packet_blocked", "executor_contract_readiness_blocked"),
    "fulfillment_authorization_consumption_revoked": ("fulfillment_executor_contract_blocked", "executor_backend_blocked", "executor_preconditions_blocked", "executor_dry_run_plan_blocked", "executor_admission_packet_blocked", "executor_contract_readiness_blocked"),
    "fulfillment_authorization_consumption_out_of_scope": ("fulfillment_executor_contract_blocked", "executor_backend_blocked", "executor_preconditions_blocked", "executor_dry_run_plan_blocked", "executor_admission_packet_blocked", "executor_contract_readiness_blocked"),
    "fulfillment_authorization_consumption_incomplete": ("fulfillment_executor_contract_incomplete", "executor_backend_incomplete", "executor_preconditions_incomplete", "executor_dry_run_plan_incomplete", "executor_admission_packet_incomplete", "executor_contract_readiness_incomplete"),
    "fulfillment_authorization_consumption_contradicted": ("fulfillment_executor_contract_contradicted", "executor_backend_contradicted", "executor_preconditions_contradicted", "executor_dry_run_plan_contradicted", "executor_admission_packet_contradicted", "executor_contract_readiness_contradicted"),
}
_FORBIDDEN_TRUE_FLAGS = (
    "executor_implemented",
    "backend_loaded",
    "backend_invoked",
    "dry_run_executed",
    "control_plane_admission_granted",
    "fulfillment_granted",
    "effect_performed",
    "host_mutation_performed",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "power_profile_mutation_performed",
    "process_kill_performed",
    "service_restart_performed",
    "package_install_performed",
    "driver_install_performed",
    "file_cleanup_performed",
    "provider_invocation_performed",
    "network_performed",
    "prompt_assembly_performed",
)


@dataclass(frozen=True)
class FulfillmentExecutorPolicy:
    policy_id: str
    required_executor_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    metadata_only: bool = True
    executor_contract_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FulfillmentExecutorContract:
    contract_id: str
    source_consumption_receipt_id: str
    source_consumption_receipt_digest: str
    requested_fulfillment_domain: str
    backend_class: str
    executor_domain: str
    contract_status: str
    required_executor_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    contract_only: bool = True
    executor_implemented: bool = False
    backend_loaded: bool = False
    fulfillment_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutorBackendDeclaration:
    declaration_id: str
    contract_id: str
    backend_class: str
    backend_label: str
    supported_executor_domains: tuple[str, ...]
    unsupported_executor_domains: tuple[str, ...]
    required_privilege_labels: tuple[str, ...]
    required_scope_labels: tuple[str, ...]
    declaration_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    declaration_only: bool = True
    backend_loaded: bool = False
    backend_invoked: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutorPreconditionManifest:
    manifest_id: str
    contract_id: str
    source_consumption_receipt_id: str
    precondition_labels: tuple[str, ...]
    missing_precondition_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    precondition_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    precondition_only: bool = True
    host_mutation_performed: bool = False
    effect_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutorDryRunPlan:
    plan_id: str
    contract_id: str
    backend_class: str
    dry_run_steps: tuple[str, ...]
    expected_no_effect_labels: tuple[str, ...]
    required_observation_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    dry_run_plan_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    dry_run_plan_only: bool = True
    dry_run_executed: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutorAdmissionPacket:
    packet_id: str
    contract_id: str
    source_consumption_receipt_id: str
    backend_declaration_id: str
    precondition_manifest_id: str
    dry_run_plan_id: str
    executor_domain: str
    admission_packet_status: str
    required_control_plane_labels: tuple[str, ...]
    required_audit_labels: tuple[str, ...]
    required_effect_receipt_labels: tuple[str, ...]
    required_postcondition_labels: tuple[str, ...]
    required_rollback_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    admission_packet_only: bool = True
    control_plane_admission_granted: bool = False
    fulfillment_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutorContractReadinessReceipt:
    receipt_id: str
    contract_id: str
    backend_declaration_id: str
    precondition_manifest_id: str
    dry_run_plan_id: str
    admission_packet_id: str
    readiness_status: str
    evidence_summary: tuple[str, ...]
    missing_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    readiness_receipt_only: bool = True
    executor_implemented: bool = False
    backend_loaded: bool = False
    dry_run_executed: bool = False
    control_plane_admission_granted: bool = False
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FulfillmentExecutorValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


class FulfillmentExecutorContractWingRecords(NamedTuple):
    contract: FulfillmentExecutorContract
    backend_declaration: ExecutorBackendDeclaration
    precondition_manifest: ExecutorPreconditionManifest
    dry_run_plan: ExecutorDryRunPlan
    admission_packet: ExecutorAdmissionPacket
    readiness_receipt: ExecutorContractReadinessReceipt


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


def fulfillment_executor_contract_digest(record_or_payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(_payload(record_or_payload)).encode("utf-8")).hexdigest()


executor_backend_declaration_digest = fulfillment_executor_contract_digest
executor_precondition_manifest_digest = fulfillment_executor_contract_digest
executor_dry_run_plan_digest = fulfillment_executor_contract_digest
executor_admission_packet_digest = fulfillment_executor_contract_digest
executor_contract_readiness_receipt_digest = fulfillment_executor_contract_digest


def _digest_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]


def build_default_fulfillment_executor_policy() -> FulfillmentExecutorPolicy:
    return FulfillmentExecutorPolicy(
        "fulfillment-executor-contract-policy-v1",
        tuple(sorted(REQUIRED_EXECUTOR_LABELS)),
        tuple(sorted(BLOCKED_ACTION_LABELS)),
    )


def _statuses_for_consumption(receipt: Mapping[str, Any]) -> tuple[str, str, str, str, str, str]:
    status = str(receipt.get("consumption_status", ""))
    if any(receipt.get(flag, False) for flag in _FORBIDDEN_TRUE_FLAGS if flag in receipt):
        return _CONSUMPTION_STATUS_MAP["fulfillment_authorization_consumption_contradicted"]
    if status in _CONSUMPTION_STATUS_MAP and receipt.get("authorization_consumed_for_future_fulfillment", False):
        return _CONSUMPTION_STATUS_MAP[status]
    if status in _CONSUMPTION_STATUS_MAP and status != "fulfillment_authorization_consumption_recorded":
        return _CONSUMPTION_STATUS_MAP[status]
    return _CONSUMPTION_STATUS_MAP["fulfillment_authorization_consumption_incomplete"]


def _executor_domain(receipt: Mapping[str, Any], requested: str | None = None) -> str:
    return requested or _DOMAIN_TO_EXECUTOR.get(str(receipt.get("requested_fulfillment_domain", "")), "operator_review_executor_contract")


def _backend_class(executor_domain: str, requested: str | None = None) -> str:
    if requested in BACKEND_CLASSES:
        return requested
    return _EXECUTOR_TO_BACKEND.get(executor_domain, "operator_manual_backend_future")


def _blocked_actions(receipt: Mapping[str, Any], executor_domain: str, extra: Sequence[str] | None = None) -> tuple[str, ...]:
    return tuple(sorted(set(BLOCKED_ACTION_LABELS) | set(_tuple(receipt.get("blocked_actions"))) | set(_DOMAIN_BLOCKS.get(executor_domain, ())) | set(_tuple(extra))))


def _missing_labels(receipt: Mapping[str, Any]) -> tuple[str, ...]:
    if receipt.get("authorization_consumed_for_future_fulfillment") and str(receipt.get("consumption_status")) in {"fulfillment_authorization_consumption_recorded", "fulfillment_authorization_consumption_recorded_with_warnings"}:
        return ()
    return ("valid_fulfillment_authorization_consumption_required",)


def build_fulfillment_executor_contract(
    consumption_receipt: FulfillmentAuthorizationConsumptionReceipt | Mapping[str, Any],
    *,
    executor_domain: str | None = None,
    backend_class: str | None = None,
    required_executor_labels: Sequence[str] | None = None,
    blocked_actions: Sequence[str] | None = None,
    contract_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> FulfillmentExecutorContract:
    receipt = _source_payload(consumption_receipt)
    domain = _executor_domain(receipt, executor_domain)
    backend = _backend_class(domain, backend_class)
    statuses = _statuses_for_consumption(receipt)
    required = tuple(sorted(set(REQUIRED_EXECUTOR_LABELS) | set(_tuple(required_executor_labels))))
    blocked = _blocked_actions(receipt, domain, blocked_actions)
    risks = tuple(sorted(set(_tuple(receipt.get("risk_codes"))) | {"executor_contract_is_not_executor", "backend_declaration_is_not_loaded_backend"}))
    provisional = FulfillmentExecutorContract(
        contract_id or _digest_id("fulfillment-executor-contract-", {"receipt": receipt.get("receipt_id"), "domain": domain, "backend": backend, "status": statuses[0]}),
        str(receipt.get("receipt_id", "")),
        str(receipt.get("digest", "")),
        str(receipt.get("requested_fulfillment_domain", "")),
        backend,
        domain,
        statuses[0],
        required,
        blocked,
        tuple(sorted(set(_tuple(receipt.get("warning_codes"))))),
        risks,
        created_at,
        "",
    )
    return replace(provisional, digest=fulfillment_executor_contract_digest(provisional))


def build_executor_backend_declaration(contract: FulfillmentExecutorContract | Mapping[str, Any], *, backend_label: str | None = None, declaration_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> ExecutorBackendDeclaration:
    c = _source_payload(contract)
    status = {
        "fulfillment_executor_contract_ready": "executor_backend_declared",
        "fulfillment_executor_contract_ready_with_conditions": "executor_backend_declared_with_warnings",
        "fulfillment_executor_contract_blocked": "executor_backend_blocked",
        "fulfillment_executor_contract_incomplete": "executor_backend_incomplete",
        "fulfillment_executor_contract_contradicted": "executor_backend_contradicted",
    }.get(str(c.get("contract_status")), "executor_backend_incomplete")
    supported = (str(c.get("executor_domain", "")),) if status not in {"executor_backend_incomplete", "executor_backend_contradicted"} else ()
    unsupported = tuple(sorted(EXECUTOR_DOMAINS - set(supported)))
    provisional = ExecutorBackendDeclaration(
        declaration_id or _digest_id("executor-backend-declaration-", {"contract": c.get("contract_id"), "backend": c.get("backend_class"), "status": status}),
        str(c.get("contract_id", "")),
        str(c.get("backend_class", "")),
        backend_label or f"{c.get('backend_class', '')}:declaration-only:not-loaded:not-invoked",
        supported,
        unsupported,
        ("local_authorization_grant_required", "control_plane_admission_required_for_future_execution", "panic_stop_required"),
        ("scope_match_required",),
        status,
        _tuple(c.get("warning_codes")),
        tuple(sorted(set(_tuple(c.get("risk_codes"))) | {"backend_declaration_does_not_load_or_invoke_backend"})),
        created_at,
        "",
    )
    return replace(provisional, digest=executor_backend_declaration_digest(provisional))


def build_executor_precondition_manifest(contract: FulfillmentExecutorContract | Mapping[str, Any], consumption_receipt: FulfillmentAuthorizationConsumptionReceipt | Mapping[str, Any], *, manifest_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> ExecutorPreconditionManifest:
    c = _source_payload(contract)
    r = _source_payload(consumption_receipt)
    missing = _missing_labels(r)
    status = {
        "fulfillment_executor_contract_ready": "executor_preconditions_ready",
        "fulfillment_executor_contract_ready_with_conditions": "executor_preconditions_ready_with_conditions",
        "fulfillment_executor_contract_blocked": "executor_preconditions_blocked",
        "fulfillment_executor_contract_incomplete": "executor_preconditions_incomplete",
        "fulfillment_executor_contract_contradicted": "executor_preconditions_contradicted",
    }.get(str(c.get("contract_status")), "executor_preconditions_incomplete")
    if missing and status == "executor_preconditions_ready":
        status = "executor_preconditions_incomplete"
    provisional = ExecutorPreconditionManifest(
        manifest_id or _digest_id("executor-precondition-manifest-", {"contract": c.get("contract_id"), "missing": missing, "status": status}),
        str(c.get("contract_id", "")),
        str(r.get("receipt_id", "")),
        tuple(sorted(REQUIRED_EXECUTOR_LABELS)),
        missing,
        _tuple(c.get("blocked_actions")),
        status,
        _tuple(c.get("warning_codes")),
        tuple(sorted(set(_tuple(c.get("risk_codes"))) | {"precondition_manifest_is_metadata_only"})),
        created_at,
        "",
    )
    return replace(provisional, digest=executor_precondition_manifest_digest(provisional))


def build_executor_dry_run_plan(contract: FulfillmentExecutorContract | Mapping[str, Any], *, plan_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> ExecutorDryRunPlan:
    c = _source_payload(contract)
    status = {
        "fulfillment_executor_contract_ready": "executor_dry_run_plan_ready",
        "fulfillment_executor_contract_ready_with_conditions": "executor_dry_run_plan_ready_with_conditions",
        "fulfillment_executor_contract_blocked": "executor_dry_run_plan_blocked",
        "fulfillment_executor_contract_incomplete": "executor_dry_run_plan_incomplete",
        "fulfillment_executor_contract_contradicted": "executor_dry_run_plan_contradicted",
    }.get(str(c.get("contract_status")), "executor_dry_run_plan_incomplete")
    provisional = ExecutorDryRunPlan(
        plan_id or _digest_id("executor-dry-run-plan-", {"contract": c.get("contract_id"), "backend": c.get("backend_class"), "status": status}),
        str(c.get("contract_id", "")),
        str(c.get("backend_class", "")),
        ("review_contract_metadata", "verify_precondition_manifest", "prepare_future_control_plane_packet_without_admission", "record_no_effect_expectations"),
        ("dry_run_plan_is_not_execution", "no_fulfillment_granted", "no_effect_performed", "no_host_mutation_performed"),
        ("runtime_supervisor_observation_required", "immutable_trace_required", "audit_receipt_required_for_future_execution"),
        _tuple(c.get("blocked_actions")),
        status,
        _tuple(c.get("warning_codes")),
        tuple(sorted(set(_tuple(c.get("risk_codes"))) | {"dry_run_plan_is_not_dry_run_execution"})),
        created_at,
        "",
    )
    return replace(provisional, digest=executor_dry_run_plan_digest(provisional))


def build_executor_admission_packet(contract: FulfillmentExecutorContract | Mapping[str, Any], backend_declaration: ExecutorBackendDeclaration | Mapping[str, Any], precondition_manifest: ExecutorPreconditionManifest | Mapping[str, Any], dry_run_plan: ExecutorDryRunPlan | Mapping[str, Any], consumption_receipt: FulfillmentAuthorizationConsumptionReceipt | Mapping[str, Any], *, packet_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> ExecutorAdmissionPacket:
    c = _source_payload(contract)
    b = _source_payload(backend_declaration)
    m = _source_payload(precondition_manifest)
    p = _source_payload(dry_run_plan)
    r = _source_payload(consumption_receipt)
    status = {
        "fulfillment_executor_contract_ready": "executor_admission_packet_ready",
        "fulfillment_executor_contract_ready_with_conditions": "executor_admission_packet_ready_with_conditions",
        "fulfillment_executor_contract_blocked": "executor_admission_packet_blocked",
        "fulfillment_executor_contract_incomplete": "executor_admission_packet_incomplete",
        "fulfillment_executor_contract_contradicted": "executor_admission_packet_contradicted",
    }.get(str(c.get("contract_status")), "executor_admission_packet_incomplete")
    provisional = ExecutorAdmissionPacket(
        packet_id or _digest_id("executor-admission-packet-", {"contract": c.get("contract_id"), "backend": b.get("declaration_id"), "manifest": m.get("manifest_id"), "plan": p.get("plan_id"), "status": status}),
        str(c.get("contract_id", "")),
        str(r.get("receipt_id", "")),
        str(b.get("declaration_id", "")),
        str(m.get("manifest_id", "")),
        str(p.get("plan_id", "")),
        str(c.get("executor_domain", "")),
        status,
        ("control_plane_admission_required_for_future_execution", "operator_authority_required", "panic_stop_required", "safety_gates_required"),
        ("audit_receipt_required_for_future_execution", "immutable_trace_required"),
        ("effect_receipt_required_for_future_execution",),
        ("postcondition_check_required_for_future_execution",),
        ("rollback_receipt_required_for_future_execution",),
        _tuple(c.get("blocked_actions")),
        tuple(sorted(set(_tuple(c.get("warning_codes"))) | set(_tuple(b.get("warning_codes"))) | set(_tuple(m.get("warning_codes"))) | set(_tuple(p.get("warning_codes"))))),
        tuple(sorted(set(_tuple(c.get("risk_codes"))) | {"admission_packet_is_not_control_plane_admission"})),
        created_at,
        "",
    )
    return replace(provisional, digest=executor_admission_packet_digest(provisional))


def build_executor_contract_readiness_receipt(contract: FulfillmentExecutorContract | Mapping[str, Any], backend_declaration: ExecutorBackendDeclaration | Mapping[str, Any], precondition_manifest: ExecutorPreconditionManifest | Mapping[str, Any], dry_run_plan: ExecutorDryRunPlan | Mapping[str, Any], admission_packet: ExecutorAdmissionPacket | Mapping[str, Any], *, receipt_id: str | None = None, created_at: str = "1970-01-01T00:00:00+00:00") -> ExecutorContractReadinessReceipt:
    c = _source_payload(contract)
    b = _source_payload(backend_declaration)
    m = _source_payload(precondition_manifest)
    p = _source_payload(dry_run_plan)
    a = _source_payload(admission_packet)
    status = {
        "fulfillment_executor_contract_ready": "executor_contract_readiness_recorded",
        "fulfillment_executor_contract_ready_with_conditions": "executor_contract_readiness_recorded_with_warnings",
        "fulfillment_executor_contract_blocked": "executor_contract_readiness_blocked",
        "fulfillment_executor_contract_incomplete": "executor_contract_readiness_incomplete",
        "fulfillment_executor_contract_contradicted": "executor_contract_readiness_contradicted",
    }.get(str(c.get("contract_status")), "executor_contract_readiness_incomplete")
    missing = tuple(sorted(set(_tuple(m.get("missing_precondition_labels")))))
    evidence = (
        "executor_contract_recorded_metadata_only",
        "backend_declaration_not_loaded_or_invoked",
        "precondition_manifest_recorded_metadata_only",
        "dry_run_plan_not_executed",
        "admission_packet_not_control_plane_admission",
        "readiness_receipt_does_not_implement_executor_or_perform_effects",
    )
    provisional = ExecutorContractReadinessReceipt(
        receipt_id or _digest_id("executor-contract-readiness-", {"contract": c.get("contract_id"), "packet": a.get("packet_id"), "status": status, "missing": missing}),
        str(c.get("contract_id", "")),
        str(b.get("declaration_id", "")),
        str(m.get("manifest_id", "")),
        str(p.get("plan_id", "")),
        str(a.get("packet_id", "")),
        status,
        evidence,
        missing,
        _tuple(c.get("blocked_actions")),
        tuple(sorted(set(_tuple(c.get("warning_codes"))) | set(_tuple(a.get("warning_codes"))))),
        tuple(sorted(set(_tuple(c.get("risk_codes"))) | {"readiness_receipt_is_not_executor_implementation", "real_fulfillment_remains_deferred"})),
        created_at,
        "",
    )
    return replace(provisional, digest=executor_contract_readiness_receipt_digest(provisional))


def _validate_common(payload: Mapping[str, Any], *, prefix: str, status_field: str, statuses: frozenset[str], only_field: str, digest_fn: Any) -> list[str]:
    findings: list[str] = []
    if not payload.get("metadata_only", False):
        findings.append(prefix + "not_metadata_only")
    if not payload.get(only_field, False):
        findings.append(prefix + f"not_{only_field}")
    if payload.get(status_field) not in statuses:
        findings.append(prefix + "unknown_status")
    for flag in _FORBIDDEN_TRUE_FLAGS:
        if payload.get(flag, False):
            findings.append(prefix + f"forbidden_flag:{flag}")
    if payload.get("digest") and payload.get("digest") != digest_fn(payload):
        findings.append(prefix + "digest_mismatch")
    return findings


def validate_fulfillment_executor_contract(contract: FulfillmentExecutorContract | Mapping[str, Any]) -> FulfillmentExecutorValidationResult:
    p = _source_payload(contract)
    f = _validate_common(p, prefix="contract:", status_field="contract_status", statuses=CONTRACT_STATUSES, only_field="contract_only", digest_fn=fulfillment_executor_contract_digest)
    if p.get("executor_domain") not in EXECUTOR_DOMAINS:
        f.append("contract:unknown_executor_domain")
    if p.get("backend_class") not in BACKEND_CLASSES:
        f.append("contract:unknown_backend_class")
    return FulfillmentExecutorValidationResult(not f, tuple(f))


def validate_executor_backend_declaration(declaration: ExecutorBackendDeclaration | Mapping[str, Any]) -> FulfillmentExecutorValidationResult:
    p = _source_payload(declaration)
    f = _validate_common(p, prefix="backend:", status_field="declaration_status", statuses=BACKEND_DECLARATION_STATUSES, only_field="declaration_only", digest_fn=executor_backend_declaration_digest)
    if p.get("backend_class") not in BACKEND_CLASSES:
        f.append("backend:unknown_backend_class")
    return FulfillmentExecutorValidationResult(not f, tuple(f))


def validate_executor_precondition_manifest(manifest: ExecutorPreconditionManifest | Mapping[str, Any]) -> FulfillmentExecutorValidationResult:
    p = _source_payload(manifest)
    f = _validate_common(p, prefix="preconditions:", status_field="precondition_status", statuses=PRECONDITION_STATUSES, only_field="precondition_only", digest_fn=executor_precondition_manifest_digest)
    return FulfillmentExecutorValidationResult(not f, tuple(f))


def validate_executor_dry_run_plan(plan: ExecutorDryRunPlan | Mapping[str, Any]) -> FulfillmentExecutorValidationResult:
    p = _source_payload(plan)
    f = _validate_common(p, prefix="dry_run_plan:", status_field="dry_run_plan_status", statuses=DRY_RUN_PLAN_STATUSES, only_field="dry_run_plan_only", digest_fn=executor_dry_run_plan_digest)
    return FulfillmentExecutorValidationResult(not f, tuple(f))


def validate_executor_admission_packet(packet: ExecutorAdmissionPacket | Mapping[str, Any]) -> FulfillmentExecutorValidationResult:
    p = _source_payload(packet)
    f = _validate_common(p, prefix="admission_packet:", status_field="admission_packet_status", statuses=ADMISSION_PACKET_STATUSES, only_field="admission_packet_only", digest_fn=executor_admission_packet_digest)
    return FulfillmentExecutorValidationResult(not f, tuple(f))


def validate_executor_contract_readiness_receipt(receipt: ExecutorContractReadinessReceipt | Mapping[str, Any]) -> FulfillmentExecutorValidationResult:
    p = _source_payload(receipt)
    f = _validate_common(p, prefix="readiness:", status_field="readiness_status", statuses=READINESS_RECEIPT_STATUSES, only_field="readiness_receipt_only", digest_fn=executor_contract_readiness_receipt_digest)
    return FulfillmentExecutorValidationResult(not f, tuple(f))


def summarize_fulfillment_executor_contract(contract: FulfillmentExecutorContract | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(contract)
    return {k: p.get(k) for k in ("contract_id", "source_consumption_receipt_id", "requested_fulfillment_domain", "backend_class", "executor_domain", "contract_status", "metadata_only", "contract_only", "executor_implemented", "backend_loaded", "fulfillment_granted", "effect_performed", "host_mutation_performed", "digest")}


def summarize_executor_backend_declaration(declaration: ExecutorBackendDeclaration | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(declaration)
    return {k: p.get(k) for k in ("declaration_id", "contract_id", "backend_class", "backend_label", "declaration_status", "metadata_only", "declaration_only", "backend_loaded", "backend_invoked", "host_mutation_performed", "digest")}


def summarize_executor_precondition_manifest(manifest: ExecutorPreconditionManifest | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(manifest)
    return {k: p.get(k) for k in ("manifest_id", "contract_id", "source_consumption_receipt_id", "missing_precondition_labels", "precondition_status", "metadata_only", "precondition_only", "effect_performed", "host_mutation_performed", "digest")}


def summarize_executor_dry_run_plan(plan: ExecutorDryRunPlan | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(plan)
    return {k: p.get(k) for k in ("plan_id", "contract_id", "backend_class", "dry_run_plan_status", "metadata_only", "dry_run_plan_only", "dry_run_executed", "effect_performed", "host_mutation_performed", "digest")}


def summarize_executor_admission_packet(packet: ExecutorAdmissionPacket | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(packet)
    return {k: p.get(k) for k in ("packet_id", "contract_id", "source_consumption_receipt_id", "executor_domain", "admission_packet_status", "metadata_only", "admission_packet_only", "control_plane_admission_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed", "digest")}


def summarize_executor_contract_readiness_receipt(receipt: ExecutorContractReadinessReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(receipt)
    return {k: p.get(k) for k in ("receipt_id", "contract_id", "readiness_status", "metadata_only", "readiness_receipt_only", "executor_implemented", "backend_loaded", "dry_run_executed", "control_plane_admission_granted", "fulfillment_granted", "effect_performed", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed", "digest")}


def build_fulfillment_executor_contract_wing(
    consumption_receipt: FulfillmentAuthorizationConsumptionReceipt | Mapping[str, Any],
    *,
    executor_domain: str | None = None,
    backend_class: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> FulfillmentExecutorContractWingRecords:
    contract = build_fulfillment_executor_contract(consumption_receipt, executor_domain=executor_domain, backend_class=backend_class, created_at=created_at)
    backend_declaration = build_executor_backend_declaration(contract, created_at=created_at)
    precondition_manifest = build_executor_precondition_manifest(contract, consumption_receipt, created_at=created_at)
    dry_run_plan = build_executor_dry_run_plan(contract, created_at=created_at)
    admission_packet = build_executor_admission_packet(contract, backend_declaration, precondition_manifest, dry_run_plan, consumption_receipt, created_at=created_at)
    readiness_receipt = build_executor_contract_readiness_receipt(contract, backend_declaration, precondition_manifest, dry_run_plan, admission_packet, created_at=created_at)
    return FulfillmentExecutorContractWingRecords(contract, backend_declaration, precondition_manifest, dry_run_plan, admission_packet, readiness_receipt)
