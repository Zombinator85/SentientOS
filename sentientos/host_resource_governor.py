"""Read-only host resource pressure governor scaffold for SentientOS Phase 1.

This module classifies supplied telemetry and emits proposal-only candidate
summaries for later governance. It never cools hardware, changes power profiles,
kills processes, restarts services, installs packages, modifies drivers, opens
network authority, invokes providers, assembles prompts, or mutates host state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

PRESSURE_LABELS = frozenset(
    {
        "nominal",
        "cpu_pressure",
        "memory_pressure",
        "gpu_pressure",
        "disk_pressure",
        "network_pressure",
        "thermal_pressure",
        "fan_signal_present",
        "battery_pressure",
        "service_degraded",
        "telemetry_incomplete",
        "sensor_unavailable",
        "unknown",
    }
)
CANDIDATE_KINDS = frozenset(
    {
        "reduce_model_load_candidate",
        "defer_heavy_task_candidate",
        "request_operator_review_candidate",
        "inspect_thermal_state_candidate",
        "inspect_disk_pressure_candidate",
        "inspect_service_health_candidate",
        "future_cooling_policy_candidate",
    }
)
FORBIDDEN_MARKER_KEYS = frozenset(
    {
        "actuation_claimed",
        "host_mutation_claimed",
        "fan_pwm_write_marker",
        "thermal_write_marker",
        "process_kill_marker",
        "service_restart_marker",
        "package_install_marker",
        "driver_install_marker",
        "provider_invocation_marker",
        "network_egress_marker",
        "prompt_assembly_marker",
    }
)


@dataclass(frozen=True)
class HostResourceTelemetrySnapshot:
    snapshot_id: str
    cpu_utilization_percent: float | None = None
    ram_utilization_percent: float | None = None
    gpu_utilization_percent: float | None = None
    vram_utilization_percent: float | None = None
    disk_utilization_percent: float | None = None
    disk_free_bytes: int | None = None
    network_rx_bytes_per_second: float | None = None
    network_tx_bytes_per_second: float | None = None
    process_count: int | None = None
    thermal_zone_temperatures_c: Mapping[str, float] = field(default_factory=dict)
    fan_rpm_observations: Mapping[str, float] = field(default_factory=dict)
    battery_percent: float | None = None
    battery_charging: bool | None = None
    power_profile_label: str | None = None
    model_runtime_pressure_labels: tuple[str, ...] = ()
    service_health_labels: tuple[str, ...] = ()
    unavailable_sensor_labels: tuple[str, ...] = ()
    observed_at: str | None = None
    forbidden_markers: Mapping[str, bool] = field(default_factory=dict)
    metadata_only: bool = True
    no_host_actuation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostResourceProposalCandidate:
    candidate_id: str
    kind: str
    reason_labels: tuple[str, ...]
    summary: str
    proposal_only: bool = True
    does_not_execute: bool = True
    does_not_mutate_host: bool = True
    requires_privilege_broker_for_future_action: bool = True
    requires_control_plane_admission_for_future_action: bool = True
    requires_operator_or_policy_approval_for_future_action: bool = True
    requires_audit_receipt_for_future_action: bool = True
    requires_rollback_receipt_for_future_action: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostResourcePressureReport:
    report_id: str
    snapshot_id: str
    pressure_labels: tuple[str, ...]
    findings: tuple[str, ...]
    proposal_candidates: tuple[HostResourceProposalCandidate, ...]
    metadata_only: bool = True
    observe_model_propose_only: bool = True
    no_host_actuation: bool = True
    no_fan_pwm_writes: bool = True
    no_process_kill_restart_install: bool = True
    no_provider_network_prompt_authority: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostResourceGovernorValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


def _tuple_str(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def build_host_resource_telemetry_snapshot(
    *,
    snapshot_id: str,
    cpu_utilization_percent: float | None = None,
    ram_utilization_percent: float | None = None,
    gpu_utilization_percent: float | None = None,
    vram_utilization_percent: float | None = None,
    disk_utilization_percent: float | None = None,
    disk_free_bytes: int | None = None,
    network_rx_bytes_per_second: float | None = None,
    network_tx_bytes_per_second: float | None = None,
    process_count: int | None = None,
    thermal_zone_temperatures_c: Mapping[str, float] | None = None,
    fan_rpm_observations: Mapping[str, float] | None = None,
    battery_percent: float | None = None,
    battery_charging: bool | None = None,
    power_profile_label: str | None = None,
    model_runtime_pressure_labels: Sequence[str] | None = None,
    service_health_labels: Sequence[str] | None = None,
    unavailable_sensor_labels: Sequence[str] | None = None,
    observed_at: str | None = None,
    forbidden_markers: Mapping[str, bool] | None = None,
) -> HostResourceTelemetrySnapshot:
    return HostResourceTelemetrySnapshot(
        snapshot_id=snapshot_id,
        cpu_utilization_percent=cpu_utilization_percent,
        ram_utilization_percent=ram_utilization_percent,
        gpu_utilization_percent=gpu_utilization_percent,
        vram_utilization_percent=vram_utilization_percent,
        disk_utilization_percent=disk_utilization_percent,
        disk_free_bytes=disk_free_bytes,
        network_rx_bytes_per_second=network_rx_bytes_per_second,
        network_tx_bytes_per_second=network_tx_bytes_per_second,
        process_count=process_count,
        thermal_zone_temperatures_c=dict(thermal_zone_temperatures_c or {}),
        fan_rpm_observations=dict(fan_rpm_observations or {}),
        battery_percent=battery_percent,
        battery_charging=battery_charging,
        power_profile_label=power_profile_label,
        model_runtime_pressure_labels=_tuple_str(model_runtime_pressure_labels),
        service_health_labels=_tuple_str(service_health_labels),
        unavailable_sensor_labels=_tuple_str(unavailable_sensor_labels),
        observed_at=observed_at,
        forbidden_markers=dict(forbidden_markers or {}),
    )


def _candidate(snapshot_id: str, kind: str, reason_labels: Sequence[str], summary: str) -> HostResourceProposalCandidate:
    material = {"snapshot_id": snapshot_id, "kind": kind, "reason_labels": sorted(str(label) for label in reason_labels), "summary": summary}
    candidate_id = "hrc_" + hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    return HostResourceProposalCandidate(candidate_id=candidate_id, kind=kind, reason_labels=tuple(material["reason_labels"]), summary=summary)


def evaluate_host_resource_pressure(
    snapshot: HostResourceTelemetrySnapshot,
    *,
    cpu_pressure_percent: float = 90.0,
    ram_pressure_percent: float = 90.0,
    gpu_pressure_percent: float = 90.0,
    disk_pressure_percent: float = 90.0,
    thermal_pressure_c: float = 85.0,
    battery_low_percent: float = 15.0,
    network_pressure_bytes_per_second: float | None = None,
) -> HostResourcePressureReport:
    labels: set[str] = set()
    findings: list[str] = []
    candidates: list[HostResourceProposalCandidate] = []
    if snapshot.cpu_utilization_percent is None and snapshot.ram_utilization_percent is None and snapshot.disk_utilization_percent is None:
        labels.add("telemetry_incomplete")
        findings.append("core_cpu_ram_disk_telemetry_incomplete")
    if snapshot.unavailable_sensor_labels:
        labels.add("sensor_unavailable")
        findings.append("sensor_unavailable:" + ",".join(sorted(snapshot.unavailable_sensor_labels)))
    if snapshot.cpu_utilization_percent is not None and snapshot.cpu_utilization_percent >= cpu_pressure_percent:
        labels.add("cpu_pressure")
        candidates.append(_candidate(snapshot.snapshot_id, "reduce_model_load_candidate", ("cpu_pressure",), "CPU pressure observed; future governance may reduce model load."))
    if snapshot.ram_utilization_percent is not None and snapshot.ram_utilization_percent >= ram_pressure_percent:
        labels.add("memory_pressure")
        candidates.append(_candidate(snapshot.snapshot_id, "defer_heavy_task_candidate", ("memory_pressure",), "Memory pressure observed; future governance may defer heavy work."))
    if (snapshot.gpu_utilization_percent is not None and snapshot.gpu_utilization_percent >= gpu_pressure_percent) or (snapshot.vram_utilization_percent is not None and snapshot.vram_utilization_percent >= gpu_pressure_percent):
        labels.add("gpu_pressure")
        candidates.append(_candidate(snapshot.snapshot_id, "reduce_model_load_candidate", ("gpu_pressure",), "GPU/VRAM pressure observed; future governance may reduce model load."))
    if snapshot.disk_utilization_percent is not None and snapshot.disk_utilization_percent >= disk_pressure_percent:
        labels.add("disk_pressure")
        candidates.append(_candidate(snapshot.snapshot_id, "inspect_disk_pressure_candidate", ("disk_pressure",), "Disk pressure observed; future governance may inspect storage posture."))
    if network_pressure_bytes_per_second is not None:
        rx = snapshot.network_rx_bytes_per_second or 0.0
        tx = snapshot.network_tx_bytes_per_second or 0.0
        if rx >= network_pressure_bytes_per_second or tx >= network_pressure_bytes_per_second:
            labels.add("network_pressure")
            candidates.append(_candidate(snapshot.snapshot_id, "request_operator_review_candidate", ("network_pressure",), "Network pressure observed; future governance may request operator review."))
    hot_zones = [zone for zone, temp in snapshot.thermal_zone_temperatures_c.items() if temp >= thermal_pressure_c]
    if hot_zones:
        labels.add("thermal_pressure")
        candidates.append(_candidate(snapshot.snapshot_id, "inspect_thermal_state_candidate", ("thermal_pressure",), "Thermal pressure observed; inspect-only candidate, not cooling action."))
        candidates.append(_candidate(snapshot.snapshot_id, "future_cooling_policy_candidate", ("thermal_pressure", "future_only"), "Future cooling policy candidate only; no fan/PWM or thermal writes are performed."))
    if snapshot.fan_rpm_observations:
        labels.add("fan_signal_present")
        findings.append("fan_rpm_observation_is_telemetry_only")
    if snapshot.battery_percent is not None and snapshot.battery_percent <= battery_low_percent and snapshot.battery_charging is not True:
        labels.add("battery_pressure")
        candidates.append(_candidate(snapshot.snapshot_id, "request_operator_review_candidate", ("battery_pressure",), "Battery pressure observed; future governance may ask operator to review."))
    degraded = [label for label in snapshot.service_health_labels if "degraded" in label or "failed" in label or "unhealthy" in label]
    if degraded:
        labels.add("service_degraded")
        candidates.append(_candidate(snapshot.snapshot_id, "inspect_service_health_candidate", ("service_degraded",), "Service degradation label observed; inspect-only candidate."))
    if not labels:
        labels.add("nominal")
    report_id = "hrr_" + hashlib.sha256(json.dumps({"snapshot_id": snapshot.snapshot_id, "labels": sorted(labels), "findings": sorted(findings)}, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    return HostResourcePressureReport(
        report_id=report_id,
        snapshot_id=snapshot.snapshot_id,
        pressure_labels=tuple(sorted(labels)),
        findings=tuple(sorted(findings)),
        proposal_candidates=tuple(sorted(candidates, key=lambda candidate: candidate.candidate_id)),
    )



def build_host_resource_telemetry_from_collector_results(
    results: Sequence[Any],
    *,
    snapshot_id: str = "collector-backed-host-resource-telemetry",
) -> HostResourceTelemetrySnapshot:
    """Build read-only resource telemetry from Phase 2 collector results."""

    from sentientos.host_collectors import HostCollectorResult, validate_host_collector_result

    by_id: dict[str, HostCollectorResult] = {str(result.collector_id): result for result in results if isinstance(result, HostCollectorResult)}
    unavailable: list[str] = []
    service_labels: list[str] = []
    model_labels: list[str] = []
    forbidden_markers: dict[str, bool] = {}
    observed_values = [result.observed_at for result in by_id.values() if result.observed_at]
    observed_at = min(observed_values) if observed_values else None

    for result in by_id.values():
        if result.status in {"unavailable", "partial", "error"}:
            unavailable.append(result.collector_id)
        for finding in validate_host_collector_result(result).findings:
            unavailable.append(f"collector_validation:{finding}")
        for warning in result.warnings:
            if "sensor_unavailable" in warning:
                unavailable.append(warning)
        for key, value in result.forbidden_markers.items():
            if value:
                forbidden_markers[key] = True

    def _collector_values(collector_id: str) -> dict[str, Any]:
        result = by_id.get(collector_id)
        return dict(result.values) if result is not None else {}

    cpu_values = _collector_values("cpu")
    memory_values = _collector_values("memory")
    disk_values = _collector_values("disk")
    process_values = _collector_values("process")
    thermal_values = _collector_values("thermal_sensors")
    fan_values = _collector_values("fan_pwm")
    service_values = _collector_values("service_manager")

    cpu_utilization_percent = cpu_values.get("utilization_percent")
    if cpu_utilization_percent is None and any(key in cpu_values for key in ("load_average_1m", "load_average_5m", "load_average_15m")):
        model_labels.append("cpu_load_average_observed_utilization_unavailable")

    ram_utilization_percent = memory_values.get("used_percent") or memory_values.get("utilization_percent")
    disk_utilization_percent = disk_values.get("used_percent")
    disk_free_bytes = disk_values.get("free_bytes")
    process_count = process_values.get("process_count")

    thermal_zone_temperatures_c: dict[str, float] = {}
    for index, zone in enumerate(tuple(thermal_values.get("zones") or ())):
        if isinstance(zone, Mapping) and zone.get("temperature_c") is not None:
            try:
                thermal_zone_temperatures_c[str(zone.get("id") or zone.get("label") or index)] = float(zone["temperature_c"])
            except (TypeError, ValueError):
                unavailable.append("thermal_temperature_malformed")

    fan_rpm_observations: dict[str, float] = {}
    for index, fan in enumerate(tuple(fan_values.get("fans") or ())):
        if isinstance(fan, Mapping) and fan.get("rpm") is not None:
            try:
                fan_rpm_observations[str(fan.get("id") or index)] = float(fan["rpm"])
            except (TypeError, ValueError):
                unavailable.append("fan_rpm_malformed")
    if fan_values.get("pwm_signal_observed"):
        model_labels.append("pwm_signal_observed_not_control_authority")

    if service_values:
        service_labels.append(str(service_values.get("service_manager_label") or "service_manager_observed"))
        if not service_values.get("live_services_queried", False):
            unavailable.append("service_health_not_queried")

    return build_host_resource_telemetry_snapshot(
        snapshot_id=snapshot_id,
        cpu_utilization_percent=float(cpu_utilization_percent) if cpu_utilization_percent is not None else None,
        ram_utilization_percent=float(ram_utilization_percent) if ram_utilization_percent is not None else None,
        disk_utilization_percent=float(disk_utilization_percent) if disk_utilization_percent is not None else None,
        disk_free_bytes=int(disk_free_bytes) if disk_free_bytes is not None else None,
        process_count=int(process_count) if process_count is not None else None,
        thermal_zone_temperatures_c=thermal_zone_temperatures_c,
        fan_rpm_observations=fan_rpm_observations,
        model_runtime_pressure_labels=tuple(sorted(set(model_labels))),
        service_health_labels=tuple(sorted(set(service_labels))),
        unavailable_sensor_labels=tuple(sorted(set(unavailable))),
        observed_at=observed_at,
        forbidden_markers=forbidden_markers,
    )


def evaluate_current_host_resource_pressure(
    results: Sequence[Any] | None = None,
    *,
    snapshot_id: str = "collector-backed-host-resource-telemetry",
    thermal_pressure_c: float = 85.0,
) -> tuple[HostResourceTelemetrySnapshot, HostResourcePressureReport]:
    """Collect or consume read-only telemetry and evaluate proposal-only pressure."""

    if results is None:
        from sentientos.host_collectors import collect_basic_host_observations

        results = collect_basic_host_observations()
    snapshot = build_host_resource_telemetry_from_collector_results(results, snapshot_id=snapshot_id)
    return snapshot, evaluate_host_resource_pressure(snapshot, thermal_pressure_c=thermal_pressure_c)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def host_resource_report_digest(report: HostResourcePressureReport) -> str:
    return hashlib.sha256(_canonical_json(report.to_dict()).encode("utf-8")).hexdigest()


def summarize_host_resource_pressure(report: HostResourcePressureReport) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "snapshot_id": report.snapshot_id,
        "pressure_labels": report.pressure_labels,
        "finding_count": len(report.findings),
        "proposal_candidate_count": len(report.proposal_candidates),
        "candidate_kinds": tuple(sorted(candidate.kind for candidate in report.proposal_candidates)),
        "metadata_only": report.metadata_only,
        "observe_model_propose_only": report.observe_model_propose_only,
        "no_host_actuation": report.no_host_actuation,
        "no_fan_pwm_writes": report.no_fan_pwm_writes,
        "no_process_kill_restart_install": report.no_process_kill_restart_install,
        "no_provider_network_prompt_authority": report.no_provider_network_prompt_authority,
        "digest": host_resource_report_digest(report),
    }


def validate_host_resource_pressure_report(
    report: HostResourcePressureReport,
    snapshot: HostResourceTelemetrySnapshot,
    *,
    min_temperature_c: float = -100.0,
    max_temperature_c: float = 150.0,
) -> HostResourceGovernorValidationResult:
    findings: list[str] = []
    if not snapshot.snapshot_id:
        findings.append("missing_snapshot_id")
    if report.snapshot_id != snapshot.snapshot_id:
        findings.append("report_snapshot_mismatch")
    percentage_fields = {
        "cpu_utilization_percent": snapshot.cpu_utilization_percent,
        "ram_utilization_percent": snapshot.ram_utilization_percent,
        "gpu_utilization_percent": snapshot.gpu_utilization_percent,
        "vram_utilization_percent": snapshot.vram_utilization_percent,
        "disk_utilization_percent": snapshot.disk_utilization_percent,
        "battery_percent": snapshot.battery_percent,
    }
    for name, value in percentage_fields.items():
        if value is not None and not 0 <= float(value) <= 100:
            findings.append(f"{name}:percent_out_of_range")
    rate_fields = {
        "disk_free_bytes": snapshot.disk_free_bytes,
        "network_rx_bytes_per_second": snapshot.network_rx_bytes_per_second,
        "network_tx_bytes_per_second": snapshot.network_tx_bytes_per_second,
        "process_count": snapshot.process_count,
    }
    for name, value in rate_fields.items():
        if value is not None and float(value) < 0:
            findings.append(f"{name}:negative_value")
    for zone, temp in snapshot.thermal_zone_temperatures_c.items():
        if float(temp) < min_temperature_c or float(temp) > max_temperature_c:
            findings.append(f"thermal_zone:{zone}:temperature_out_of_range")
    for label, rpm in snapshot.fan_rpm_observations.items():
        if float(rpm) < 0:
            findings.append(f"fan_rpm:{label}:negative_value")
    for key, value in snapshot.forbidden_markers.items():
        if key in FORBIDDEN_MARKER_KEYS and bool(value):
            findings.append(f"forbidden_marker:{key}")
    for label in report.pressure_labels:
        if label not in PRESSURE_LABELS:
            findings.append(f"unknown_pressure_label:{label}")
    if not report.metadata_only:
        findings.append("report_not_metadata_only")
    if not report.observe_model_propose_only or not report.no_host_actuation or not report.no_fan_pwm_writes or not report.no_process_kill_restart_install or not report.no_provider_network_prompt_authority:
        findings.append("report_claims_forbidden_authority")
    for candidate in report.proposal_candidates:
        prefix = f"candidate:{candidate.candidate_id or '<missing>'}"
        if not candidate.candidate_id:
            findings.append(prefix + ":missing_id")
        if candidate.kind not in CANDIDATE_KINDS:
            findings.append(prefix + ":unknown_kind")
        required = (
            candidate.proposal_only,
            candidate.does_not_execute,
            candidate.does_not_mutate_host,
            candidate.requires_privilege_broker_for_future_action,
            candidate.requires_control_plane_admission_for_future_action,
            candidate.requires_operator_or_policy_approval_for_future_action,
            candidate.requires_audit_receipt_for_future_action,
            candidate.requires_rollback_receipt_for_future_action,
        )
        if not all(required):
            findings.append(prefix + ":candidate_claims_execution_or_missing_future_gate")
    return HostResourceGovernorValidationResult(ok=not findings, findings=tuple(findings))


def evaluate_host_resource_policy_from_telemetry(
    snapshot: HostResourceTelemetrySnapshot,
    *,
    host_id: str | None = None,
    node_id: str | None = None,
    thermal_pressure_c: float = 85.0,
) -> tuple[Any, tuple[Any, ...]]:
    """Evaluate Phase 3 policy receipts from supplied read-only telemetry.

    The returned decision and receipts are proposal-only metadata. This helper
    does not authorize or fulfill host action.
    """

    from sentientos.host_resource_policy import build_host_resource_proposal_receipts, evaluate_host_resource_policy

    report = evaluate_host_resource_pressure(snapshot, thermal_pressure_c=thermal_pressure_c)
    decision = evaluate_host_resource_policy(report, host_id=host_id, node_id=node_id)
    return decision, build_host_resource_proposal_receipts(decision)
