"""Reviewer-facing non-mutating host embodiment trace artifacts.

The trace builder uses supplied fake/sample telemetry by default. It does not
collect live host data unless callers explicitly pass already-built records, and
it never mutates host state, opens network egress, invokes providers, assembles
prompts, executes host actions, or grants authorization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence

from sentientos.actuation_fulfillment import (
    build_actuation_fulfillment_plan,
    build_actuation_fulfillment_rehearsal_receipt,
    summarize_actuation_fulfillment_plan,
    summarize_actuation_fulfillment_rehearsal_receipt,
)
from sentientos.authorization_review import (
    build_authorization_review_wing_for_execution_readiness,
    summarize_authorization_review_decision,
    summarize_authorization_review_packet,
    summarize_authorization_review_receipt,
    summarize_future_authorization_grant_schema,
)
from sentientos.controlled_authorization import (
    BLOCKED_ACTION_LABELS,
    build_controlled_authorization_wing_for_review_receipt,
    summarize_controlled_authorization_grant_contract,
    summarize_controlled_authorization_grant_record,
    summarize_controlled_authorization_ledger,
    summarize_controlled_authorization_revocation_record,
)
from sentientos.effect_proof import (
    build_execution_proof_wing_for_rehearsal_receipt,
    summarize_effect_receipt_contract,
    summarize_execution_readiness_manifest,
    summarize_future_effect_receipt_schema,
    summarize_postcondition_check_plan,
    summarize_rollback_plan,
)
from sentientos.host_collectors import collect_fan_pwm_observation, collect_thermal_sensor_observation
from sentientos.host_inventory import build_host_inventory_from_collector_results, summarize_host_inventory_manifest
from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results, evaluate_host_resource_pressure, summarize_host_resource_pressure
from sentientos.host_resource_policy import build_host_resource_proposal_receipts, evaluate_host_resource_policy, summarize_host_resource_policy_decision, summarize_host_resource_proposal_receipt
from sentientos.privilege_broker import build_privilege_broker_review_receipt, evaluate_privilege_broker_eligibility, summarize_privilege_broker_eligibility_decision, summarize_privilege_broker_review_receipt

HOST_EMBODIMENT_TRACE_STATUSES = frozenset({
    "host_embodiment_trace_recorded",
    "host_embodiment_trace_recorded_with_warnings",
    "host_embodiment_trace_blocked",
    "host_embodiment_trace_incomplete",
    "host_embodiment_trace_contradicted",
})
HOST_EMBODIMENT_TRACE_STEP_KINDS = frozenset({
    "collector_result",
    "host_inventory_manifest",
    "telemetry_snapshot",
    "pressure_report",
    "policy_decision",
    "proposal_receipt",
    "broker_decision",
    "broker_review_receipt",
    "fulfillment_plan",
    "fulfillment_rehearsal_receipt",
    "effect_contract",
    "future_effect_schema",
    "postcondition_plan",
    "rollback_plan",
    "execution_readiness_manifest",
    "authorization_review_packet",
    "authorization_review_decision",
    "authorization_review_receipt",
    "future_authorization_schema",
    "controlled_authorization_contract",
    "controlled_authorization_grant_record",
    "controlled_authorization_revocation_record",
    "controlled_authorization_ledger",
})
TRACE_BLOCKED_ACTION_LABELS = tuple(sorted(set(BLOCKED_ACTION_LABELS) | {"fan_pwm_write", "thermal_actuation", "power_profile_mutation", "service_restart", "process_kill", "file_cleanup", "file_delete", "provider_invocation", "network_egress", "prompt_assembly", "federation_transport", "remote_execution"}))
TRACE_DEFERRED_CAPABILITY_LABELS = (
    "live_authorization_grant",
    "real_effect_execution",
    "real_rollback_execution",
    "real_fan_pwm_control",
    "real_thermal_actuation",
    "real_power_profile_mutation",
    "real_service_restart",
    "real_process_kill",
    "real_file_cleanup",
    "real_file_delete",
    "network_egress",
    "provider_invocation",
    "prompt_assembly",
    "federation_transport",
    "remote_execution",
)

@dataclass(frozen=True)
class HostEmbodimentTraceStep:
    step_id: str
    step_kind: str
    source_id: str
    source_digest: str
    status: str
    summary: Mapping[str, Any]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    metadata_only: bool = True
    effect_performed: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostEmbodimentTrace:
    trace_id: str
    scenario_id: str
    scenario_label: str
    steps: tuple[HostEmbodimentTraceStep, ...]
    trace_status: str
    step_count: int
    blocked_action_labels: tuple[str, ...]
    deferred_capability_labels: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    demo_only: bool = True
    live_authorization_granted: bool = False
    effect_performed: bool = False
    host_mutation_performed: bool = False
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostEmbodimentTraceValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest_payload(prefix: str, payload: Mapping[str, Any], length: int = 24) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:length]


def _record_digest(value: Any) -> str:
    if hasattr(value, "to_dict"):
        payload = value.to_dict()
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        payload = {"repr": repr(value)}
    if "digest" in payload:
        payload["digest"] = ""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def host_embodiment_trace_digest(trace: HostEmbodimentTrace) -> str:
    return _record_digest(trace)


def _source_id(value: Any, *names: str) -> str:
    for name in names:
        attr = getattr(value, name, None)
        if attr:
            return str(attr)
    return _digest_payload("src_", {"digest": _source_digest(value)}, 12)


def _source_digest(value: Any) -> str:
    digest = getattr(value, "digest", None)
    if digest:
        return str(digest)
    return _record_digest(value)


def _warnings(value: Any) -> tuple[str, ...]:
    codes = list(getattr(value, "warning_codes", ()) or getattr(value, "warnings", ()) or ())
    return tuple(str(code) for code in codes)


def _risks(value: Any) -> tuple[str, ...]:
    codes = list(getattr(value, "risk_codes", ()) or getattr(value, "risks", ()) or ())
    return tuple(str(code) for code in codes)


def _step(kind: str, value: Any, *, summary: Mapping[str, Any], status: str, id_names: Sequence[str]) -> HostEmbodimentTraceStep:
    source_id = _source_id(value, *id_names)
    provisional = HostEmbodimentTraceStep(
        step_id=_digest_payload("hets_", {"kind": kind, "source": source_id, "digest": _source_digest(value)}),
        step_kind=kind,
        source_id=source_id,
        source_digest=_source_digest(value),
        status=str(status),
        summary=dict(summary),
        warning_codes=_warnings(value),
        risk_codes=_risks(value),
    )
    return provisional


def _collector_demo_results(created_at: str) -> tuple[Any, ...]:
    def list_dir(path: str) -> tuple[str, ...]:
        mapping = {
            "/thermal": ("thermal_zone0",),
            "/hwmon": ("hwmon0",),
            "/hwmon/hwmon0": ("temp1_input", "fan1_input", "pwm1"),
        }
        return mapping.get(path, ())

    def read_text(path: str) -> str:
        if path.endswith("/thermal_zone0/temp") or path.endswith("temp1_input"):
            return "91000\n"
        if path.endswith("/thermal_zone0/type"):
            return "x86_pkg_temp\n"
        if path.endswith("fan1_input"):
            return "1800\n"
        if path.endswith("pwm1"):
            return "128\n"
        return ""

    thermal = collect_thermal_sensor_observation(thermal_path="/thermal", hwmon_path="/hwmon", directory_lister=list_dir, text_reader=read_text, observed_at=created_at)
    fan_pwm = collect_fan_pwm_observation(hwmon_path="/hwmon", directory_lister=list_dir, text_reader=read_text, observed_at=created_at)
    return (thermal, fan_pwm)


def build_host_embodiment_demo_trace(
    *,
    collector_results: Sequence[Any] | None = None,
    scenario_id: str = "demo-thermal-pwm-non-mutating-ladder",
    scenario_label: str = "Thermal + PWM presence proves telemetry is not control authority",
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> HostEmbodimentTrace:
    results = tuple(collector_results) if collector_results is not None else _collector_demo_results(created_at)
    inventory = build_host_inventory_from_collector_results(results, manifest_id=f"{scenario_id}-inventory", node_id="review-demo-node", host_id="review-demo-host")
    snapshot = build_host_resource_telemetry_from_collector_results(results, snapshot_id=f"{scenario_id}-telemetry")
    pressure = evaluate_host_resource_pressure(snapshot, thermal_pressure_c=80)
    policy_decision = evaluate_host_resource_policy(pressure)
    proposal_receipts = build_host_resource_proposal_receipts(policy_decision)
    proposal = next((receipt for receipt in proposal_receipts if receipt.proposal_kind == "future_cooling_policy_candidate"), proposal_receipts[0])
    broker_decision = evaluate_privilege_broker_eligibility(proposal)
    broker_receipt = build_privilege_broker_review_receipt(broker_decision, created_at=created_at)
    fulfillment_plan = build_actuation_fulfillment_plan(broker_receipt)
    rehearsal_receipt = build_actuation_fulfillment_rehearsal_receipt(fulfillment_plan, created_at=created_at)
    proof = build_execution_proof_wing_for_rehearsal_receipt(rehearsal_receipt, created_at=created_at)
    review = build_authorization_review_wing_for_execution_readiness(proof.execution_readiness_manifest, created_at=created_at)
    controlled = build_controlled_authorization_wing_for_review_receipt(review.receipt, review.future_authorization_grant_schema, created_at=created_at)

    steps: list[HostEmbodimentTraceStep] = []
    for result in results:
        steps.append(_step("collector_result", result, summary={"collector_id": result.collector_id, "status": result.status, "telemetry_only": result.telemetry_only, "values": result.values}, status=result.status, id_names=("collector_id",)))
    steps.extend([
        _step("host_inventory_manifest", inventory, summary=summarize_host_inventory_manifest(inventory), status="recorded", id_names=("manifest_id",)),
        _step("telemetry_snapshot", snapshot, summary={"snapshot_id": snapshot.snapshot_id, "thermal_zone_temperatures_c": dict(snapshot.thermal_zone_temperatures_c), "fan_rpm_observations": dict(snapshot.fan_rpm_observations), "model_runtime_pressure_labels": snapshot.model_runtime_pressure_labels, "metadata_only": snapshot.metadata_only, "no_host_actuation": snapshot.no_host_actuation}, status="recorded", id_names=("snapshot_id",)),
        _step("pressure_report", pressure, summary=summarize_host_resource_pressure(pressure), status="recorded", id_names=("report_id",)),
        _step("policy_decision", policy_decision, summary=summarize_host_resource_policy_decision(policy_decision), status=policy_decision.status, id_names=("decision_id",)),
        _step("proposal_receipt", proposal, summary=summarize_host_resource_proposal_receipt(proposal), status=proposal.proposal_status, id_names=("receipt_id",)),
        _step("broker_decision", broker_decision, summary=summarize_privilege_broker_eligibility_decision(broker_decision), status=broker_decision.eligibility_status, id_names=("decision_id",)),
        _step("broker_review_receipt", broker_receipt, summary=summarize_privilege_broker_review_receipt(broker_receipt), status=broker_receipt.review_status, id_names=("receipt_id",)),
        _step("fulfillment_plan", fulfillment_plan, summary=summarize_actuation_fulfillment_plan(fulfillment_plan), status=fulfillment_plan.plan_status, id_names=("plan_id",)),
        _step("fulfillment_rehearsal_receipt", rehearsal_receipt, summary=summarize_actuation_fulfillment_rehearsal_receipt(rehearsal_receipt), status=rehearsal_receipt.rehearsal_status, id_names=("receipt_id",)),
        _step("effect_contract", proof.effect_contract, summary=summarize_effect_receipt_contract(proof.effect_contract), status=proof.effect_contract.status, id_names=("contract_id",)),
        _step("future_effect_schema", proof.future_effect_receipt, summary=summarize_future_effect_receipt_schema(proof.future_effect_receipt), status=proof.future_effect_receipt.status, id_names=("receipt_id",)),
        _step("postcondition_plan", proof.postcondition_plan, summary=summarize_postcondition_check_plan(proof.postcondition_plan), status=proof.postcondition_plan.status, id_names=("plan_id",)),
        _step("rollback_plan", proof.rollback_plan, summary=summarize_rollback_plan(proof.rollback_plan), status=proof.rollback_plan.status, id_names=("plan_id",)),
        _step("execution_readiness_manifest", proof.execution_readiness_manifest, summary=summarize_execution_readiness_manifest(proof.execution_readiness_manifest), status=proof.execution_readiness_manifest.readiness_status, id_names=("manifest_id",)),
        _step("authorization_review_packet", review.packet, summary=summarize_authorization_review_packet(review.packet), status=review.packet.packet_status, id_names=("packet_id",)),
        _step("authorization_review_decision", review.decision, summary=summarize_authorization_review_decision(review.decision), status=review.decision.decision_status, id_names=("decision_id",)),
        _step("authorization_review_receipt", review.receipt, summary=summarize_authorization_review_receipt(review.receipt), status=review.receipt.receipt_status, id_names=("receipt_id",)),
        _step("future_authorization_schema", review.future_authorization_grant_schema, summary=summarize_future_authorization_grant_schema(review.future_authorization_grant_schema), status=review.future_authorization_grant_schema.schema_status, id_names=("schema_id",)),
        _step("controlled_authorization_contract", controlled.contract, summary=summarize_controlled_authorization_grant_contract(controlled.contract), status=controlled.contract.status, id_names=("contract_id",)),
        _step("controlled_authorization_grant_record", controlled.grant_record, summary=summarize_controlled_authorization_grant_record(controlled.grant_record), status=controlled.grant_record.grant_status, id_names=("grant_record_id",)),
        _step("controlled_authorization_revocation_record", controlled.revocation_record, summary=summarize_controlled_authorization_revocation_record(controlled.revocation_record), status=controlled.revocation_record.revocation_status, id_names=("revocation_id",)),
        _step("controlled_authorization_ledger", controlled.ledger, summary=summarize_controlled_authorization_ledger(controlled.ledger), status=controlled.ledger.ledger_status, id_names=("ledger_id",)),
    ])
    warnings = tuple(sorted({warning for step in steps for warning in step.warning_codes}))
    risks = tuple(sorted({risk for step in steps for risk in step.risk_codes} | {"pwm_presence_is_not_control_authority", "demo_trace_is_reviewer_proof_only"}))
    if any("contradicted" in step.status for step in steps):
        trace_status = "host_embodiment_trace_contradicted"
    elif any("incomplete" in step.status for step in steps):
        trace_status = "host_embodiment_trace_incomplete"
    elif any("blocked" in step.status for step in steps):
        trace_status = "host_embodiment_trace_blocked"
    elif warnings:
        trace_status = "host_embodiment_trace_recorded_with_warnings"
    else:
        trace_status = "host_embodiment_trace_recorded"
    provisional = HostEmbodimentTrace(
        trace_id=_digest_payload("het_", {"scenario_id": scenario_id, "steps": [step.step_id for step in steps], "created_at": created_at}),
        scenario_id=scenario_id,
        scenario_label=scenario_label,
        steps=tuple(steps),
        trace_status=trace_status,
        step_count=len(steps),
        blocked_action_labels=TRACE_BLOCKED_ACTION_LABELS,
        deferred_capability_labels=TRACE_DEFERRED_CAPABILITY_LABELS,
        warning_codes=warnings,
        risk_codes=risks,
        created_at=created_at,
        digest="",
    )
    return replace(provisional, digest=host_embodiment_trace_digest(provisional))


def validate_host_embodiment_trace_step(step: HostEmbodimentTraceStep) -> HostEmbodimentTraceValidationResult:
    findings: list[str] = []
    if step.step_kind not in HOST_EMBODIMENT_TRACE_STEP_KINDS: findings.append("unknown_step_kind")
    if not step.metadata_only: findings.append("step_not_metadata_only")
    if step.effect_performed: findings.append("step_claims_effect")
    if step.host_mutation_performed: findings.append("step_claims_host_mutation")
    if not step.source_id: findings.append("missing_source_id")
    if not step.source_digest: findings.append("missing_source_digest")
    return HostEmbodimentTraceValidationResult(not findings, tuple(findings))


def validate_host_embodiment_trace(trace: HostEmbodimentTrace) -> HostEmbodimentTraceValidationResult:
    findings: list[str] = []
    if trace.trace_status not in HOST_EMBODIMENT_TRACE_STATUSES: findings.append("unknown_trace_status")
    if not trace.metadata_only or not trace.demo_only: findings.append("trace_not_metadata_demo_only")
    for flag in ("live_authorization_granted", "effect_performed", "host_mutation_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed"):
        if getattr(trace, flag, False): findings.append(f"trace_forbidden_flag:{flag}")
    if trace.step_count != len(trace.steps): findings.append("trace_step_count_mismatch")
    required_blocks = {"fan_pwm_write", "thermal_actuation", "power_profile_mutation", "service_restart", "process_kill", "file_cleanup", "file_delete", "provider_invocation", "network_egress", "prompt_assembly", "federation_transport", "remote_execution"}
    if not required_blocks.issubset(set(trace.blocked_action_labels)): findings.append("trace_missing_required_blocked_actions")
    required_deferred = {"live_authorization_grant", "real_effect_execution", "real_fan_pwm_control", "real_power_profile_mutation", "real_file_cleanup"}
    if not required_deferred.issubset(set(trace.deferred_capability_labels)): findings.append("trace_missing_required_deferred_capabilities")
    for step in trace.steps:
        if not validate_host_embodiment_trace_step(step).ok: findings.append(f"invalid_trace_step:{step.step_id}")
    if trace.digest and trace.digest != host_embodiment_trace_digest(trace): findings.append("trace_digest_mismatch")
    return HostEmbodimentTraceValidationResult(not findings, tuple(findings))


def summarize_host_embodiment_trace(trace: HostEmbodimentTrace) -> dict[str, Any]:
    return {
        "trace_id": trace.trace_id,
        "scenario_id": trace.scenario_id,
        "scenario_label": trace.scenario_label,
        "trace_status": trace.trace_status,
        "step_count": trace.step_count,
        "step_kinds": tuple(step.step_kind for step in trace.steps),
        "metadata_only": trace.metadata_only,
        "demo_only": trace.demo_only,
        "live_authorization_granted": trace.live_authorization_granted,
        "effect_performed": trace.effect_performed,
        "host_mutation_performed": trace.host_mutation_performed,
        "network_performed": trace.network_performed,
        "provider_invocation_performed": trace.provider_invocation_performed,
        "prompt_assembly_performed": trace.prompt_assembly_performed,
        "blocked_action_labels": trace.blocked_action_labels,
        "deferred_capability_labels": trace.deferred_capability_labels,
        "digest": trace.digest,
    }
