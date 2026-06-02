"""Read-only host inventory manifest for SentientOS Phase 1.

The manifest is a supplied-observation body map. It does not probe privileged
hardware, mutate host state, invoke providers, assemble prompts, or grant action
authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

KNOWN_OS_FAMILIES = frozenset({"linux", "windows", "darwin", "macos", "freebsd", "openbsd", "netbsd", "unknown"})
DEVICE_KINDS = frozenset({"cpu", "gpu", "ram", "disk", "network", "battery", "power", "thermal", "fan_pwm", "audio", "camera", "display", "input", "service_manager", "privilege_model", "other"})
SENSOR_KINDS = frozenset({"temperature", "fan_rpm", "battery_percent", "power_state", "utilization", "capacity", "presence", "unknown"})
CONTROL_CLAIM_KEYS = frozenset({"control_available", "fan_pwm_control_available", "privileged_action_available", "host_actuation_available", "provider_authority", "network_authority", "prompt_authority"})


@dataclass(frozen=True)
class HostInventoryDevice:
    device_id: str
    kind: str
    label: str
    summary: Mapping[str, Any] = field(default_factory=dict)
    status: str = "unknown"
    source_label: str = "supplied"
    control_available: bool = False
    privileged_action_available: bool = False
    metadata_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostInventorySensor:
    sensor_id: str
    kind: str
    label: str
    status: str = "unknown"
    observed_value: Any | None = None
    unit: str | None = None
    source_label: str = "supplied"
    control_available: bool = False
    metadata_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostInventoryManifest:
    manifest_id: str
    node_id: str
    host_id: str
    os_family: str
    os_release: str = "unknown"
    architecture: str = "unknown"
    cpu_summary: Mapping[str, Any] = field(default_factory=dict)
    gpu_summary: Mapping[str, Any] = field(default_factory=dict)
    ram_summary: Mapping[str, Any] = field(default_factory=dict)
    disk_summary: Mapping[str, Any] = field(default_factory=dict)
    network_interface_summary: Mapping[str, Any] = field(default_factory=dict)
    battery_power_summary: Mapping[str, Any] = field(default_factory=dict)
    thermal_zone_summary: Mapping[str, Any] = field(default_factory=dict)
    fan_pwm_controller_summary: Mapping[str, Any] = field(default_factory=dict)
    audio_device_summary: Mapping[str, Any] = field(default_factory=dict)
    camera_display_input_summary: Mapping[str, Any] = field(default_factory=dict)
    service_manager_summary: Mapping[str, Any] = field(default_factory=dict)
    privilege_model_summary: Mapping[str, Any] = field(default_factory=dict)
    devices: tuple[HostInventoryDevice, ...] = ()
    sensors: tuple[HostInventorySensor, ...] = ()
    observed_at: str = "unknown"
    source_labels: tuple[str, ...] = ()
    unsupported_deferred_labels: tuple[str, ...] = ()
    warning_risk_codes: tuple[str, ...] = ()
    metadata_only: bool = True
    no_host_actuation: bool = True
    no_provider_network_prompt_authority: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostInventoryValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _tuple_str(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _device_from_mapping(value: HostInventoryDevice | Mapping[str, Any]) -> HostInventoryDevice:
    if isinstance(value, HostInventoryDevice):
        return value
    if not isinstance(value, Mapping):
        return HostInventoryDevice(device_id="", kind="other", label="malformed", status="malformed")
    return HostInventoryDevice(
        device_id=str(value.get("device_id") or value.get("id") or ""),
        kind=str(value.get("kind") or "other"),
        label=str(value.get("label") or value.get("name") or ""),
        summary=_mapping(value.get("summary") if isinstance(value.get("summary"), Mapping) else {}),
        status=str(value.get("status") or "unknown"),
        source_label=str(value.get("source_label") or "supplied"),
        control_available=bool(value.get("control_available", False)),
        privileged_action_available=bool(value.get("privileged_action_available", False)),
        metadata_only=bool(value.get("metadata_only", True)),
    )


def _sensor_from_mapping(value: HostInventorySensor | Mapping[str, Any]) -> HostInventorySensor:
    if isinstance(value, HostInventorySensor):
        return value
    if not isinstance(value, Mapping):
        return HostInventorySensor(sensor_id="", kind="unknown", label="malformed", status="malformed")
    return HostInventorySensor(
        sensor_id=str(value.get("sensor_id") or value.get("id") or ""),
        kind=str(value.get("kind") or "unknown"),
        label=str(value.get("label") or value.get("name") or ""),
        status=str(value.get("status") or "unknown"),
        observed_value=value.get("observed_value", value.get("value")),
        unit=str(value.get("unit")) if value.get("unit") is not None else None,
        source_label=str(value.get("source_label") or "supplied"),
        control_available=bool(value.get("control_available", False)),
        metadata_only=bool(value.get("metadata_only", True)),
    )


def build_host_inventory_manifest(
    *,
    manifest_id: str,
    node_id: str,
    host_id: str | None = None,
    os_family: str = "unknown",
    os_release: str = "unknown",
    architecture: str = "unknown",
    cpu_summary: Mapping[str, Any] | None = None,
    gpu_summary: Mapping[str, Any] | None = None,
    ram_summary: Mapping[str, Any] | None = None,
    disk_summary: Mapping[str, Any] | None = None,
    network_interface_summary: Mapping[str, Any] | None = None,
    battery_power_summary: Mapping[str, Any] | None = None,
    thermal_zone_summary: Mapping[str, Any] | None = None,
    fan_pwm_controller_summary: Mapping[str, Any] | None = None,
    audio_device_summary: Mapping[str, Any] | None = None,
    camera_display_input_summary: Mapping[str, Any] | None = None,
    service_manager_summary: Mapping[str, Any] | None = None,
    privilege_model_summary: Mapping[str, Any] | None = None,
    devices: Sequence[HostInventoryDevice | Mapping[str, Any]] | None = None,
    sensors: Sequence[HostInventorySensor | Mapping[str, Any]] | None = None,
    observed_at: str | None = None,
    source_labels: Sequence[str] | None = None,
    unsupported_deferred_labels: Sequence[str] | None = None,
    warning_risk_codes: Sequence[str] | None = None,
) -> HostInventoryManifest:
    fan_summary = _mapping(fan_pwm_controller_summary)
    deferred = list(unsupported_deferred_labels or ())
    if not fan_summary:
        fan_summary = {"status": "unknown_unavailable_deferred", "control_available": False, "telemetry_only": True}
        deferred.append("fan_pwm_control_deferred")
    else:
        fan_summary.setdefault("telemetry_only", True)
        fan_summary.setdefault("control_available", False)
    return HostInventoryManifest(
        manifest_id=manifest_id,
        node_id=node_id,
        host_id=host_id or node_id,
        os_family=os_family.lower() if os_family else "unknown",
        os_release=os_release,
        architecture=architecture,
        cpu_summary=_mapping(cpu_summary),
        gpu_summary=_mapping(gpu_summary),
        ram_summary=_mapping(ram_summary),
        disk_summary=_mapping(disk_summary),
        network_interface_summary=_mapping(network_interface_summary),
        battery_power_summary=_mapping(battery_power_summary),
        thermal_zone_summary=_mapping(thermal_zone_summary),
        fan_pwm_controller_summary=fan_summary,
        audio_device_summary=_mapping(audio_device_summary),
        camera_display_input_summary=_mapping(camera_display_input_summary),
        service_manager_summary=_mapping(service_manager_summary),
        privilege_model_summary=_mapping(privilege_model_summary),
        devices=tuple(_device_from_mapping(item) for item in (devices or ())),
        sensors=tuple(_sensor_from_mapping(item) for item in (sensors or ())),
        observed_at=observed_at or _now_iso(),
        source_labels=_tuple_str(source_labels),
        unsupported_deferred_labels=tuple(sorted(set(str(item) for item in deferred))),
        warning_risk_codes=_tuple_str(warning_risk_codes),
    )


def collect_basic_host_inventory(*, manifest_id: str = "basic-host-inventory", node_id: str = "local-node") -> HostInventoryManifest:
    """Best-effort standard-library inventory; read-only and non-privileged."""

    disk = shutil.disk_usage(os.getcwd())
    return build_host_inventory_manifest(
        manifest_id=manifest_id,
        node_id=node_id,
        os_family=(platform.system() or "unknown").lower(),
        os_release=platform.release() or "unknown",
        architecture=platform.machine() or "unknown",
        cpu_summary={"processor": platform.processor() or "unknown", "cpu_count": os.cpu_count()},
        disk_summary={"cwd_total_bytes": disk.total, "cwd_free_bytes": disk.free},
        service_manager_summary={"status": "not_probed", "read_only": True},
        privilege_model_summary={"status": "not_probed", "read_only": True},
        source_labels=("standard_library_platform_os_shutil",),
        warning_risk_codes=("best_effort_read_only_inventory",),
    )



def build_host_inventory_from_collector_results(
    results: Sequence[Any],
    *,
    manifest_id: str = "collector-backed-host-inventory",
    node_id: str = "local-node",
    host_id: str | None = None,
) -> HostInventoryManifest:
    """Build a metadata-only inventory manifest from Phase 2 collectors.

    Collector results are read-only observations. They populate inventory summary
    fields but never grant device control or privileged host action.
    """

    from sentientos.host_collectors import HostCollectorResult, validate_host_collector_result

    by_id: dict[str, HostCollectorResult] = {str(result.collector_id): result for result in results if isinstance(result, HostCollectorResult)}
    source_labels: list[str] = []
    warnings: list[str] = []
    deferred: list[str] = []
    devices: list[HostInventoryDevice] = []
    sensors: list[HostInventorySensor] = []
    observed_values = [result.observed_at for result in by_id.values() if result.observed_at]
    observed_at = min(observed_values) if observed_values else _now_iso()

    for result in by_id.values():
        source_labels.append(f"collector:{result.collector_id}:{result.source}")
        warnings.extend(result.warnings)
        warnings.extend(f"collector_validation:{finding}" for finding in validate_host_collector_result(result).findings)
        if result.status in {"unavailable", "partial", "error"}:
            deferred.append(f"{result.collector_id}_{result.status}")
        warnings.extend(f"{result.collector_id}:{finding.code}" for finding in result.findings)
        warnings.extend(f"risk:{risk}" for risk in result.risks)

    def _collector_values(collector_id: str) -> dict[str, Any]:
        result = by_id.get(collector_id)
        return dict(result.values) if result is not None else {}

    def _collector_status(collector_id: str, default: str = "partial") -> str:
        result = by_id.get(collector_id)
        return result.status if result is not None else default

    platform_values = _collector_values("platform")
    cpu_values = _collector_values("cpu")
    memory_values = _collector_values("memory")
    disk_values = _collector_values("disk")
    network_values = _collector_values("network_interfaces")
    service_values = _collector_values("service_manager")
    thermal_values = _collector_values("thermal_sensors")
    fan_values = _collector_values("fan_pwm")

    if platform_values:
        devices.append(HostInventoryDevice(device_id="host-platform", kind="other", label="Host platform", summary=platform_values, status=_collector_status("platform"), source_label="collector:platform"))
    if cpu_values or platform_values.get("cpu_count") is not None:
        merged_cpu = {**({"cpu_count": platform_values.get("cpu_count")} if platform_values.get("cpu_count") is not None else {}), **cpu_values}
        devices.append(HostInventoryDevice(device_id="cpu-summary", kind="cpu", label="CPU summary", summary=merged_cpu, status=_collector_status("cpu"), source_label="collector:cpu"))
    if memory_values:
        devices.append(HostInventoryDevice(device_id="ram-summary", kind="ram", label="RAM summary", summary=memory_values, status=_collector_status("memory"), source_label="collector:memory"))
    if disk_values:
        devices.append(HostInventoryDevice(device_id="disk-summary", kind="disk", label="Disk summary", summary=disk_values, status=_collector_status("disk"), source_label="collector:disk"))
    if network_values:
        devices.append(HostInventoryDevice(device_id="network-interfaces", kind="network", label="Network interfaces", summary=network_values, status=_collector_status("network_interfaces"), source_label="collector:network_interfaces"))
    if service_values:
        devices.append(HostInventoryDevice(device_id="service-manager", kind="service_manager", label="Service manager", summary=service_values, status=_collector_status("service_manager"), source_label="collector:service_manager"))

    zones = tuple(thermal_values.get("zones") or ())
    for index, zone in enumerate(zones):
        if isinstance(zone, Mapping):
            sensors.append(HostInventorySensor(sensor_id=f"thermal-{index}", kind="temperature", label=str(zone.get("label") or zone.get("id") or f"thermal-{index}"), status="observed", observed_value=zone.get("temperature_c"), unit="C", source_label="collector:thermal_sensors", control_available=False, metadata_only=True))
    fans = tuple(fan_values.get("fans") or ())
    for index, fan in enumerate(fans):
        if isinstance(fan, Mapping):
            sensors.append(HostInventorySensor(sensor_id=f"fan-rpm-{index}", kind="fan_rpm", label=str(fan.get("id") or f"fan-rpm-{index}"), status="observed", observed_value=fan.get("rpm"), unit="rpm", source_label="collector:fan_pwm", control_available=False, metadata_only=True))

    fan_summary = {
        **fan_values,
        "status": _collector_status("fan_pwm", "unavailable"),
        "telemetry_only": True,
        "pwm_signal_observed": bool(fan_values.get("pwm_signal_observed", False)),
        "control_available": False,
        "control_deferred": True,
        "requires_future_allowlist": True,
        "requires_privilege_broker": True,
    }
    if fan_summary["pwm_signal_observed"]:
        deferred.extend(("fan_pwm_control_deferred", "pwm_presence_not_control_authority", "requires_future_allowlist", "requires_privilege_broker"))

    thermal_summary = {**thermal_values, "telemetry_only": True, "control_available": False, "thermal_actuation_deferred": True}
    if zones:
        deferred.append("thermal_actuation_deferred")

    return build_host_inventory_manifest(
        manifest_id=manifest_id,
        node_id=node_id,
        host_id=host_id,
        os_family=str(platform_values.get("os_family") or "unknown"),
        os_release=str(platform_values.get("os_release") or "unknown"),
        architecture=str(platform_values.get("architecture") or "unknown"),
        cpu_summary={**cpu_values, **({"cpu_count": platform_values.get("cpu_count")} if platform_values.get("cpu_count") is not None and "cpu_count" not in cpu_values else {})},
        ram_summary=memory_values,
        disk_summary=disk_values,
        network_interface_summary=network_values,
        thermal_zone_summary=thermal_summary,
        fan_pwm_controller_summary=fan_summary,
        service_manager_summary=service_values,
        devices=devices,
        sensors=sensors,
        observed_at=observed_at,
        source_labels=tuple(sorted(set(source_labels))),
        unsupported_deferred_labels=tuple(sorted(set(deferred))),
        warning_risk_codes=tuple(sorted(set(warnings))),
    )


def collect_host_inventory_manifest(
    *,
    manifest_id: str = "collector-backed-host-inventory",
    node_id: str = "local-node",
    host_id: str | None = None,
) -> HostInventoryManifest:
    """Collect read-only Phase 2 host observations and build a manifest."""

    from sentientos.host_collectors import collect_basic_host_observations

    return build_host_inventory_from_collector_results(
        collect_basic_host_observations(),
        manifest_id=manifest_id,
        node_id=node_id,
        host_id=host_id,
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def host_inventory_digest(manifest: HostInventoryManifest) -> str:
    return hashlib.sha256(_canonical_json(manifest.to_dict()).encode("utf-8")).hexdigest()


def summarize_host_inventory_manifest(manifest: HostInventoryManifest) -> dict[str, Any]:
    return {
        "manifest_id": manifest.manifest_id,
        "node_id": manifest.node_id,
        "host_id": manifest.host_id,
        "os_family": manifest.os_family,
        "architecture": manifest.architecture,
        "device_count": len(manifest.devices),
        "sensor_count": len(manifest.sensors),
        "fan_pwm_status": manifest.fan_pwm_controller_summary.get("status", "unknown"),
        "fan_pwm_telemetry_only": bool(manifest.fan_pwm_controller_summary.get("telemetry_only", True)),
        "metadata_only": manifest.metadata_only,
        "no_host_actuation": manifest.no_host_actuation,
        "no_provider_network_prompt_authority": manifest.no_provider_network_prompt_authority,
        "unsupported_deferred_labels": manifest.unsupported_deferred_labels,
        "warning_risk_codes": manifest.warning_risk_codes,
        "digest": host_inventory_digest(manifest),
    }


def _check_non_negative_mapping(prefix: str, mapping: Mapping[str, Any], findings: list[str]) -> None:
    for key, value in mapping.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0:
            findings.append(f"{prefix}:{key}:negative_value")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and "percent" in str(key).lower() and not 0 <= float(value) <= 100:
            findings.append(f"{prefix}:{key}:percent_out_of_range")
        if str(key) in CONTROL_CLAIM_KEYS and bool(value):
            findings.append(f"{prefix}:{key}:authority_claim_forbidden")


def validate_host_inventory_manifest(manifest: HostInventoryManifest) -> HostInventoryValidationResult:
    findings: list[str] = []
    if not manifest.manifest_id:
        findings.append("missing_manifest_id")
    if not manifest.node_id:
        findings.append("missing_node_id")
    if not manifest.host_id:
        findings.append("missing_host_id")
    if manifest.os_family not in KNOWN_OS_FAMILIES:
        findings.append("unknown_os_family")
    if not manifest.metadata_only:
        findings.append("manifest_not_metadata_only")
    if not manifest.no_host_actuation:
        findings.append("host_actuation_claimed")
    if not manifest.no_provider_network_prompt_authority:
        findings.append("provider_network_prompt_authority_claimed")
    summary_maps = {
        "cpu_summary": manifest.cpu_summary,
        "gpu_summary": manifest.gpu_summary,
        "ram_summary": manifest.ram_summary,
        "disk_summary": manifest.disk_summary,
        "network_interface_summary": manifest.network_interface_summary,
        "battery_power_summary": manifest.battery_power_summary,
        "thermal_zone_summary": manifest.thermal_zone_summary,
        "fan_pwm_controller_summary": manifest.fan_pwm_controller_summary,
        "audio_device_summary": manifest.audio_device_summary,
        "camera_display_input_summary": manifest.camera_display_input_summary,
        "service_manager_summary": manifest.service_manager_summary,
        "privilege_model_summary": manifest.privilege_model_summary,
    }
    for name, mapping in summary_maps.items():
        if not isinstance(mapping, Mapping):
            findings.append(f"{name}:malformed_mapping")
            continue
        _check_non_negative_mapping(name, mapping, findings)
    if bool(manifest.fan_pwm_controller_summary.get("control_available", False)) and not manifest.fan_pwm_controller_summary.get("backend_metadata"):
        findings.append("fan_pwm_control_claimed_without_backend_metadata")
    for device in manifest.devices:
        prefix = f"device:{device.device_id or '<missing>'}"
        if not device.device_id or not device.label:
            findings.append(prefix + ":malformed_device")
        if device.kind not in DEVICE_KINDS:
            findings.append(prefix + ":unknown_device_kind")
        if not device.metadata_only:
            findings.append(prefix + ":not_metadata_only")
        if device.control_available or device.privileged_action_available:
            findings.append(prefix + ":privileged_action_claimed")
        _check_non_negative_mapping(prefix + ":summary", device.summary, findings)
    for sensor in manifest.sensors:
        prefix = f"sensor:{sensor.sensor_id or '<missing>'}"
        if not sensor.sensor_id or not sensor.label:
            findings.append(prefix + ":malformed_sensor")
        if sensor.kind not in SENSOR_KINDS:
            findings.append(prefix + ":unknown_sensor_kind")
        if not sensor.metadata_only:
            findings.append(prefix + ":not_metadata_only")
        if sensor.control_available:
            findings.append(prefix + ":control_claimed")
        if isinstance(sensor.observed_value, (int, float)) and not isinstance(sensor.observed_value, bool) and sensor.observed_value < 0 and sensor.kind in {"fan_rpm", "battery_percent", "utilization", "capacity"}:
            findings.append(prefix + ":negative_observed_value")
        if sensor.kind == "battery_percent" and isinstance(sensor.observed_value, (int, float)) and not 0 <= float(sensor.observed_value) <= 100:
            findings.append(prefix + ":percent_out_of_range")
    return HostInventoryValidationResult(ok=not findings, findings=tuple(findings))
