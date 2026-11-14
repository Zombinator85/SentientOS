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


def test_vram_pressure_has_a_separate_lower_threshold_than_gpu_compute() -> None:
    snapshot = build_host_resource_telemetry_snapshot(
        snapshot_id="snap-vram-pressure", observed_at="t",
        cpu_utilization_percent=10, ram_utilization_percent=30,
        disk_utilization_percent=20, gpu_utilization_percent=15,
        vram_utilization_percent=86)
    report = evaluate_host_resource_pressure(snapshot)

    assert "gpu_pressure" in report.pressure_labels
    assert validate_host_resource_pressure_report(report, snapshot).ok

    below_threshold = replace(snapshot, snapshot_id="snap-vram-below",
        vram_utilization_percent=84)
    below_report = evaluate_host_resource_pressure(below_threshold)
    assert "gpu_pressure" not in below_report.pressure_labels
    assert validate_host_resource_pressure_report(below_report, below_threshold).ok


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


def test_build_resource_telemetry_from_collectors_classifies_thermal_and_fan_telemetry_only() -> None:
    from sentientos.host_collectors import collect_fan_pwm_observation, collect_thermal_sensor_observation
    from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results

    tree = {"/thermal": ("thermal_zone0",), "/hwmon": ("hwmon0",), "/hwmon/hwmon0": ("fan1_input", "pwm1")}
    files = {"/thermal/thermal_zone0/temp": "90000\n", "/thermal/thermal_zone0/type": "cpu\n", "/hwmon/hwmon0/fan1_input": "1400\n", "/hwmon/hwmon0/pwm1": "128\n"}
    results = (
        collect_thermal_sensor_observation(thermal_path="/thermal", hwmon_path="/empty", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at="2026-01-01T00:00:00+00:00"),
        collect_fan_pwm_observation(hwmon_path="/hwmon", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at="2026-01-01T00:00:00+00:00"),
    )
    snapshot = build_host_resource_telemetry_from_collector_results(results, snapshot_id="s")
    report = evaluate_host_resource_pressure(snapshot, thermal_pressure_c=85)
    assert snapshot.thermal_zone_temperatures_c["thermal_zone0"] == 90
    assert snapshot.fan_rpm_observations["hwmon0/fan1_input"] == 1400
    assert "pwm_signal_observed_not_control_authority" in snapshot.model_runtime_pressure_labels
    assert "thermal_pressure" in report.pressure_labels
    assert "fan_signal_present" in report.pressure_labels
    assert all(candidate.does_not_mutate_host for candidate in report.proposal_candidates)
    assert validate_host_resource_pressure_report(report, snapshot).ok


def test_cpu_and_memory_collector_samples_reach_pressure_evaluation() -> None:
    from sentientos.host_collectors import collect_cpu_observation, collect_memory_observation
    from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results

    results = (
        collect_cpu_observation(cpu_utilization_provider=lambda: 93.0, observed_at="2026-01-01T00:00:00+00:00"),
        collect_memory_observation(
            memory_provider=lambda: {"total_bytes": 1000, "available_bytes": 80, "used_percent": 92.0},
            observed_at="2026-01-01T00:00:00+00:00",
        ),
    )
    snapshot = build_host_resource_telemetry_from_collector_results(results, snapshot_id="cpu-ram")
    report = evaluate_host_resource_pressure(snapshot)

    assert snapshot.cpu_utilization_percent == 93.0
    assert snapshot.ram_utilization_percent == 92.0
    assert set(report.pressure_labels) == {"cpu_pressure", "memory_pressure"}
    assert all(candidate.does_not_mutate_host for candidate in report.proposal_candidates)


def test_nvml_device_wide_samples_reach_pressure_using_worst_device() -> None:
    from sentientos.host_collectors import HostCollectorResult
    from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results

    gpu = HostCollectorResult(
        collector_id="nvidia_gpu",
        status="available",
        observed_at="2026-11-02T00:00:00+00:00",
        source="test:NVML",
        values={
            "device_count": 2,
            "sample_scope": "device_wide",
            "per_process_attribution_available": False,
            "devices": [
                {"index": 0, "gpu_utilization_percent": 18.0, "vram_utilization_percent": 25.0},
                {"index": 1, "gpu_utilization_percent": 93.0, "vram_utilization_percent": 96.0},
            ],
        },
    )

    snapshot = build_host_resource_telemetry_from_collector_results((gpu,), snapshot_id="nvml-multi")
    report = evaluate_host_resource_pressure(snapshot)

    assert snapshot.gpu_utilization_percent == 93.0
    assert snapshot.vram_utilization_percent == 96.0
    assert "gpu_pressure" in report.pressure_labels
    assert validate_host_resource_pressure_report(report, snapshot).ok


def test_nvml_gpu_temperature_reaches_thermal_pressure_without_host_thermal_zones() -> None:
    from sentientos.host_collectors import HostCollectorResult
    from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results

    gpu = HostCollectorResult(
        collector_id="nvidia_gpu",
        status="available",
        observed_at="2026-11-02T00:00:00+00:00",
        source="test:NVML",
        values={
            "device_count": 1,
            "sample_scope": "device_wide",
            "per_process_attribution_available": False,
            "devices": [{
                "index": 0,
                "gpu_utilization_percent": 18.0,
                "vram_utilization_percent": 25.0,
                "temperature_c": 90.0,
            }],
        },
    )
    thermal = HostCollectorResult(
        collector_id="thermal_sensors",
        status="unavailable",
        observed_at="2026-11-02T00:00:00+00:00",
        source="test:unavailable",
        warnings=("sensor_unavailable:thermal",),
    )

    snapshot = build_host_resource_telemetry_from_collector_results(
        (gpu, thermal), snapshot_id="nvml-gpu-thermal")
    report = evaluate_host_resource_pressure(snapshot)

    assert snapshot.thermal_zone_temperatures_c == {"nvidia_gpu_0": 90.0}
    assert "thermal_pressure" in report.pressure_labels
    assert "sensor_unavailable" in report.pressure_labels
    assert validate_host_resource_pressure_report(report, snapshot).ok


def test_malformed_nvml_gpu_temperature_is_unavailable_not_thermal_pressure() -> None:
    from sentientos.host_collectors import HostCollectorResult
    from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results

    gpu = HostCollectorResult(
        collector_id="nvidia_gpu",
        status="available",
        observed_at="2026-11-02T00:00:00+00:00",
        source="test:NVML",
        values={"device_count": 1, "devices": [{
            "index": 0, "temperature_c": 151.0,
        }]},
    )

    snapshot = build_host_resource_telemetry_from_collector_results(
        (gpu,), snapshot_id="nvml-gpu-temperature-invalid")
    report = evaluate_host_resource_pressure(snapshot)

    assert snapshot.thermal_zone_temperatures_c == {}
    assert "nvidia_gpu_temperature_c_malformed:0" in snapshot.unavailable_sensor_labels
    assert "thermal_pressure" not in report.pressure_labels


def test_nvml_malformed_device_sample_is_unavailable_not_idle() -> None:
    from sentientos.host_collectors import HostCollectorResult
    from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results

    gpu = HostCollectorResult(
        collector_id="nvidia_gpu",
        status="available",
        observed_at="2026-11-02T00:00:00+00:00",
        source="test:NVML",
        values={"device_count": 1, "devices": [{"gpu_utilization_percent": 101.0}]},
    )
    snapshot = build_host_resource_telemetry_from_collector_results((gpu,), snapshot_id="nvml-invalid")

    assert snapshot.gpu_utilization_percent is None
    assert "nvidia_gpu_gpu_utilization_percent_malformed" in snapshot.unavailable_sensor_labels


def test_incomplete_collector_data_yields_unavailable_findings_and_digest_is_deterministic() -> None:
    from sentientos.host_collectors import HostCollectorResult
    from sentientos.host_resource_governor import build_host_resource_telemetry_from_collector_results

    result = HostCollectorResult(collector_id="memory", status="unavailable", observed_at="2026-01-01T00:00:00+00:00", source="test", warnings=("sensor_unavailable:memory",))
    snapshot = build_host_resource_telemetry_from_collector_results((result,), snapshot_id="s")
    report = evaluate_host_resource_pressure(snapshot)
    assert "telemetry_incomplete" in report.pressure_labels
    assert "sensor_unavailable" in report.pressure_labels
    assert any("sensor_unavailable" in finding for finding in report.findings)
    assert host_resource_report_digest(report) == host_resource_report_digest(evaluate_host_resource_pressure(build_host_resource_telemetry_from_collector_results((result,), snapshot_id="s")))
    bad_snapshot = replace(snapshot, forbidden_markers={"actuation_claimed": True})
    bad_report = evaluate_host_resource_pressure(bad_snapshot)
    assert not validate_host_resource_pressure_report(bad_report, bad_snapshot).ok
