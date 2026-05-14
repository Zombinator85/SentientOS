from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.host_resource_governor import (
    HostResourceProposalCandidate,
    build_host_resource_telemetry_snapshot,
    evaluate_host_resource_pressure,
    host_resource_report_digest,
    summarize_host_resource_pressure,
    validate_host_resource_pressure_report,
)

pytestmark = pytest.mark.no_legacy_skip


def _report(**kwargs):
    snapshot = build_host_resource_telemetry_snapshot(snapshot_id="snap-1", observed_at="t", **kwargs)
    report = evaluate_host_resource_pressure(snapshot)
    return snapshot, report


def test_nominal_telemetry_produces_nominal_report() -> None:
    snapshot, report = _report(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30)
    assert report.pressure_labels == ("nominal",)
    assert not report.proposal_candidates
    assert validate_host_resource_pressure_report(report, snapshot).ok


def test_pressure_classification_for_cpu_memory_gpu_disk_and_thermal() -> None:
    snapshot, report = _report(
        cpu_utilization_percent=95,
        ram_utilization_percent=91,
        gpu_utilization_percent=92,
        disk_utilization_percent=93,
        thermal_zone_temperatures_c={"cpu": 90},
    )
    assert {"cpu_pressure", "memory_pressure", "gpu_pressure", "disk_pressure", "thermal_pressure"}.issubset(set(report.pressure_labels))
    assert validate_host_resource_pressure_report(report, snapshot).ok


def test_fan_rpm_observation_is_telemetry_only() -> None:
    snapshot, report = _report(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, fan_rpm_observations={"fan0": 1200})
    assert "fan_signal_present" in report.pressure_labels
    assert "fan_rpm_observation_is_telemetry_only" in report.findings
    assert report.no_fan_pwm_writes is True
    assert validate_host_resource_pressure_report(report, snapshot).ok


def test_incomplete_telemetry_and_unavailable_sensors_are_findings() -> None:
    snapshot, report = _report(unavailable_sensor_labels=("gpu", "fan_pwm"))
    assert "telemetry_incomplete" in report.pressure_labels
    assert "sensor_unavailable" in report.pressure_labels
    assert any("sensor_unavailable" in finding for finding in report.findings)


def test_proposal_candidates_are_proposal_only_and_non_mutating() -> None:
    snapshot, report = _report(cpu_utilization_percent=99, ram_utilization_percent=95, disk_utilization_percent=95)
    assert report.proposal_candidates
    for candidate in report.proposal_candidates:
        assert candidate.proposal_only is True
        assert candidate.does_not_execute is True
        assert candidate.does_not_mutate_host is True
        assert candidate.requires_privilege_broker_for_future_action is True
        assert candidate.requires_control_plane_admission_for_future_action is True
        assert candidate.requires_operator_or_policy_approval_for_future_action is True
        assert candidate.requires_audit_receipt_for_future_action is True
        assert candidate.requires_rollback_receipt_for_future_action is True
    assert validate_host_resource_pressure_report(report, snapshot).ok


def test_invalid_percentages_fail_closed() -> None:
    snapshot, report = _report(cpu_utilization_percent=101, ram_utilization_percent=-1, disk_utilization_percent=10)
    result = validate_host_resource_pressure_report(report, snapshot)
    assert not result.ok
    assert any("percent_out_of_range" in finding for finding in result.findings)


def test_negative_rates_and_counts_fail_closed() -> None:
    snapshot, report = _report(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, disk_free_bytes=-1, network_rx_bytes_per_second=-1, process_count=-1)
    result = validate_host_resource_pressure_report(report, snapshot)
    assert not result.ok
    assert any("negative_value" in finding for finding in result.findings)


def test_fan_pwm_write_marker_fails_closed() -> None:
    snapshot, report = _report(cpu_utilization_percent=10, ram_utilization_percent=20, disk_utilization_percent=30, forbidden_markers={"fan_pwm_write_marker": True})
    result = validate_host_resource_pressure_report(report, snapshot)
    assert not result.ok
    assert "forbidden_marker:fan_pwm_write_marker" in result.findings


def test_process_kill_restart_install_markers_fail_closed() -> None:
    snapshot, report = _report(
        cpu_utilization_percent=10,
        ram_utilization_percent=20,
        disk_utilization_percent=30,
        forbidden_markers={"process_kill_marker": True, "service_restart_marker": True, "package_install_marker": True},
    )
    result = validate_host_resource_pressure_report(report, snapshot)
    assert not result.ok
    assert "forbidden_marker:process_kill_marker" in result.findings
    assert "forbidden_marker:service_restart_marker" in result.findings
    assert "forbidden_marker:package_install_marker" in result.findings


def test_provider_network_prompt_markers_fail_closed() -> None:
    snapshot, report = _report(
        cpu_utilization_percent=10,
        ram_utilization_percent=20,
        disk_utilization_percent=30,
        forbidden_markers={"provider_invocation_marker": True, "network_egress_marker": True, "prompt_assembly_marker": True},
    )
    result = validate_host_resource_pressure_report(report, snapshot)
    assert not result.ok
    assert "forbidden_marker:provider_invocation_marker" in result.findings
    assert "forbidden_marker:network_egress_marker" in result.findings
    assert "forbidden_marker:prompt_assembly_marker" in result.findings


def test_candidate_execution_or_host_mutation_claim_fails_closed() -> None:
    snapshot, report = _report(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    bad_candidate = replace(report.proposal_candidates[0], does_not_execute=False)
    bad_report = replace(report, proposal_candidates=(bad_candidate,))
    result = validate_host_resource_pressure_report(bad_report, snapshot)
    assert not result.ok
    assert any("candidate_claims_execution" in finding for finding in result.findings)


def test_deterministic_digest_and_metadata_summary() -> None:
    first_snapshot, first_report = _report(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    second_snapshot, second_report = _report(cpu_utilization_percent=95, ram_utilization_percent=20, disk_utilization_percent=30)
    assert host_resource_report_digest(first_report) == host_resource_report_digest(second_report)
    summary = summarize_host_resource_pressure(first_report)
    assert summary["metadata_only"] is True
    assert summary["observe_model_propose_only"] is True
    assert summary["no_host_actuation"] is True
    assert summary["no_fan_pwm_writes"] is True
    assert validate_host_resource_pressure_report(first_report, first_snapshot).ok
