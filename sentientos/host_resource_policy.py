"""Proposal-only host resource policy receipts for SentientOS Phase 3.

This module turns read-only host resource pressure reports into deterministic,
metadata-only policy decisions and proposal receipts. It never performs host
mutation, fan/PWM writes, thermal actuation, process control, service restart,
package or driver installation, provider invocation, network activity, prompt
assembly, federation transport, or remote execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping, Sequence

from sentientos.host_resource_governor import HostResourcePressureReport, host_resource_report_digest

HOST_RESOURCE_POLICY_STATUSES = frozenset(
    {
        "host_resource_policy_nominal",
        "host_resource_policy_monitor",
        "host_resource_policy_proposal_ready",
        "host_resource_policy_operator_review_required",
        "host_resource_policy_blocked",
        "host_resource_policy_incomplete",
        "host_resource_policy_contradicted",
    }
)
HOST_RESOURCE_PROPOSAL_STATUSES = frozenset(
    {
        "host_resource_proposal_recorded",
        "host_resource_proposal_recorded_with_warnings",
        "host_resource_proposal_blocked",
        "host_resource_proposal_incomplete",
        "host_resource_proposal_contradicted",
    }
)
HOST_RESOURCE_PROPOSAL_KINDS = frozenset(
    {
        "reduce_model_load_candidate",
        "defer_heavy_task_candidate",
        "request_operator_review_candidate",
        "inspect_thermal_state_candidate",
        "inspect_disk_pressure_candidate",
        "inspect_memory_pressure_candidate",
        "inspect_cpu_pressure_candidate",
        "inspect_gpu_pressure_candidate",
        "inspect_service_health_candidate",
        "future_cooling_policy_candidate",
        "future_power_policy_candidate",
        "future_cleanup_policy_candidate",
    }
)
HOST_RESOURCE_POLICY_SCOPES = frozenset(
    {
        "local_observation_only",
        "operator_review_queue",
        "future_privilege_broker_queue",
        "diagnostics_only",
        "rehearsal_candidate_only",
    }
)

FUTURE_ACTION_GATES = (
    "future_privilege_broker_required",
    "future_control_plane_admission_required",
    "operator_or_policy_approval_required",
    "audit_receipt_required",
    "rollback_receipt_required",
)
BLOCKED_HOST_ACTIONS = (
    "host_mutation",
    "fan_pwm_write",
    "thermal_actuation",
    "process_kill",
    "service_restart",
    "package_install",
    "driver_install",
    "provider_invocation",
    "network_egress",
    "prompt_assembly",
    "federation_transport_sync_adoption",
    "remote_execution",
)

_LABEL_TO_KINDS: Mapping[str, tuple[str, ...]] = {
    "cpu_pressure": ("inspect_cpu_pressure_candidate", "reduce_model_load_candidate", "defer_heavy_task_candidate"),
    "memory_pressure": ("inspect_memory_pressure_candidate", "defer_heavy_task_candidate"),
    "gpu_pressure": ("inspect_gpu_pressure_candidate", "reduce_model_load_candidate", "defer_heavy_task_candidate"),
    "disk_pressure": ("inspect_disk_pressure_candidate", "future_cleanup_policy_candidate"),
    "thermal_pressure": ("inspect_thermal_state_candidate", "future_cooling_policy_candidate"),
    "battery_pressure": ("future_power_policy_candidate", "request_operator_review_candidate"),
    "service_degraded": ("inspect_service_health_candidate",),
    "telemetry_incomplete": ("request_operator_review_candidate",),
    "sensor_unavailable": ("request_operator_review_candidate",),
    "fan_signal_present": (),
    "network_pressure": ("request_operator_review_candidate",),
}


@dataclass(frozen=True)
class HostResourcePolicyRule:
    rule_id: str
    pressure_labels: tuple[str, ...]
    proposal_kinds: tuple[str, ...]
    proposal_scope: str
    reason_codes: tuple[str, ...]
    warning_codes: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ()
    blocked_proposal_kinds: tuple[str, ...] = ()
    required_future_gates: tuple[str, ...] = FUTURE_ACTION_GATES
    metadata_only: bool = True
    proposal_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostResourcePolicyDecision:
    decision_id: str
    report_id: str
    report_digest: str
    host_id: str | None = None
    node_id: str | None = None
    observed_pressure_labels: tuple[str, ...] = ()
    selected_policy_rules: tuple[str, ...] = ()
    proposal_kinds: tuple[str, ...] = ()
    blocked_proposal_kinds: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ()
    required_future_gates: tuple[str, ...] = FUTURE_ACTION_GATES
    status: str = "host_resource_policy_monitor"
    reason_codes: tuple[str, ...] = ()
    metadata_only: bool = True
    proposal_only: bool = True
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
class HostResourceProposalReceipt:
    receipt_id: str
    decision_id: str
    report_id: str
    report_digest: str
    proposal_kind: str
    proposal_status: str
    proposal_scope: str
    pressure_labels: tuple[str, ...]
    evidence_summary: tuple[str, ...]
    required_future_gates: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str = ""
    proposal_only: bool = True
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    not_authorized_for_fulfillment: bool = True
    requires_privilege_broker_for_future_action: bool = True
    requires_control_plane_admission_for_future_action: bool = True
    requires_operator_or_policy_approval_for_future_action: bool = True
    requires_audit_receipt_for_future_action: bool = True
    requires_rollback_receipt_for_future_action: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostResourcePolicyValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


def _tuple_str(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest_payload(prefix: str, payload: Mapping[str, Any], length: int = 24) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:length]


def build_default_host_resource_policy_rules() -> tuple[HostResourcePolicyRule, ...]:
    return (
        HostResourcePolicyRule("nominal_monitor", ("nominal",), (), "local_observation_only", ("nominal_monitor_only",)),
        HostResourcePolicyRule("cpu_pressure_policy", ("cpu_pressure",), _LABEL_TO_KINDS["cpu_pressure"], "operator_review_queue", ("cpu_pressure_observed",)),
        HostResourcePolicyRule("memory_pressure_policy", ("memory_pressure",), _LABEL_TO_KINDS["memory_pressure"], "operator_review_queue", ("memory_pressure_observed",)),
        HostResourcePolicyRule("gpu_pressure_policy", ("gpu_pressure",), _LABEL_TO_KINDS["gpu_pressure"], "operator_review_queue", ("gpu_pressure_observed",)),
        HostResourcePolicyRule("disk_pressure_policy", ("disk_pressure",), _LABEL_TO_KINDS["disk_pressure"], "future_privilege_broker_queue", ("disk_pressure_observed",), blocked_proposal_kinds=("future_cleanup_policy_candidate",)),
        HostResourcePolicyRule("thermal_pressure_policy", ("thermal_pressure",), _LABEL_TO_KINDS["thermal_pressure"], "future_privilege_broker_queue", ("thermal_pressure_observed",), warning_codes=("thermal_pressure_is_not_cooling_authorization",), risk_codes=("future_cooling_requires_privileged_gates",), blocked_proposal_kinds=("future_cooling_policy_candidate",)),
        HostResourcePolicyRule("fan_signal_diagnostics_policy", ("fan_signal_present",), (), "diagnostics_only", ("fan_signal_is_telemetry_only",), warning_codes=("pwm_presence_is_not_control_authority",)),
        HostResourcePolicyRule("service_degraded_policy", ("service_degraded",), _LABEL_TO_KINDS["service_degraded"], "operator_review_queue", ("service_degraded_observed",), blocked_proposal_kinds=("service_restart",)),
        HostResourcePolicyRule("incomplete_telemetry_policy", ("telemetry_incomplete", "sensor_unavailable"), ("request_operator_review_candidate",), "diagnostics_only", ("telemetry_incomplete_or_sensor_unavailable",), warning_codes=("incomplete_telemetry_blocks_automatic_readiness",)),
        HostResourcePolicyRule("unknown_contradiction_policy", ("unknown",), (), "diagnostics_only", ("unknown_or_contradictory_pressure_report",), warning_codes=("proposal_readiness_blocked",)),
    )


def evaluate_host_resource_policy(
    report: HostResourcePressureReport,
    *,
    host_id: str | None = None,
    node_id: str | None = None,
    rules: Sequence[HostResourcePolicyRule] | None = None,
) -> HostResourcePolicyDecision:
    labels = tuple(sorted(str(label) for label in report.pressure_labels))
    report_digest = host_resource_report_digest(report)
    rule_set = tuple(rules or build_default_host_resource_policy_rules())
    selected: list[HostResourcePolicyRule] = []
    proposal_kinds: set[str] = set()
    blocked_kinds: set[str] = set()
    warnings: set[str] = set()
    risks: set[str] = set()
    reasons: set[str] = set()

    for rule in rule_set:
        if set(rule.pressure_labels).intersection(labels):
            selected.append(rule)
            proposal_kinds.update(rule.proposal_kinds)
            blocked_kinds.update(rule.blocked_proposal_kinds)
            warnings.update(rule.warning_codes)
            risks.update(rule.risk_codes)
            reasons.update(rule.reason_codes)

    candidate_kinds = {candidate.kind for candidate in report.proposal_candidates}
    for label in labels:
        proposal_kinds.update(_LABEL_TO_KINDS.get(label, ()))
    proposal_kinds.update(kind for kind in candidate_kinds if kind in HOST_RESOURCE_PROPOSAL_KINDS)

    unknown_candidate_kinds = sorted(kind for kind in candidate_kinds if kind not in HOST_RESOURCE_PROPOSAL_KINDS)
    if unknown_candidate_kinds:
        warnings.add("unknown_candidate_kind_observed")
        blocked_kinds.update(unknown_candidate_kinds)

    if "nominal" in labels and len(labels) > 1:
        status = "host_resource_policy_contradicted"
        reasons.add("nominal_with_pressure_labels")
    elif "unknown" in labels:
        status = "host_resource_policy_blocked"
        reasons.add("unknown_pressure_label_blocks_proposal_readiness")
    elif "telemetry_incomplete" in labels or "sensor_unavailable" in labels:
        status = "host_resource_policy_incomplete"
        reasons.add("incomplete_telemetry_requires_review")
        proposal_kinds.add("request_operator_review_candidate")
    elif labels == ("nominal",):
        status = "host_resource_policy_nominal"
        reasons.add("nominal_monitor_only")
    elif labels == ("fan_signal_present",) or set(labels).issubset({"fan_signal_present"}):
        status = "host_resource_policy_monitor"
        reasons.add("fan_pwm_observation_is_diagnostics_only")
        warnings.add("pwm_presence_is_not_control_authority")
    elif proposal_kinds:
        status = "host_resource_policy_proposal_ready"
        reasons.add("pressure_report_mapped_to_proposal_receipts")
    else:
        status = "host_resource_policy_operator_review_required"
        reasons.add("no_deterministic_policy_mapping")
        proposal_kinds.add("request_operator_review_candidate")

    if "service_degraded" in labels:
        blocked_kinds.add("service_restart")
    if "fan_signal_present" in labels:
        warnings.add("fan_pwm_signal_is_observation_only")
    if "thermal_pressure" in labels:
        blocked_kinds.add("future_cooling_policy_candidate")
    if "disk_pressure" in labels:
        blocked_kinds.add("future_cleanup_policy_candidate")

    material = {
        "report_id": report.report_id,
        "report_digest": report_digest,
        "host_id": host_id,
        "node_id": node_id,
        "labels": labels,
        "rules": sorted(rule.rule_id for rule in selected),
        "proposal_kinds": sorted(proposal_kinds),
        "blocked_proposal_kinds": sorted(blocked_kinds),
        "status": status,
        "reasons": sorted(reasons),
    }
    decision_id = _digest_payload("hrpd_", material)
    return HostResourcePolicyDecision(
        decision_id=decision_id,
        report_id=report.report_id,
        report_digest=report_digest,
        host_id=host_id,
        node_id=node_id,
        observed_pressure_labels=labels,
        selected_policy_rules=tuple(sorted(rule.rule_id for rule in selected)),
        proposal_kinds=tuple(sorted(proposal_kinds)),
        blocked_proposal_kinds=tuple(sorted(blocked_kinds)),
        warning_codes=tuple(sorted(warnings)),
        risk_codes=tuple(sorted(risks)),
        required_future_gates=FUTURE_ACTION_GATES,
        status=status,
        reason_codes=tuple(sorted(reasons)),
    )


def _proposal_scope(proposal_kind: str, decision: HostResourcePolicyDecision) -> str:
    if decision.status in {"host_resource_policy_blocked", "host_resource_policy_contradicted"}:
        return "diagnostics_only"
    if proposal_kind.startswith("future_"):
        return "future_privilege_broker_queue"
    if proposal_kind.startswith("inspect_"):
        return "diagnostics_only"
    if proposal_kind == "request_operator_review_candidate":
        return "operator_review_queue"
    return "rehearsal_candidate_only"


def build_host_resource_proposal_receipts(
    decision: HostResourcePolicyDecision,
    *,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> tuple[HostResourceProposalReceipt, ...]:
    receipts: list[HostResourceProposalReceipt] = []
    for proposal_kind in decision.proposal_kinds:
        if decision.status == "host_resource_policy_contradicted":
            proposal_status = "host_resource_proposal_contradicted"
        elif decision.status == "host_resource_policy_blocked" or proposal_kind in decision.blocked_proposal_kinds:
            proposal_status = "host_resource_proposal_blocked"
        elif decision.status == "host_resource_policy_incomplete":
            proposal_status = "host_resource_proposal_incomplete"
        elif decision.warning_codes:
            proposal_status = "host_resource_proposal_recorded_with_warnings"
        else:
            proposal_status = "host_resource_proposal_recorded"
        scope = _proposal_scope(proposal_kind, decision)
        evidence = (
            f"decision_status:{decision.status}",
            f"pressure_label_count:{len(decision.observed_pressure_labels)}",
            "pressure_is_not_action",
            "policy_decision_is_not_authorization",
        )
        material = {
            "decision_id": decision.decision_id,
            "report_id": decision.report_id,
            "report_digest": decision.report_digest,
            "proposal_kind": proposal_kind,
            "proposal_status": proposal_status,
            "proposal_scope": scope,
            "pressure_labels": decision.observed_pressure_labels,
            "created_at": created_at,
            "required_future_gates": decision.required_future_gates,
            "blocked_actions": BLOCKED_HOST_ACTIONS,
            "warning_codes": decision.warning_codes,
            "risk_codes": decision.risk_codes,
        }
        receipt_id = _digest_payload("hrpr_", material)
        provisional = HostResourceProposalReceipt(
            receipt_id=receipt_id,
            decision_id=decision.decision_id,
            report_id=decision.report_id,
            report_digest=decision.report_digest,
            proposal_kind=proposal_kind,
            proposal_status=proposal_status,
            proposal_scope=scope,
            pressure_labels=decision.observed_pressure_labels,
            evidence_summary=evidence,
            required_future_gates=decision.required_future_gates,
            blocked_actions=BLOCKED_HOST_ACTIONS,
            warning_codes=decision.warning_codes,
            risk_codes=decision.risk_codes,
            created_at=created_at,
        )
        receipts.append(replace(provisional, digest=host_resource_proposal_receipt_digest(provisional)))
    return tuple(sorted(receipts, key=lambda receipt: receipt.receipt_id))


def host_resource_policy_decision_digest(decision: HostResourcePolicyDecision) -> str:
    return hashlib.sha256(_canonical_json(decision.to_dict()).encode("utf-8")).hexdigest()


def host_resource_proposal_receipt_digest(receipt: HostResourceProposalReceipt) -> str:
    payload = receipt.to_dict()
    payload["digest"] = ""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def summarize_host_resource_policy_decision(decision: HostResourcePolicyDecision) -> dict[str, Any]:
    return {
        "decision_id": decision.decision_id,
        "report_id": decision.report_id,
        "report_digest": decision.report_digest,
        "status": decision.status,
        "pressure_labels": decision.observed_pressure_labels,
        "selected_policy_rule_count": len(decision.selected_policy_rules),
        "proposal_kind_count": len(decision.proposal_kinds),
        "blocked_proposal_kind_count": len(decision.blocked_proposal_kinds),
        "warning_count": len(decision.warning_codes),
        "risk_count": len(decision.risk_codes),
        "metadata_only": decision.metadata_only,
        "proposal_only": decision.proposal_only,
        "host_mutation_performed": decision.host_mutation_performed,
        "fan_pwm_write_performed": decision.fan_pwm_write_performed,
        "thermal_actuation_performed": decision.thermal_actuation_performed,
        "network_performed": decision.network_performed,
        "digest": host_resource_policy_decision_digest(decision),
    }


def summarize_host_resource_proposal_receipt(receipt: HostResourceProposalReceipt) -> dict[str, Any]:
    return {
        "receipt_id": receipt.receipt_id,
        "decision_id": receipt.decision_id,
        "report_id": receipt.report_id,
        "proposal_kind": receipt.proposal_kind,
        "proposal_status": receipt.proposal_status,
        "proposal_scope": receipt.proposal_scope,
        "pressure_labels": receipt.pressure_labels,
        "future_gate_count": len(receipt.required_future_gates),
        "blocked_action_count": len(receipt.blocked_actions),
        "warning_count": len(receipt.warning_codes),
        "risk_count": len(receipt.risk_codes),
        "proposal_only": receipt.proposal_only,
        "does_not_execute": receipt.does_not_execute,
        "does_not_mutate_host": receipt.does_not_mutate_host,
        "not_authorized_for_fulfillment": receipt.not_authorized_for_fulfillment,
        "digest": receipt.digest,
    }


def validate_host_resource_policy_decision(decision: HostResourcePolicyDecision) -> HostResourcePolicyValidationResult:
    findings: list[str] = []
    if not decision.decision_id:
        findings.append("missing_decision_id")
    if not decision.report_id:
        findings.append("missing_report_id")
    if decision.status not in HOST_RESOURCE_POLICY_STATUSES:
        findings.append("unknown_policy_status")
    for kind in decision.proposal_kinds:
        if kind not in HOST_RESOURCE_PROPOSAL_KINDS:
            findings.append(f"unknown_proposal_kind:{kind}")
    if not decision.metadata_only or not decision.proposal_only:
        findings.append("decision_not_metadata_proposal_only")
    forbidden_flags = {
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
    for flag, value in forbidden_flags.items():
        if value:
            findings.append(f"forbidden_decision_flag:{flag}")
    return HostResourcePolicyValidationResult(ok=not findings, findings=tuple(findings))


def validate_host_resource_proposal_receipt(receipt: HostResourceProposalReceipt) -> HostResourcePolicyValidationResult:
    findings: list[str] = []
    if not receipt.receipt_id:
        findings.append("missing_receipt_id")
    if not receipt.decision_id:
        findings.append("missing_decision_id")
    if receipt.proposal_kind not in HOST_RESOURCE_PROPOSAL_KINDS:
        findings.append("unknown_proposal_kind")
    if receipt.proposal_status not in HOST_RESOURCE_PROPOSAL_STATUSES:
        findings.append("unknown_proposal_status")
    if receipt.proposal_scope not in HOST_RESOURCE_POLICY_SCOPES:
        findings.append("unknown_proposal_scope")
    if receipt.digest and receipt.digest != host_resource_proposal_receipt_digest(receipt):
        findings.append("receipt_digest_mismatch")
    required_true = {
        "proposal_only": receipt.proposal_only,
        "does_not_execute": receipt.does_not_execute,
        "does_not_mutate_host": receipt.does_not_mutate_host,
        "not_authorized_for_fulfillment": receipt.not_authorized_for_fulfillment,
        "requires_privilege_broker_for_future_action": receipt.requires_privilege_broker_for_future_action,
        "requires_control_plane_admission_for_future_action": receipt.requires_control_plane_admission_for_future_action,
        "requires_operator_or_policy_approval_for_future_action": receipt.requires_operator_or_policy_approval_for_future_action,
        "requires_audit_receipt_for_future_action": receipt.requires_audit_receipt_for_future_action,
        "requires_rollback_receipt_for_future_action": receipt.requires_rollback_receipt_for_future_action,
    }
    for flag, value in required_true.items():
        if not value:
            findings.append(f"receipt_claims_execution_or_authority:{flag}")
    missing_gates = [gate for gate in FUTURE_ACTION_GATES if gate not in receipt.required_future_gates]
    if missing_gates:
        findings.append("receipt_missing_future_gates")
    missing_blocks = [action for action in BLOCKED_HOST_ACTIONS if action not in receipt.blocked_actions]
    if missing_blocks:
        findings.append("receipt_missing_blocked_actions")
    return HostResourcePolicyValidationResult(ok=not findings, findings=tuple(findings))
