from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.host_inventory import (
    HostInventoryDevice,
    HostInventoryManifest,
    HostInventorySensor,
    build_host_inventory_manifest,
    host_inventory_digest,
    summarize_host_inventory_manifest,
    validate_host_inventory_manifest,
)

pytestmark = pytest.mark.no_legacy_skip


def _clean_manifest() -> HostInventoryManifest:
    return build_host_inventory_manifest(
        manifest_id="manifest-1",
        node_id="node-1",
        host_id="host-1",
        os_family="linux",
        os_release="6.x",
        architecture="x86_64",
        cpu_summary={"model": "test cpu", "cores": 8},
        gpu_summary={"devices": ["test gpu"]},
        ram_summary={"total_bytes": 16_000_000_000, "used_percent": 50},
        disk_summary={"total_bytes": 100_000_000_000, "free_bytes": 50_000_000_000, "used_percent": 50},
        network_interface_summary={"interfaces": ["lo", "eth0"]},
        battery_power_summary={"battery_percent": 80, "charging": True},
        thermal_zone_summary={"zones": ["cpu"], "max_c": 55},
        fan_pwm_controller_summary={"status": "rpm_observable", "telemetry_only": True, "control_available": False},
        audio_device_summary={"devices": ["default"]},
        camera_display_input_summary={"camera_count": 1, "display_count": 1, "input_count": 2},
        service_manager_summary={"kind": "systemd", "read_only": True},
        privilege_model_summary={"user": "non-root", "read_only": True},
        devices=(
            {"device_id": "cpu0", "kind": "cpu", "label": "CPU", "summary": {"cores": 8}, "status": "observed"},
            {"device_id": "gpu0", "kind": "gpu", "label": "GPU", "summary": {"memory_bytes": 8_000_000_000}, "status": "observed"},
        ),
        sensors=(
            {"sensor_id": "temp0", "kind": "temperature", "label": "CPU temp", "observed_value": 55, "unit": "C", "status": "observed"},
            {"sensor_id": "fan0", "kind": "fan_rpm", "label": "Fan RPM", "observed_value": 1200, "unit": "rpm", "status": "observed"},
        ),
        observed_at="2026-01-01T00:00:00+00:00",
        source_labels=("test",),
    )


def test_clean_manifest_with_supplied_metadata_validates() -> None:
    manifest = _clean_manifest()
    assert validate_host_inventory_manifest(manifest).ok
    summary = summarize_host_inventory_manifest(manifest)
    assert summary["metadata_only"] is True
    assert summary["no_host_actuation"] is True
    assert summary["device_count"] == 2
    assert summary["sensor_count"] == 2


def test_missing_unknown_fan_pwm_is_unavailable_deferred_not_control() -> None:
    manifest = build_host_inventory_manifest(manifest_id="manifest-2", node_id="node-1", os_family="linux", observed_at="t")
    assert validate_host_inventory_manifest(manifest).ok
    assert manifest.fan_pwm_controller_summary["status"] == "unknown_unavailable_deferred"
    assert manifest.fan_pwm_controller_summary["control_available"] is False
    assert "fan_pwm_control_deferred" in manifest.unsupported_deferred_labels


def test_negative_ram_disk_and_percent_values_fail_closed() -> None:
    manifest = build_host_inventory_manifest(
        manifest_id="bad",
        node_id="node",
        os_family="linux",
        ram_summary={"total_bytes": -1, "used_percent": 101},
        disk_summary={"free_bytes": -2},
        observed_at="t",
    )
    result = validate_host_inventory_manifest(manifest)
    assert not result.ok
    assert any("negative_value" in finding for finding in result.findings)
    assert any("percent_out_of_range" in finding for finding in result.findings)


def test_malformed_device_and_sensor_entries_fail_closed() -> None:
    manifest = build_host_inventory_manifest(
        manifest_id="bad",
        node_id="node",
        os_family="linux",
        devices=({"device_id": "", "kind": "warp", "label": ""},),
        sensors=({"sensor_id": "", "kind": "warp", "label": ""},),
        observed_at="t",
    )
    result = validate_host_inventory_manifest(manifest)
    assert not result.ok
    assert any("malformed_device" in finding for finding in result.findings)
    assert any("unknown_sensor_kind" in finding for finding in result.findings)


def test_digest_is_deterministic_and_changes_on_metadata() -> None:
    first = _clean_manifest()
    second = _clean_manifest()
    assert host_inventory_digest(first) == host_inventory_digest(second)
    changed = replace(first, architecture="arm64")
    assert host_inventory_digest(changed) != host_inventory_digest(first)


def test_no_host_actuation_flags_allowed() -> None:
    manifest = replace(_clean_manifest(), no_host_actuation=False)
    result = validate_host_inventory_manifest(manifest)
    assert not result.ok
    assert "host_actuation_claimed" in result.findings


def test_fan_pwm_control_claim_requires_backend_metadata_and_privileged_devices_rejected() -> None:
    manifest = replace(
        _clean_manifest(),
        fan_pwm_controller_summary={"status": "claimed", "control_available": True},
        devices=(HostInventoryDevice(device_id="fanctl", kind="fan_pwm", label="Fan controller", control_available=True),),
        sensors=(HostInventorySensor(sensor_id="fan", kind="fan_rpm", label="Fan", control_available=True),),
    )
    result = validate_host_inventory_manifest(manifest)
    assert not result.ok
    assert "fan_pwm_control_claimed_without_backend_metadata" in result.findings
    assert any("privileged_action_claimed" in finding for finding in result.findings)
    assert any("control_claimed" in finding for finding in result.findings)


def test_build_inventory_from_collector_results_maps_read_only_discovery() -> None:
    from sentientos.host_collectors import (
        collect_disk_observation,
        collect_fan_pwm_observation,
        collect_network_interface_observation,
        collect_platform_observation,
        collect_thermal_sensor_observation,
    )
    from sentientos.host_inventory import build_host_inventory_from_collector_results

    tree = {"/thermal": ("thermal_zone0",), "/hwmon": ("hwmon0",), "/hwmon/hwmon0": ("fan1_input", "pwm1")}
    files = {
        "/thermal/thermal_zone0/temp": "86000\n",
        "/thermal/thermal_zone0/type": "cpu\n",
        "/hwmon/hwmon0/fan1_input": "1300\n",
        "/hwmon/hwmon0/pwm1": "200\n",
    }
    results = (
        collect_platform_observation(observed_at="2026-01-01T00:00:00+00:00"),
        collect_disk_observation(disk_provider=lambda path: type("D", (), {"total": 100, "used": 50, "free": 50})(), observed_at="2026-01-01T00:00:00+00:00"),
        collect_network_interface_observation(directory_lister=lambda path: ("lo",), text_reader=lambda path: "00\n", observed_at="2026-01-01T00:00:00+00:00"),
        collect_thermal_sensor_observation(thermal_path="/thermal", hwmon_path="/empty", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at="2026-01-01T00:00:00+00:00"),
        collect_fan_pwm_observation(hwmon_path="/hwmon", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at="2026-01-01T00:00:00+00:00"),
    )
    manifest = build_host_inventory_from_collector_results(results, manifest_id="m", node_id="n")
    assert validate_host_inventory_manifest(manifest).ok
    assert manifest.disk_summary["free_bytes"] == 50
    assert manifest.thermal_zone_summary["zones"][0]["temperature_c"] == 86
    assert manifest.fan_pwm_controller_summary["pwm_signal_observed"] is True
    assert manifest.fan_pwm_controller_summary["control_available"] is False
    assert manifest.fan_pwm_controller_summary["control_deferred"] is True
    assert manifest.fan_pwm_controller_summary["requires_future_allowlist"] is True
    assert manifest.fan_pwm_controller_summary["requires_privilege_broker"] is True
    assert "pwm_presence_not_control_authority" in manifest.unsupported_deferred_labels
    assert host_inventory_digest(manifest) == host_inventory_digest(build_host_inventory_from_collector_results(results, manifest_id="m", node_id="n"))


def test_collector_unavailable_inventory_adds_warning_deferred_labels_and_rejects_authority_claims() -> None:
    from sentientos.host_collectors import HostCollectorResult
    from sentientos.host_inventory import build_host_inventory_from_collector_results

    result = HostCollectorResult(
        collector_id="fan_pwm",
        status="unavailable",
        observed_at="2026-01-01T00:00:00+00:00",
        source="test",
        warnings=("sensor_unavailable:fan_pwm",),
    )
    manifest = build_host_inventory_from_collector_results((result,), manifest_id="m", node_id="n")
    assert validate_host_inventory_manifest(manifest).ok
    assert "fan_pwm_unavailable" in manifest.unsupported_deferred_labels
    assert "sensor_unavailable:fan_pwm" in manifest.warning_risk_codes
    bad = replace(manifest, fan_pwm_controller_summary={**manifest.fan_pwm_controller_summary, "control_available": True})
    assert not validate_host_inventory_manifest(bad).ok
