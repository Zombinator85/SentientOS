"""Deterministic dry-run execution harness for executor contract readiness.

This wing is simulation-only. It may record that an inert in-process simulated
backend mapping ran, but it does not fulfill host actions, mutate host state,
load or invoke real backends, write fan/PWM controls, change thermal or power
settings, restart services, kill processes, install packages or drivers, clean
or delete files, make network calls, invoke providers, assemble prompts, spawn
subprocess execution, run shell execution, invoke OS backends, or call
control-plane admission/execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, NamedTuple, Sequence

from sentientos.fulfillment_executor_contract import ExecutorContractReadinessReceipt

HARNESS_STATUSES = frozenset({
    "dry_run_harness_ready",
    "dry_run_harness_ready_with_warnings",
    "dry_run_harness_blocked",
    "dry_run_harness_incomplete",
    "dry_run_harness_contradicted",
})
SIMULATED_BACKEND_STATUSES = frozenset({
    "simulated_backend_available",
    "simulated_backend_available_with_warnings",
    "simulated_backend_blocked",
    "simulated_backend_incomplete",
    "simulated_backend_contradicted",
})
DRY_RUN_REQUEST_STATUSES = frozenset({
    "dry_run_execution_request_recorded",
    "dry_run_execution_request_recorded_with_warnings",
    "dry_run_execution_request_blocked",
    "dry_run_execution_request_incomplete",
    "dry_run_execution_request_contradicted",
})
DRY_RUN_RESULT_STATUSES = frozenset({
    "dry_run_execution_simulated",
    "dry_run_execution_simulated_with_warnings",
    "dry_run_execution_blocked",
    "dry_run_execution_incomplete",
    "dry_run_execution_contradicted",
})
DRY_RUN_RECEIPT_STATUSES = frozenset({
    "dry_run_execution_receipt_recorded",
    "dry_run_execution_receipt_recorded_with_warnings",
    "dry_run_execution_receipt_blocked",
    "dry_run_execution_receipt_incomplete",
    "dry_run_execution_receipt_contradicted",
})
DRY_RUN_DOMAINS = frozenset({
    "diagnostics_dry_run",
    "operator_review_dry_run",
    "resource_pressure_dry_run",
    "thermal_safety_dry_run",
    "future_cooling_dry_run",
    "future_power_dry_run",
    "future_cleanup_dry_run",
    "future_service_dry_run",
})
SIMULATED_BACKEND_CLASSES = frozenset({
    "diagnostic_backend_simulated",
    "operator_manual_backend_simulated",
    "cooling_backend_simulated",
    "power_backend_simulated",
    "cleanup_backend_simulated",
    "service_backend_simulated",
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
    "subprocess_execution",
    "shell_execution",
    "os_backend_invocation",
    "control_plane_admission_execution",
})
_DOMAIN_BACKEND_CLASS = {
    "diagnostics_dry_run": "diagnostic_backend_simulated",
    "operator_review_dry_run": "operator_manual_backend_simulated",
    "resource_pressure_dry_run": "diagnostic_backend_simulated",
    "thermal_safety_dry_run": "diagnostic_backend_simulated",
    "future_cooling_dry_run": "cooling_backend_simulated",
    "future_power_dry_run": "power_backend_simulated",
    "future_cleanup_dry_run": "cleanup_backend_simulated",
    "future_service_dry_run": "service_backend_simulated",
}
_BACKEND_DOMAINS = {
    "diagnostic_backend_simulated": ("diagnostics_dry_run", "resource_pressure_dry_run", "thermal_safety_dry_run"),
    "operator_manual_backend_simulated": ("operator_review_dry_run",),
    "cooling_backend_simulated": ("future_cooling_dry_run",),
    "power_backend_simulated": ("future_power_dry_run",),
    "cleanup_backend_simulated": ("future_cleanup_dry_run",),
    "service_backend_simulated": ("future_service_dry_run",),
}
_DOMAIN_BLOCKS = {
    "future_cooling_dry_run": ("fan_pwm_write", "thermal_actuation"),
    "future_power_dry_run": ("power_profile_mutation",),
    "future_cleanup_dry_run": ("file_cleanup", "file_delete"),
    "future_service_dry_run": ("service_restart", "process_kill"),
}
_READY_READINESS_STATUSES = {"executor_contract_readiness_recorded", "executor_contract_readiness_recorded_with_warnings"}
_BLOCKED_READINESS_STATUSES = {"executor_contract_readiness_blocked"}
_INCOMPLETE_READINESS_STATUSES = {"executor_contract_readiness_incomplete"}
_CONTRADICTED_READINESS_STATUSES = {"executor_contract_readiness_contradicted"}
_FORBIDDEN_TRUE_FLAGS = (
    "executor_implemented",
    "backend_loaded",
    "backend_invoked",
    "real_backend_invoked",
    "control_plane_admission_granted",
    "fulfillment_granted",
    "real_fulfillment_performed",
    "effect_performed",
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
    "provider_invocation_performed",
    "network_performed",
    "prompt_assembly_performed",
    "subprocess_execution_performed",
    "shell_execution_performed",
    "os_backend_invoked",
    "control_plane_admission_execution_performed",
)


@dataclass(frozen=True)
class DryRunExecutionHarnessPolicy:
    policy_id: str
    harness_status: str
    supported_dry_run_domains: tuple[str, ...]
    supported_backend_classes: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    simulated_only: bool = True
    no_real_backends: bool = True
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimulatedBackendRecord:
    backend_id: str
    backend_class: str
    supported_dry_run_domains: tuple[str, ...]
    backend_status: str
    simulation_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    simulated_only: bool = True
    backend_loaded: bool = False
    backend_invoked: bool = False
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimulatedBackendRegistry:
    registry_id: str
    backend_records: tuple[SimulatedBackendRecord, ...]
    supported_backend_classes: tuple[str, ...]
    supported_dry_run_domains: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    registry_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    simulated_only: bool = True
    no_real_backends: bool = True
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunExecutionRequest:
    request_id: str
    source_executor_readiness_receipt_id: str
    source_executor_readiness_receipt_digest: str
    source_executor_contract_id: str
    requested_dry_run_domain: str
    requested_simulated_backend_class: str
    requested_scope_labels: tuple[str, ...]
    requested_step_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    request_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    dry_run_request_only: bool = True
    does_not_execute_real_backend: bool = True
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunExecutionResult:
    result_id: str
    request_id: str
    simulated_backend_id: str
    dry_run_domain: str
    simulated_backend_class: str
    result_status: str
    simulated_step_labels: tuple[str, ...]
    simulated_postcondition_labels: tuple[str, ...]
    simulated_rollback_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    simulated_only: bool = True
    dry_run_executed: bool = True
    real_backend_invoked: bool = False
    real_fulfillment_performed: bool = False
    real_effect_performed: bool = False
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
    file_delete_performed: bool = False
    provider_invocation_performed: bool = False
    network_performed: bool = False
    prompt_assembly_performed: bool = False
    subprocess_execution_performed: bool = False
    shell_execution_performed: bool = False
    os_backend_invoked: bool = False
    control_plane_admission_execution_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunExecutionReceipt:
    receipt_id: str
    request_id: str
    result_id: str
    source_executor_readiness_receipt_id: str
    dry_run_domain: str
    simulated_backend_class: str
    receipt_status: str
    evidence_summary: tuple[str, ...]
    simulated_step_labels: tuple[str, ...]
    simulated_postcondition_labels: tuple[str, ...]
    simulated_rollback_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    dry_run_receipt_only: bool = True
    dry_run_executed: bool = True
    real_fulfillment_performed: bool = False
    real_effect_performed: bool = False
    real_backend_invoked: bool = False
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
    subprocess_execution_performed: bool = False
    shell_execution_performed: bool = False
    os_backend_invoked: bool = False
    control_plane_admission_execution_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunExecutionBlockReceipt:
    receipt_id: str
    request_id: str | None
    source_executor_readiness_receipt_id: str | None
    block_status: str
    block_reason_codes: tuple[str, ...]
    missing_labels: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    block_receipt_only: bool = True
    dry_run_executed: bool = False
    real_fulfillment_performed: bool = False
    host_mutation_performed: bool = False
    does_not_execute: bool = True
    does_not_mutate_host: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DryRunExecutionValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


class DryRunExecutionHarnessWingRecords(NamedTuple):
    registry: SimulatedBackendRegistry
    request: DryRunExecutionRequest
    result_or_block_receipt: DryRunExecutionResult | DryRunExecutionBlockReceipt
    receipt: DryRunExecutionReceipt | None


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


def dry_run_execution_digest(record_or_payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(_payload(record_or_payload)).encode("utf-8")).hexdigest()


simulated_backend_registry_digest = dry_run_execution_digest
simulated_backend_record_digest = dry_run_execution_digest
dry_run_execution_request_digest = dry_run_execution_digest
dry_run_execution_result_digest = dry_run_execution_digest
dry_run_execution_receipt_digest = dry_run_execution_digest
dry_run_execution_block_receipt_digest = dry_run_execution_digest


def _digest_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]


def _blocked_actions(domain: str, extra: Sequence[str] | None = None) -> tuple[str, ...]:
    return tuple(sorted(set(BLOCKED_ACTION_LABELS) | set(_DOMAIN_BLOCKS.get(domain, ())) | set(_tuple(extra))))


def _domain_from_readiness(readiness: Mapping[str, Any], requested: str | None) -> str:
    if requested:
        return requested
    blocked = set(_tuple(readiness.get("blocked_actions")))
    if {"fan_pwm_write", "thermal_actuation"} <= blocked:
        return "future_cooling_dry_run"
    if "power_profile_mutation" in blocked:
        return "future_power_dry_run"
    if {"file_cleanup", "file_delete"} & blocked:
        return "future_cleanup_dry_run"
    if {"service_restart", "process_kill"} & blocked:
        return "future_service_dry_run"
    return "operator_review_dry_run"


def _backend_for_domain(domain: str, requested: str | None) -> str:
    return requested or _DOMAIN_BACKEND_CLASS.get(domain, "operator_manual_backend_simulated")


def _status_from_readiness(readiness: Mapping[str, Any]) -> str:
    status = str(readiness.get("readiness_status", ""))
    if any(readiness.get(flag, False) for flag in _FORBIDDEN_TRUE_FLAGS if flag in readiness):
        return "dry_run_execution_request_contradicted"
    if status in _READY_READINESS_STATUSES:
        return "dry_run_execution_request_recorded_with_warnings" if status.endswith("with_warnings") else "dry_run_execution_request_recorded"
    if status in _BLOCKED_READINESS_STATUSES:
        return "dry_run_execution_request_blocked"
    if status in _CONTRADICTED_READINESS_STATUSES:
        return "dry_run_execution_request_contradicted"
    return "dry_run_execution_request_incomplete"


def build_default_dry_run_harness_policy() -> DryRunExecutionHarnessPolicy:
    return DryRunExecutionHarnessPolicy(
        "dry-run-execution-harness-policy-v1",
        "dry_run_harness_ready",
        tuple(sorted(DRY_RUN_DOMAINS)),
        tuple(sorted(SIMULATED_BACKEND_CLASSES)),
        tuple(sorted(BLOCKED_ACTION_LABELS)),
        (),
        ("simulation_only_no_host_effects", "real_fulfillment_deferred"),
    )


def build_default_simulated_backend_registry(*, created_at: str = "1970-01-01T00:00:00+00:00") -> SimulatedBackendRegistry:
    records = tuple(
        SimulatedBackendRecord(
            backend_id=f"simulated-backend-{backend_class.replace('_', '-')}",
            backend_class=backend_class,
            supported_dry_run_domains=tuple(sorted(domains)),
            backend_status="simulated_backend_available",
            simulation_labels=("in_process_deterministic_mapping", "no_real_backend_loaded", "no_host_effects"),
            warning_codes=(),
            risk_codes=("simulation_not_fulfillment",),
        )
        for backend_class, domains in sorted(_BACKEND_DOMAINS.items())
    )
    provisional = SimulatedBackendRegistry(
        "simulated-backend-registry-v1",
        records,
        tuple(sorted(SIMULATED_BACKEND_CLASSES)),
        tuple(sorted(DRY_RUN_DOMAINS)),
        tuple(sorted(BLOCKED_ACTION_LABELS)),
        "dry_run_harness_ready",
        (),
        ("no_real_backends_registered", "simulation_only"),
        created_at,
        "",
    )
    return replace(provisional, digest=simulated_backend_registry_digest(provisional))


def build_dry_run_execution_request(
    executor_readiness_receipt: ExecutorContractReadinessReceipt | Mapping[str, Any],
    *,
    requested_dry_run_domain: str | None = None,
    requested_simulated_backend_class: str | None = None,
    requested_scope_labels: Sequence[str] = (),
    requested_step_labels: Sequence[str] = (),
    request_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> DryRunExecutionRequest:
    readiness = _source_payload(executor_readiness_receipt)
    domain = _domain_from_readiness(readiness, requested_dry_run_domain)
    backend_class = _backend_for_domain(domain, requested_simulated_backend_class)
    status = _status_from_readiness(readiness)
    if domain not in DRY_RUN_DOMAINS or backend_class not in SIMULATED_BACKEND_CLASSES:
        status = "dry_run_execution_request_blocked"
    if backend_class != _DOMAIN_BACKEND_CLASS.get(domain):
        status = "dry_run_execution_request_blocked"
    blocked = _blocked_actions(domain, readiness.get("blocked_actions"))
    warnings = _tuple(readiness.get("warning_codes"))
    risks = tuple(sorted(set(_tuple(readiness.get("risk_codes"))) | {"dry_run_execution_is_not_real_fulfillment"}))
    provisional = DryRunExecutionRequest(
        request_id or _digest_id("dry-run-execution-request-", {"readiness": readiness.get("receipt_id"), "domain": domain, "backend": backend_class, "status": status}),
        str(readiness.get("receipt_id", "")),
        str(readiness.get("digest", "")),
        str(readiness.get("contract_id", "")),
        domain,
        backend_class,
        _tuple(requested_scope_labels),
        _tuple(requested_step_labels) or ("simulate_contract_steps", "record_no_effect_posture"),
        blocked,
        status,
        warnings,
        risks,
        created_at,
        "",
    )
    return replace(provisional, digest=dry_run_execution_request_digest(provisional))


def _registry_record(registry: SimulatedBackendRegistry | Mapping[str, Any], backend_class: str) -> Mapping[str, Any] | None:
    payload = _source_payload(registry)
    for record in payload.get("backend_records", ()):
        item = _source_payload(record)
        if item.get("backend_class") == backend_class:
            return item
    return None


def _simulated_labels(domain: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    base_steps = ("load_simulated_mapping_metadata", "match_executor_contract_record", "simulate_no_effect_backend_response")
    domain_steps = {
        "future_cooling_dry_run": ("simulate_cooling_plan_without_fan_pwm_or_thermal_write",),
        "future_power_dry_run": ("simulate_power_plan_without_power_profile_mutation",),
        "future_cleanup_dry_run": ("simulate_cleanup_plan_without_file_cleanup_or_delete",),
        "future_service_dry_run": ("simulate_service_plan_without_restart_or_process_kill",),
    }.get(domain, (f"simulate_{domain}",))
    postconditions = ("dry_run_executed_in_process", "real_backend_invoked_false", "effect_performed_false", "host_mutation_performed_false")
    rollbacks = ("rollback_not_required_no_effect_performed", "future_real_rollback_still_deferred")
    return base_steps + domain_steps, postconditions, rollbacks


def build_dry_run_execution_block_receipt(
    *,
    request: DryRunExecutionRequest | Mapping[str, Any] | None = None,
    source_executor_readiness_receipt_id: str | None = None,
    block_status: str = "dry_run_execution_receipt_blocked",
    block_reason_codes: Sequence[str] = (),
    missing_labels: Sequence[str] = (),
    blocked_actions: Sequence[str] = (),
    warning_codes: Sequence[str] = (),
    risk_codes: Sequence[str] = (),
    receipt_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> DryRunExecutionBlockReceipt:
    req = _source_payload(request) if request is not None else {}
    blocked = _blocked_actions(str(req.get("requested_dry_run_domain", "operator_review_dry_run")), blocked_actions or req.get("blocked_actions", ()))
    provisional = DryRunExecutionBlockReceipt(
        receipt_id or _digest_id("dry-run-execution-block-", {"request": req.get("request_id"), "reasons": tuple(block_reason_codes), "status": block_status}),
        str(req.get("request_id")) if req else None,
        source_executor_readiness_receipt_id or (str(req.get("source_executor_readiness_receipt_id")) if req else None),
        block_status,
        _tuple(block_reason_codes) or ("dry_run_execution_not_allowed",),
        _tuple(missing_labels),
        blocked,
        _tuple(warning_codes) or _tuple(req.get("warning_codes")),
        tuple(sorted(set(_tuple(risk_codes)) | set(_tuple(req.get("risk_codes"))) | {"dry_run_block_receipt_no_execution"})),
        created_at,
        "",
    )
    return replace(provisional, digest=dry_run_execution_block_receipt_digest(provisional))


def run_dry_run_execution(
    request: DryRunExecutionRequest | Mapping[str, Any],
    registry: SimulatedBackendRegistry | Mapping[str, Any] | None = None,
    *,
    result_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> DryRunExecutionResult | DryRunExecutionBlockReceipt:
    req = _source_payload(request)
    reg = registry or build_default_simulated_backend_registry(created_at=created_at)
    validation = validate_dry_run_execution_request(req)
    if not validation.ok:
        return build_dry_run_execution_block_receipt(request=req, block_status="dry_run_execution_receipt_contradicted", block_reason_codes=validation.findings, created_at=created_at)
    if req.get("request_status") in {"dry_run_execution_request_blocked", "dry_run_execution_request_incomplete", "dry_run_execution_request_contradicted"}:
        status = str(req.get("request_status")).replace("request", "receipt")
        return build_dry_run_execution_block_receipt(request=req, block_status=status, block_reason_codes=(str(req.get("request_status")),), missing_labels=("ready_executor_contract_readiness_receipt_required",), created_at=created_at)
    record = _registry_record(reg, str(req.get("requested_simulated_backend_class")))
    if record is None:
        return build_dry_run_execution_block_receipt(request=req, block_reason_codes=("unknown_simulated_backend_class",), missing_labels=("registered_simulated_backend_required",), created_at=created_at)
    if str(req.get("requested_dry_run_domain")) not in tuple(record.get("supported_dry_run_domains", ())):
        return build_dry_run_execution_block_receipt(request=req, block_reason_codes=("simulated_backend_does_not_support_domain",), missing_labels=("matching_simulated_backend_domain_required",), created_at=created_at)
    if record.get("backend_status") != "simulated_backend_available":
        return build_dry_run_execution_block_receipt(request=req, block_reason_codes=("simulated_backend_not_available",), missing_labels=("available_simulated_backend_required",), created_at=created_at)
    steps, postconditions, rollbacks = _simulated_labels(str(req.get("requested_dry_run_domain")))
    status = "dry_run_execution_simulated_with_warnings" if req.get("warning_codes") else "dry_run_execution_simulated"
    provisional = DryRunExecutionResult(
        result_id or _digest_id("dry-run-execution-result-", {"request": req.get("request_id"), "backend": record.get("backend_id"), "status": status}),
        str(req.get("request_id", "")),
        str(record.get("backend_id", "")),
        str(req.get("requested_dry_run_domain", "")),
        str(req.get("requested_simulated_backend_class", "")),
        status,
        steps,
        postconditions,
        rollbacks,
        _tuple(req.get("blocked_actions")),
        _tuple(req.get("warning_codes")),
        tuple(sorted(set(_tuple(req.get("risk_codes"))) | {"dry_run_result_is_not_effect_receipt"})),
        created_at,
        "",
    )
    return replace(provisional, digest=dry_run_execution_result_digest(provisional))


def build_dry_run_execution_receipt(
    request: DryRunExecutionRequest | Mapping[str, Any],
    result: DryRunExecutionResult | Mapping[str, Any],
    *,
    receipt_id: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> DryRunExecutionReceipt:
    req = _source_payload(request)
    res = _source_payload(result)
    result_validation = validate_dry_run_execution_result(res)
    status = "dry_run_execution_receipt_recorded"
    if not result_validation.ok:
        status = "dry_run_execution_receipt_contradicted"
    elif res.get("warning_codes"):
        status = "dry_run_execution_receipt_recorded_with_warnings"
    evidence = (
        "dry_run_execution_simulated_in_process_only",
        "dry_run_execution_is_not_real_fulfillment",
        "dry_run_result_is_not_effect_receipt",
        "dry_run_receipt_is_not_proof_of_host_mutation",
        "real_backend_invoked_false",
        "real_effect_performed_false",
        "host_mutation_performed_false",
    )
    provisional = DryRunExecutionReceipt(
        receipt_id or _digest_id("dry-run-execution-receipt-", {"request": req.get("request_id"), "result": res.get("result_id"), "status": status}),
        str(req.get("request_id", "")),
        str(res.get("result_id", "")),
        str(req.get("source_executor_readiness_receipt_id", "")),
        str(res.get("dry_run_domain", "")),
        str(res.get("simulated_backend_class", "")),
        status,
        evidence,
        _tuple(res.get("simulated_step_labels")),
        _tuple(res.get("simulated_postcondition_labels")),
        _tuple(res.get("simulated_rollback_labels")),
        _tuple(res.get("blocked_actions")),
        _tuple(res.get("warning_codes")),
        tuple(sorted(set(_tuple(res.get("risk_codes"))) | {"dry_run_receipt_is_not_host_mutation_proof"})),
        created_at,
        "",
    )
    return replace(provisional, digest=dry_run_execution_receipt_digest(provisional))


def _validate_common(payload: Mapping[str, Any], *, prefix: str, status_field: str, statuses: frozenset[str], only_field: str, digest_fn: Any) -> list[str]:
    findings: list[str] = []
    if not payload.get("metadata_only", False):
        findings.append(prefix + "not_metadata_only")
    if not payload.get(only_field, False):
        findings.append(prefix + f"missing_{only_field}")
    if payload.get("host_mutation_performed", False):
        findings.append(prefix + "forbidden_flag:host_mutation_performed")
    if payload.get(status_field) not in statuses:
        findings.append(prefix + f"unknown_{status_field}")
    for flag in _FORBIDDEN_TRUE_FLAGS:
        if flag in payload and payload.get(flag, False):
            findings.append(prefix + f"forbidden_flag:{flag}")
    if payload.get("digest") and payload.get("digest") != digest_fn(payload):
        findings.append(prefix + "digest_mismatch")
    return findings


def validate_simulated_backend_record(record: SimulatedBackendRecord | Mapping[str, Any]) -> DryRunExecutionValidationResult:
    p = _source_payload(record)
    f = _validate_common(p, prefix="simulated_backend:", status_field="backend_status", statuses=SIMULATED_BACKEND_STATUSES, only_field="simulated_only", digest_fn=simulated_backend_record_digest)
    if p.get("backend_class") not in SIMULATED_BACKEND_CLASSES:
        f.append("simulated_backend:unknown_backend_class")
    for domain in _tuple(p.get("supported_dry_run_domains")):
        if domain not in DRY_RUN_DOMAINS:
            f.append("simulated_backend:unknown_dry_run_domain")
    return DryRunExecutionValidationResult(not f, tuple(f))


def validate_simulated_backend_registry(registry: SimulatedBackendRegistry | Mapping[str, Any]) -> DryRunExecutionValidationResult:
    p = _source_payload(registry)
    f = _validate_common(p, prefix="registry:", status_field="registry_status", statuses=HARNESS_STATUSES, only_field="simulated_only", digest_fn=simulated_backend_registry_digest)
    if not p.get("no_real_backends", False):
        f.append("registry:real_backends_allowed")
    for record in p.get("backend_records", ()):
        result = validate_simulated_backend_record(record)
        f.extend("registry:" + item for item in result.findings)
    return DryRunExecutionValidationResult(not f, tuple(f))


def validate_dry_run_execution_request(request: DryRunExecutionRequest | Mapping[str, Any]) -> DryRunExecutionValidationResult:
    p = _source_payload(request)
    f = _validate_common(p, prefix="request:", status_field="request_status", statuses=DRY_RUN_REQUEST_STATUSES, only_field="dry_run_request_only", digest_fn=dry_run_execution_request_digest)
    if not p.get("does_not_execute_real_backend", False):
        f.append("request:may_execute_real_backend")
    if p.get("requested_dry_run_domain") not in DRY_RUN_DOMAINS:
        f.append("request:unknown_dry_run_domain")
    if p.get("requested_simulated_backend_class") not in SIMULATED_BACKEND_CLASSES:
        f.append("request:unknown_simulated_backend_class")
    return DryRunExecutionValidationResult(not f, tuple(f))


def validate_dry_run_execution_result(result: DryRunExecutionResult | Mapping[str, Any]) -> DryRunExecutionValidationResult:
    p = _source_payload(result)
    f = _validate_common(p, prefix="result:", status_field="result_status", statuses=DRY_RUN_RESULT_STATUSES, only_field="simulated_only", digest_fn=dry_run_execution_result_digest)
    if p.get("dry_run_executed") is not True:
        f.append("result:dry_run_not_executed")
    if p.get("dry_run_domain") not in DRY_RUN_DOMAINS:
        f.append("result:unknown_dry_run_domain")
    if p.get("simulated_backend_class") not in SIMULATED_BACKEND_CLASSES:
        f.append("result:unknown_simulated_backend_class")
    return DryRunExecutionValidationResult(not f, tuple(f))


def validate_dry_run_execution_receipt(receipt: DryRunExecutionReceipt | Mapping[str, Any]) -> DryRunExecutionValidationResult:
    p = _source_payload(receipt)
    f = _validate_common(p, prefix="receipt:", status_field="receipt_status", statuses=DRY_RUN_RECEIPT_STATUSES, only_field="dry_run_receipt_only", digest_fn=dry_run_execution_receipt_digest)
    if p.get("dry_run_executed") is not True:
        f.append("receipt:dry_run_not_executed")
    return DryRunExecutionValidationResult(not f, tuple(f))


def validate_dry_run_execution_block_receipt(receipt: DryRunExecutionBlockReceipt | Mapping[str, Any]) -> DryRunExecutionValidationResult:
    p = _source_payload(receipt)
    f = _validate_common(p, prefix="block_receipt:", status_field="block_status", statuses=DRY_RUN_RECEIPT_STATUSES, only_field="block_receipt_only", digest_fn=dry_run_execution_block_receipt_digest)
    if p.get("dry_run_executed", True):
        f.append("block_receipt:dry_run_executed")
    if not p.get("does_not_execute", False):
        f.append("block_receipt:may_execute")
    if not p.get("does_not_mutate_host", False):
        f.append("block_receipt:may_mutate_host")
    return DryRunExecutionValidationResult(not f, tuple(f))


def summarize_simulated_backend_registry(registry: SimulatedBackendRegistry | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(registry)
    return {k: p.get(k) for k in ("registry_id", "supported_backend_classes", "supported_dry_run_domains", "blocked_actions", "registry_status", "metadata_only", "simulated_only", "no_real_backends", "host_mutation_performed", "digest")}


def summarize_dry_run_execution_request(request: DryRunExecutionRequest | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(request)
    return {k: p.get(k) for k in ("request_id", "source_executor_readiness_receipt_id", "source_executor_contract_id", "requested_dry_run_domain", "requested_simulated_backend_class", "request_status", "metadata_only", "dry_run_request_only", "does_not_execute_real_backend", "host_mutation_performed", "digest")}


def summarize_dry_run_execution_result(result: DryRunExecutionResult | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(result)
    return {k: p.get(k) for k in ("result_id", "request_id", "simulated_backend_id", "dry_run_domain", "simulated_backend_class", "result_status", "metadata_only", "simulated_only", "dry_run_executed", "real_backend_invoked", "real_fulfillment_performed", "real_effect_performed", "effect_performed", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed", "subprocess_execution_performed", "shell_execution_performed", "os_backend_invoked", "control_plane_admission_execution_performed", "digest")}


def summarize_dry_run_execution_receipt(receipt: DryRunExecutionReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(receipt)
    return {k: p.get(k) for k in ("receipt_id", "request_id", "result_id", "source_executor_readiness_receipt_id", "dry_run_domain", "simulated_backend_class", "receipt_status", "metadata_only", "dry_run_receipt_only", "dry_run_executed", "real_fulfillment_performed", "real_effect_performed", "real_backend_invoked", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "provider_invocation_performed", "network_performed", "prompt_assembly_performed", "subprocess_execution_performed", "shell_execution_performed", "os_backend_invoked", "control_plane_admission_execution_performed", "digest")}


def summarize_dry_run_execution_block_receipt(receipt: DryRunExecutionBlockReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(receipt)
    return {k: p.get(k) for k in ("receipt_id", "request_id", "source_executor_readiness_receipt_id", "block_status", "block_reason_codes", "missing_labels", "metadata_only", "block_receipt_only", "dry_run_executed", "real_fulfillment_performed", "host_mutation_performed", "does_not_execute", "does_not_mutate_host", "digest")}


def build_dry_run_execution_harness_wing(
    executor_readiness_receipt: ExecutorContractReadinessReceipt | Mapping[str, Any],
    *,
    registry: SimulatedBackendRegistry | Mapping[str, Any] | None = None,
    requested_dry_run_domain: str | None = None,
    requested_simulated_backend_class: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> DryRunExecutionHarnessWingRecords:
    simulated_registry = registry if isinstance(registry, SimulatedBackendRegistry) else build_default_simulated_backend_registry(created_at=created_at)
    request = build_dry_run_execution_request(
        executor_readiness_receipt,
        requested_dry_run_domain=requested_dry_run_domain,
        requested_simulated_backend_class=requested_simulated_backend_class,
        created_at=created_at,
    )
    result_or_block = run_dry_run_execution(request, simulated_registry, created_at=created_at)
    receipt = build_dry_run_execution_receipt(request, result_or_block, created_at=created_at) if isinstance(result_or_block, DryRunExecutionResult) else None
    return DryRunExecutionHarnessWingRecords(simulated_registry, request, result_or_block, receipt)
