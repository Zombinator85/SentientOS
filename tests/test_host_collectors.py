from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from sentientos.host_collectors import (
    HostCollectorResult,
    collect_accelerator_observation,
    collect_cpu_feature_observation,
    collect_cpu_observation,
    collect_disk_observation,
    collect_fan_pwm_observation,
    collect_memory_observation,
    collect_network_interface_observation,
    collect_platform_observation,
    collect_thermal_sensor_observation,
    validate_host_collector_result,
)

pytestmark = pytest.mark.no_legacy_skip

STAMP = "2026-01-01T00:00:00+00:00"


def test_platform_collector_is_telemetry_only_and_non_mutating() -> None:
    result = collect_platform_observation(observed_at=STAMP)
    assert result.telemetry_only is True
    assert result.host_mutation_performed is False
    assert result.network_performed is False
    assert result.privileged_action_performed is False
    assert validate_host_collector_result(result).ok


def test_disk_collector_uses_supplied_disk_provider() -> None:
    result = collect_disk_observation(path="/fake", disk_provider=lambda path: SimpleNamespace(total=100, used=25, free=75), observed_at=STAMP)
    assert result.status == "available"
    assert result.values["used_percent"] == 25
    assert result.values["path_label"] == "/fake"
    assert validate_host_collector_result(result).ok


def test_memory_collector_degrades_when_details_missing() -> None:
    result = collect_memory_observation(memory_provider=lambda: None, observed_at=STAMP)
    assert result.status in {"partial", "unavailable"}
    assert result.telemetry_only is True
    assert validate_host_collector_result(result).ok


def test_cpu_collector_reports_partial_when_utilization_unavailable() -> None:
    result = collect_cpu_observation(observed_at=STAMP)
    assert result.status in {"partial", "unavailable"}
    assert result.values.get("utilization_percent") is None
    assert any(finding.code == "cpu_utilization_unavailable" for finding in result.findings)


def test_linux_cpu_features_are_explicit_tri_state_facts() -> None:
    result = collect_cpu_feature_observation(
        system="Linux", architecture="x86_64",
        text_reader=lambda path: "processor: 0\nflags: sse avx avx2 avx512f\n",
        observed_at=STAMP,
    )
    assert result.status == "available"
    assert result.values == {"architecture": "x86_64", "avx": True, "avx2": True, "avx512": True}

    absent = collect_cpu_feature_observation(
        system="Linux", architecture="amd64", text_reader=lambda path: "flags: sse sse2\n", observed_at=STAMP,
    )
    assert (absent.values["avx"], absent.values["avx2"], absent.values["avx512"]) == (False, False, False)


def test_cpu_feature_unavailable_and_non_x86_do_not_fabricate_false() -> None:
    unavailable = collect_cpu_feature_observation(
        system="Linux", architecture="x86_64", text_reader=lambda path: (_ for _ in ()).throw(OSError()), observed_at=STAMP,
    )
    non_x86 = collect_cpu_feature_observation(system="Darwin", architecture="arm64", observed_at=STAMP)
    assert unavailable.status == "unavailable" and "avx" not in unavailable.values
    assert non_x86.status == "unavailable" and "avx" not in non_x86.values
    assert any(finding.code == "x86_features_not_applicable" for finding in non_x86.findings)


def test_windows_cpu_feature_api_is_injectable_and_api_absence_is_unknown() -> None:
    answers = {18: True, 40: False, 41: True}
    observed = collect_cpu_feature_observation(
        system="Windows", architecture="AMD64", windows_feature_provider=answers.__getitem__, observed_at=STAMP,
    )
    unavailable = collect_cpu_feature_observation(
        system="Windows", architecture="AMD64",
        windows_feature_provider=lambda feature: (_ for _ in ()).throw(OSError()), observed_at=STAMP,
    )
    assert (observed.values["avx"], observed.values["avx2"], observed.values["avx512"]) == (True, False, True)
    assert unavailable.status == "unavailable" and "avx" not in unavailable.values


def test_linux_accelerator_observation_preserves_explicit_identity_and_vram() -> None:
    tree = {"/drm": ("card0", "renderD128", "version")}
    files = {"/drm/card0/device/vendor": "0x10de\n", "/drm/card0/device/device": "0x2684\n",
             "/drm/card0/device/mem_info_vram_total": "8589934592\n"}
    result = collect_accelerator_observation(
        system="Linux", drm_path="/drm", directory_lister=lambda path: tree.get(path, ()),
        text_reader=lambda path: files[path], observed_at=STAMP,
    )
    assert result.values["observed"] is True
    assert result.values["vendor"] == "nvidia" and result.values["family"] == "0x2684"
    assert result.values["vram_bytes"] == 8589934592
    assert "backend_family" not in result.values


def test_accelerator_negative_evidence_and_multiple_device_ambiguity() -> None:
    absent = collect_accelerator_observation(
        system="Linux", drm_path="/drm", directory_lister=lambda path: (), text_reader=lambda path: "", observed_at=STAMP,
    )
    unavailable = collect_accelerator_observation(system="Darwin", observed_at=STAMP)
    failed = collect_accelerator_observation(
        system="Linux", drm_path="/drm", directory_lister=lambda path: (_ for _ in ()).throw(OSError()), observed_at=STAMP,
    )
    tree = {"/drm": ("card1", "card0")}
    files = {
        "/drm/card0/device/vendor": "0x10de", "/drm/card0/device/device": "0x1", "/drm/card0/device/mem_info_vram_total": "1",
        "/drm/card1/device/vendor": "0x1002", "/drm/card1/device/device": "0x2", "/drm/card1/device/mem_info_vram_total": "2",
    }
    multiple = collect_accelerator_observation(
        system="Linux", drm_path="/drm", directory_lister=lambda path: tree.get(path, ()), text_reader=lambda path: files[path], observed_at=STAMP,
    )
    assert absent.values["observed"] is False and absent.values["enumeration_complete"] is True
    assert unavailable.status == "unavailable" and "observed" not in unavailable.values
    assert failed.status == "unavailable" and "observed" not in failed.values
    assert [device["vendor"] for device in multiple.values["devices"]] == ["nvidia", "amd"]
    assert not ({"vendor", "family", "vram_bytes"} & multiple.values.keys())


def test_network_collector_reads_interfaces_without_connectivity_check() -> None:
    def lister(path: str) -> tuple[str, ...]:
        assert path == "/sys/class/net"
        return ("lo", "eth0")

    def reader(path: str) -> str:
        return "00:00:00:00:00:00\n"

    result = collect_network_interface_observation(directory_lister=lister, text_reader=reader, observed_at=STAMP)
    assert result.status == "available"
    assert result.values["connectivity_checked"] is False
    assert result.network_performed is False
    assert [item["name"] for item in result.values["interfaces"]] == ["eth0", "lo"]


def test_thermal_collector_reads_injected_fake_sysfs_and_malformed_values() -> None:
    tree = {
        "/thermal": ("thermal_zone0", "thermal_zone1"),
        "/hwmon": ("hwmon0",),
        "/hwmon/hwmon0": ("temp1_input", "temp2_input"),
    }
    files = {
        "/thermal/thermal_zone0/temp": "42000\n",
        "/thermal/thermal_zone0/type": "x86_pkg_temp\n",
        "/thermal/thermal_zone1/temp": "not-a-number\n",
        "/thermal/thermal_zone1/type": "bad\n",
        "/hwmon/hwmon0/temp1_input": "44000\n",
        "/hwmon/hwmon0/temp2_input": "bad\n",
    }
    result = collect_thermal_sensor_observation(
        thermal_path="/thermal",
        hwmon_path="/hwmon",
        directory_lister=lambda path: tree.get(path, ()),
        text_reader=lambda path: files[path],
        observed_at=STAMP,
    )
    assert result.status == "partial"
    assert [zone["temperature_c"] for zone in result.values["zones"]] == [42.0, 44.0]
    assert any(finding.code == "malformed_thermal_value" for finding in result.findings)
    assert result.values["control_available"] is False


def test_fan_pwm_collector_treats_pwm_presence_as_telemetry_not_control() -> None:
    tree = {"/hwmon": ("hwmon0",), "/hwmon/hwmon0": ("fan1_input", "fan2_input", "pwm1")}
    files = {"/hwmon/hwmon0/fan1_input": "1200\n", "/hwmon/hwmon0/fan2_input": "bad\n", "/hwmon/hwmon0/pwm1": "255\n"}
    result = collect_fan_pwm_observation(
        hwmon_path="/hwmon",
        directory_lister=lambda path: tree.get(path, ()),
        text_reader=lambda path: files[path],
        observed_at=STAMP,
    )
    assert result.status == "partial"
    assert result.values["pwm_signal_observed"] is True
    assert result.values["control_available"] is False
    assert result.values["control_deferred"] is True
    assert result.values["requires_future_allowlist"] is True
    assert result.values["requires_privilege_broker"] is True
    assert result.values["fans"][0]["rpm"] == 1200
    assert any(finding.code == "malformed_fan_rpm_value" for finding in result.findings)
    assert validate_host_collector_result(result).ok


@pytest.mark.parametrize(
    ("field", "finding"),
    [
        ("host_mutation_performed", "host_mutation_performed"),
        ("network_performed", "network_performed"),
        ("privileged_action_performed", "privileged_action_performed"),
    ],
)
def test_validation_rejects_forbidden_action_flags(field: str, finding: str) -> None:
    result = HostCollectorResult(collector_id="bad", status="available", observed_at=STAMP, source="test")
    bad = replace(result, **{field: True})
    validation = validate_host_collector_result(bad)
    assert not validation.ok
    assert finding in validation.findings


@pytest.mark.parametrize(
    "marker",
    [
        "fan_pwm_write_marker",
        "thermal_write_marker",
        "process_kill_marker",
        "service_restart_marker",
        "package_install_marker",
        "driver_install_marker",
    ],
)
def test_validation_rejects_forbidden_markers(marker: str) -> None:
    result = HostCollectorResult(collector_id="bad", status="available", observed_at=STAMP, source="test", forbidden_markers={marker: True})
    validation = validate_host_collector_result(result)
    assert not validation.ok
    assert f"forbidden_marker:{marker}" in validation.findings
