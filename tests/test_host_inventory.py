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
