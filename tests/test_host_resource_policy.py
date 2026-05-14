from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.capability_registry import build_default_capability_registry, update_registry_from_host_resource_policy, validate_capability_registry
from sentientos.host_collectors import collect_fan_pwm_observation, collect_thermal_sensor_observation
from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results, build_host_resource_telemetry_snapshot, evaluate_host_resource_policy_from_telemetry, evaluate_host_resource_pressure
from sentientos.host_resource_policy import (
    build_host_resource_proposal_receipts,
    evaluate_host_resource_policy,
    host_resource_policy_decision_digest,
    host_resource_proposal_receipt_digest,
    summarize_host_resource_policy_decision,
    summarize_host_resource_proposal_receipt,
    validate_host_resource_policy_decision,
    validate_host_resource_proposal_receipt,
)

pytestmark = pytest.mark.no_legacy_skip


def _decision(**kwargs):
    snapshot = build_host_resource_telemetry_snapshot(snapshot_id="snap-policy", observed_at="2026-01-01T00:00:00+00:00", **kwargs)
    report = evaluate_host_resource_pressure(snapshot, thermal_pressure_c=85)
    decision = evaluate_host_resource_policy(report, host_id="host", node_id="node")
    receipts = build_host_resource_proposal_receipts(decision)
    return snapshot, report, decision, receipts


def _kinds(receipts):
    return {receipt.proposal_kind for receipt in receipts}


def test_nominal_pressure_report_produces_nominal_monitor_and_no_executable_receipt() -> None:
    _, _, decision, receipts = _decision(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30)
    assert decision.status == "host_resource_policy_nominal"
    assert decision.proposal_kinds == ()
    assert receipts == ()
    assert validate_host_resource_policy_decision(decision).ok


def test_cpu_pressure_produces_reduce_and_defer_proposal_receipts() -> None:
    _, _, decision, receipts = _decision(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    assert decision.status == "host_resource_policy_proposal_ready"
    assert {"inspect_cpu_pressure_candidate", "reduce_model_load_candidate", "defer_heavy_task_candidate"}.issubset(_kinds(receipts))
    assert all(receipt.does_not_execute and receipt.does_not_mutate_host for receipt in receipts)


def test_memory_gpu_disk_pressure_map_to_inspect_and_future_candidates() -> None:
    _, _, decision, receipts = _decision(cpu_utilization_percent=10, ram_utilization_percent=95, gpu_utilization_percent=95, disk_utilization_percent=95)
    kinds = _kinds(receipts)
    assert "inspect_memory_pressure_candidate" in kinds
    assert "defer_heavy_task_candidate" in kinds
    assert "inspect_gpu_pressure_candidate" in kinds
    assert "inspect_disk_pressure_candidate" in kinds
    assert "future_cleanup_policy_candidate" in kinds
    cleanup = [receipt for receipt in receipts if receipt.proposal_kind == "future_cleanup_policy_candidate"][0]
    assert cleanup.proposal_status == "host_resource_proposal_blocked"
    assert validate_host_resource_policy_decision(decision).ok


def test_thermal_pressure_produces_inspect_and_future_cooling_non_executing_receipts() -> None:
    _, _, decision, receipts = _decision(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, thermal_zone_temperatures_c={"cpu": 90})
    kinds = _kinds(receipts)
    assert {"inspect_thermal_state_candidate", "future_cooling_policy_candidate"}.issubset(kinds)
    cooling = [receipt for receipt in receipts if receipt.proposal_kind == "future_cooling_policy_candidate"][0]
    assert cooling.proposal_status == "host_resource_proposal_blocked"
    assert cooling.does_not_execute is True
    assert cooling.not_authorized_for_fulfillment is True
    assert "future_privilege_broker_required" in cooling.required_future_gates
    assert "fan_pwm_write" in cooling.blocked_actions
    assert "thermal_actuation" in cooling.blocked_actions


def test_fan_rpm_and_pwm_observation_alone_remains_diagnostics_not_control() -> None:
    _, _, decision, receipts = _decision(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, fan_rpm_observations={"fan0": 1200}, model_runtime_pressure_labels=("pwm_signal_observed_not_control_authority",))
    assert decision.status == "host_resource_policy_monitor"
    assert decision.proposal_kinds == ()
    assert receipts == ()
    assert "pwm_presence_is_not_control_authority" in decision.warning_codes
    assert decision.fan_pwm_write_performed is False


def test_service_degraded_creates_inspect_service_health_not_restart() -> None:
    _, _, decision, receipts = _decision(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, service_health_labels=("daemon_degraded",))
    assert "inspect_service_health_candidate" in _kinds(receipts)
    assert "service_restart" in decision.blocked_proposal_kinds
    assert all("service_restart" in receipt.blocked_actions for receipt in receipts)


def test_incomplete_telemetry_produces_diagnostics_operator_review_only() -> None:
    _, _, decision, receipts = _decision(unavailable_sensor_labels=("cpu",))
    assert decision.status == "host_resource_policy_incomplete"
    assert _kinds(receipts) == {"request_operator_review_candidate"}
    assert receipts[0].proposal_status == "host_resource_proposal_incomplete"
    assert receipts[0].proposal_scope in {"diagnostics_only", "operator_review_queue"}


def test_unknown_and_contradictory_reports_block_proposal_readiness() -> None:
    snapshot = build_host_resource_telemetry_snapshot(snapshot_id="snap", cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30)
    report = evaluate_host_resource_pressure(snapshot)
    unknown_decision = evaluate_host_resource_policy(replace(report, pressure_labels=("unknown",)))
    assert unknown_decision.status == "host_resource_policy_blocked"
    contradicted = evaluate_host_resource_policy(replace(report, pressure_labels=("nominal", "cpu_pressure")))
    assert contradicted.status == "host_resource_policy_contradicted"


def test_receipts_and_decision_digests_are_deterministic_and_change_on_metadata() -> None:
    _, _, first_decision, first_receipts = _decision(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    _, _, second_decision, second_receipts = _decision(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    assert host_resource_policy_decision_digest(first_decision) == host_resource_policy_decision_digest(second_decision)
    assert [receipt.digest for receipt in first_receipts] == [receipt.digest for receipt in second_receipts]
    changed = replace(first_decision, reason_codes=first_decision.reason_codes + ("extra_reason",))
    assert host_resource_policy_decision_digest(changed) != host_resource_policy_decision_digest(first_decision)
    changed_receipt = replace(first_receipts[0], warning_codes=first_receipts[0].warning_codes + ("extra_warning",), digest="")
    assert host_resource_proposal_receipt_digest(changed_receipt) != first_receipts[0].digest


def test_summaries_are_metadata_only_and_do_not_include_raw_sensitive_evidence() -> None:
    _, _, decision, receipts = _decision(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    decision_summary = summarize_host_resource_policy_decision(decision)
    receipt_summary = summarize_host_resource_proposal_receipt(receipts[0])
    assert set(decision_summary) == {"decision_id", "report_id", "report_digest", "status", "pressure_labels", "selected_policy_rule_count", "proposal_kind_count", "blocked_proposal_kind_count", "warning_count", "risk_count", "metadata_only", "proposal_only", "host_mutation_performed", "fan_pwm_write_performed", "thermal_actuation_performed", "network_performed", "digest"}
    assert set(receipt_summary) == {"receipt_id", "decision_id", "report_id", "proposal_kind", "proposal_status", "proposal_scope", "pressure_labels", "future_gate_count", "blocked_action_count", "warning_count", "risk_count", "proposal_only", "does_not_execute", "does_not_mutate_host", "not_authorized_for_fulfillment", "digest"}


@pytest.mark.parametrize(
    "field",
    [
        "host_mutation_performed",
        "fan_pwm_write_performed",
        "thermal_actuation_performed",
        "process_kill_performed",
        "service_restart_performed",
        "package_install_performed",
        "driver_install_performed",
        "provider_invocation_performed",
        "network_performed",
        "prompt_assembly_performed",
    ],
)
def test_validation_rejects_policy_decision_forbidden_flags(field: str) -> None:
    _, _, decision, _ = _decision(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    bad = replace(decision, **{field: True})
    result = validate_host_resource_policy_decision(bad)
    assert not result.ok
    assert f"forbidden_decision_flag:{field}" in result.findings


@pytest.mark.parametrize(
    "field",
    [
        "proposal_only",
        "does_not_execute",
        "does_not_mutate_host",
        "not_authorized_for_fulfillment",
        "requires_privilege_broker_for_future_action",
        "requires_control_plane_admission_for_future_action",
        "requires_operator_or_policy_approval_for_future_action",
        "requires_audit_receipt_for_future_action",
        "requires_rollback_receipt_for_future_action",
    ],
)
def test_validation_rejects_proposal_receipt_claiming_execution_or_authorization(field: str) -> None:
    _, _, _, receipts = _decision(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    bad = replace(receipts[0], **{field: False})
    result = validate_host_resource_proposal_receipt(bad)
    assert not result.ok
    assert any("receipt_claims_execution_or_authority" in finding for finding in result.findings)


def test_fake_collectors_to_policy_receipts_integration_thermal_pwm_proposal_only() -> None:
    tree = {"/thermal": ("thermal_zone0",), "/hwmon": ("hwmon0",), "/hwmon/hwmon0": ("fan1_input", "pwm1")}
    files = {"/thermal/thermal_zone0/temp": "90000\n", "/thermal/thermal_zone0/type": "cpu\n", "/hwmon/hwmon0/fan1_input": "1400\n", "/hwmon/hwmon0/pwm1": "128\n"}
    results = (
        collect_thermal_sensor_observation(thermal_path="/thermal", hwmon_path="/empty", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at="2026-01-01T00:00:00+00:00"),
        collect_fan_pwm_observation(hwmon_path="/hwmon", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at="2026-01-01T00:00:00+00:00"),
    )
    snapshot = build_host_resource_telemetry_from_collector_results(results, snapshot_id="collector-snap")
    decision, receipts = evaluate_host_resource_policy_from_telemetry(snapshot, host_id="host", node_id="node", thermal_pressure_c=85)
    assert "future_cooling_policy_candidate" in _kinds(receipts)
    assert "pwm_presence_is_not_control_authority" in decision.warning_codes
    assert all(validate_host_resource_proposal_receipt(receipt).ok for receipt in receipts)
    assert all(receipt.does_not_execute and receipt.does_not_mutate_host for receipt in receipts)


def test_capability_registry_reflects_policy_proposal_only_and_deferred_fulfillment() -> None:
    _, _, decision, receipts = _decision(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    registry = update_registry_from_host_resource_policy(build_default_capability_registry(), decision, receipts)
    records = registry.by_id()
    assert records["host_resource_policy"].status == "implemented"
    assert records["host_resource_policy"].authority_level == "proposal_only"
    assert records["host_resource_proposal_receipts"].authority_level == "proposal_only"
    assert records["direct_fan_pwm_thermal_control"].status == "blocked"
    assert records["privilege_broker"].status == "deferred"
    assert records["actuation_fulfillment"].status == "deferred"
    assert all(record.host_actuation_performed is False for record in records.values() if "host_resource" in record.capability_id or record.capability_id in {"direct_fan_pwm_thermal_control", "privilege_broker", "actuation_fulfillment"})
    assert validate_capability_registry(registry).ok
