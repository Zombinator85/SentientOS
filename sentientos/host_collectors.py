"""Read-only host observation collectors for Host Embodiment Phase 2.

Collectors in this module observe local metadata only. They do not mutate host
state, open network connections, invoke providers, assemble prompts, install
packages or drivers, kill processes, restart services, or write fan/PWM/thermal
controls.
"""

from __future__ import annotations

import fnmatch
import os
import platform
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

COLLECTOR_STATUSES = frozenset({"available", "partial", "unavailable", "error"})
FORBIDDEN_COLLECTOR_MARKERS = frozenset(
    {
        "host_mutation_performed",
        "network_performed",
        "privileged_action_performed",
        "fan_pwm_write_marker",
        "thermal_write_marker",
        "process_kill_marker",
        "service_restart_marker",
        "package_install_marker",
        "driver_install_marker",
        "provider_invocation_marker",
        "prompt_assembly_marker",
        "federation_transport_marker",
        "remote_execution_marker",
    }
)

DiskUsageProvider = Callable[[str], Any]
MemoryProvider = Callable[[], Mapping[str, Any] | None]
DirectoryLister = Callable[[str], Sequence[str]]
TextReader = Callable[[str], str]


@dataclass(frozen=True)
class HostCollectorObservation:
    label: str
    value: Any
    unit: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostCollectorFinding:
    code: str
    severity: str = "info"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostCollectorResult:
    collector_id: str
    status: str
    observed_at: str
    source: str
    values: Mapping[str, Any] = field(default_factory=dict)
    observations: tuple[HostCollectorObservation, ...] = ()
    findings: tuple[HostCollectorFinding, ...] = ()
    warnings: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    privacy_notes: tuple[str, ...] = ()
    telemetry_only: bool = True
    host_mutation_performed: bool = False
    network_performed: bool = False
    privileged_action_performed: bool = False
    forbidden_markers: Mapping[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostCollectorValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tuple_str(values: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(value) for value in (values or ()))


def _finding(code: str, severity: str = "info", detail: str = "") -> HostCollectorFinding:
    return HostCollectorFinding(code=code, severity=severity, detail=detail)


def _result(
    collector_id: str,
    status: str,
    *,
    observed_at: str | None = None,
    source: str,
    values: Mapping[str, Any] | None = None,
    observations: Sequence[HostCollectorObservation] | None = None,
    findings: Sequence[HostCollectorFinding] | None = None,
    warnings: Sequence[str] | None = None,
    risks: Sequence[str] | None = None,
    privacy_notes: Sequence[str] | None = None,
    forbidden_markers: Mapping[str, bool] | None = None,
) -> HostCollectorResult:
    return HostCollectorResult(
        collector_id=collector_id,
        status=status if status in COLLECTOR_STATUSES else "error",
        observed_at=observed_at or _now_iso(),
        source=source,
        values=dict(values or {}),
        observations=tuple(observations or ()),
        findings=tuple(findings or ()),
        warnings=_tuple_str(warnings),
        risks=_tuple_str(risks),
        privacy_notes=_tuple_str(privacy_notes),
        forbidden_markers=dict(forbidden_markers or {}),
    )


def _safe_read(path: str, text_reader: TextReader | None = None) -> str | None:
    try:
        if text_reader is not None:
            return text_reader(path)
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None


def _safe_list(path: str, directory_lister: DirectoryLister | None = None) -> tuple[str, ...]:
    try:
        if directory_lister is not None:
            return tuple(str(item) for item in directory_lister(path))
        return tuple(sorted(item.name for item in Path(path).iterdir()))
    except OSError:
        return ()


def _to_float(raw: str | None, *, scale: float = 1.0) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).strip()) / scale
    except (TypeError, ValueError):
        return None


def _disk_usage_dict(usage: Any) -> dict[str, int]:
    return {"total_bytes": int(usage.total), "used_bytes": int(usage.used), "free_bytes": int(usage.free)}


def collect_platform_observation(*, observed_at: str | None = None) -> HostCollectorResult:
    values = {
        "os_family": (platform.system() or "unknown").lower(),
        "os_release": platform.release() or "unknown",
        "platform": platform.platform(aliased=True, terse=True) or "unknown",
        "architecture": platform.machine() or "unknown",
        "python_implementation": platform.python_implementation() or "unknown",
        "cpu_count": os.cpu_count(),
    }
    return _result(
        "platform",
        "available",
        observed_at=observed_at,
        source="standard_library:platform,os",
        values=values,
        privacy_notes=("Platform metadata may identify OS family and architecture but does not inspect files or network.",),
    )


def collect_disk_observation(
    *,
    path: str = ".",
    disk_provider: DiskUsageProvider | None = None,
    observed_at: str | None = None,
) -> HostCollectorResult:
    try:
        usage = (disk_provider or shutil.disk_usage)(path)
        values: dict[str, Any] = _disk_usage_dict(usage)
        total = values["total_bytes"]
        values["used_percent"] = round((values["used_bytes"] / total) * 100, 6) if total else None
        values["path_label"] = path
        return _result("disk", "available", observed_at=observed_at, source="standard_library:shutil.disk_usage", values=values)
    except (OSError, AttributeError, TypeError, ValueError) as exc:
        return _result("disk", "error", observed_at=observed_at, source="standard_library:shutil.disk_usage", findings=(_finding("disk_unavailable", "warning", str(exc)),), warnings=("disk_usage_unavailable",))


def collect_memory_observation(*, memory_provider: MemoryProvider | None = None, observed_at: str | None = None) -> HostCollectorResult:
    try:
        supplied = dict(memory_provider() or {}) if memory_provider is not None else {}
    except Exception as exc:  # deterministic tests may inject failing providers
        return _result("memory", "error", observed_at=observed_at, source="injected_memory_provider", findings=(_finding("memory_provider_error", "warning", str(exc)),), warnings=("memory_unavailable",))
    values: dict[str, Any] = dict(supplied)
    if not values:
        if hasattr(os, "sysconf"):
            try:
                page_size = int(os.sysconf("SC_PAGE_SIZE"))
                page_count = int(os.sysconf("SC_PHYS_PAGES"))
                values["total_bytes"] = page_size * page_count
                values["usage_unavailable"] = True
            except (OSError, ValueError, AttributeError):
                values = {}
    if not values:
        return _result("memory", "unavailable", observed_at=observed_at, source="standard_library:os.sysconf", findings=(_finding("memory_details_unavailable", "info", "Exact RAM details unavailable via safe standard library path."),), warnings=("sensor_unavailable:memory",))
    status = "partial" if values.get("usage_unavailable") or "used_percent" not in values else "available"
    findings = () if status == "available" else (_finding("memory_usage_unavailable", "info", "Total RAM observed but utilization was not computed."),)
    return _result("memory", status, observed_at=observed_at, source="standard_library:os.sysconf", values=values, findings=findings)


def collect_cpu_observation(*, observed_at: str | None = None) -> HostCollectorResult:
    values: dict[str, Any] = {"cpu_count": os.cpu_count(), "processor": platform.processor() or "unknown", "utilization_percent": None}
    findings = [_finding("cpu_utilization_unavailable", "info", "Standard library does not provide instantaneous CPU utilization without sampling or optional dependencies.")]
    try:
        load1, load5, load15 = os.getloadavg()
        values.update({"load_average_1m": load1, "load_average_5m": load5, "load_average_15m": load15})
        status = "partial"
    except (OSError, AttributeError):
        status = "partial" if values["cpu_count"] is not None else "unavailable"
        findings.append(_finding("load_average_unavailable", "info", "Load average unavailable on this platform."))
    return _result("cpu", status, observed_at=observed_at, source="standard_library:os,platform", values=values, findings=findings)


def collect_process_observation(
    *,
    proc_path: str = "/proc",
    directory_lister: DirectoryLister | None = None,
    observed_at: str | None = None,
) -> HostCollectorResult:
    entries = _safe_list(proc_path, directory_lister)
    if not entries:
        return _result("process", "unavailable", observed_at=observed_at, source="read_only:/proc directory names", findings=(_finding("process_count_unavailable", "info", "Process count unavailable without privileged or platform-specific probing."),), warnings=("sensor_unavailable:process_count",), privacy_notes=("No process command lines are inspected.",))
    count = sum(1 for entry in entries if str(entry).isdigit())
    status = "available" if count else "unavailable"
    return _result("process", status, observed_at=observed_at, source="read_only:/proc directory names", values={"process_count": count}, privacy_notes=("Only numeric process directory names are counted; command lines are not read.",))


def collect_network_interface_observation(
    *,
    interface_path: str = "/sys/class/net",
    directory_lister: DirectoryLister | None = None,
    text_reader: TextReader | None = None,
    observed_at: str | None = None,
) -> HostCollectorResult:
    names = _safe_list(interface_path, directory_lister)
    if not names:
        return _result("network_interfaces", "unavailable", observed_at=observed_at, source="read_only:/sys/class/net", findings=(_finding("network_interfaces_unavailable", "info", "Interface names unavailable via safe local filesystem observation."),), warnings=("sensor_unavailable:network_interfaces",), privacy_notes=("No connectivity check or network call is performed.",))
    interfaces: list[dict[str, Any]] = []
    for name in sorted(names):
        address = _safe_read(f"{interface_path}/{name}/address", text_reader)
        interfaces.append({"name": str(name), "address_observed": bool(address), "address": str(address).strip() if address else None})
    return _result("network_interfaces", "available", observed_at=observed_at, source="read_only:/sys/class/net", values={"interfaces": interfaces, "connectivity_checked": False}, privacy_notes=("Interface names and local link addresses may be identifying; no connectivity check is performed.",))


def collect_service_manager_observation(*, observed_at: str | None = None) -> HostCollectorResult:
    system = (platform.system() or "unknown").lower()
    label = "unknown"
    if system == "linux":
        if Path("/run/systemd/system").exists():
            label = "systemd_present_marker"
        elif Path("/sbin/openrc").exists() or Path("/run/openrc").exists():
            label = "openrc_present_marker"
        else:
            label = "linux_service_manager_unidentified"
    elif system == "darwin":
        label = "launchd_platform_label"
    elif system == "windows":
        label = "windows_service_control_manager_platform_label"
    status = "partial" if label.endswith("unidentified") or label == "unknown" else "available"
    return _result("service_manager", status, observed_at=observed_at, source="read_only:platform/filesystem labels", values={"service_manager_label": label, "live_services_queried": False, "restart_performed": False}, warnings=("service_health_not_queried",) if status == "partial" else ())


def collect_thermal_sensor_observation(
    *,
    thermal_path: str = "/sys/class/thermal",
    hwmon_path: str = "/sys/class/hwmon",
    directory_lister: DirectoryLister | None = None,
    text_reader: TextReader | None = None,
    observed_at: str | None = None,
) -> HostCollectorResult:
    zones: list[dict[str, Any]] = []
    findings: list[HostCollectorFinding] = []
    for entry in _safe_list(thermal_path, directory_lister):
        if not fnmatch.fnmatch(str(entry), "thermal_zone*"):
            continue
        base = f"{thermal_path}/{entry}"
        raw_temp = _safe_read(f"{base}/temp", text_reader)
        temp_c = _to_float(raw_temp, scale=1000.0)
        label = (_safe_read(f"{base}/type", text_reader) or str(entry)).strip()
        if raw_temp is not None and temp_c is None:
            findings.append(_finding("malformed_thermal_value", "warning", str(entry)))
        elif temp_c is not None:
            zones.append({"id": str(entry), "label": label, "temperature_c": temp_c, "control_available": False, "telemetry_only": True})
    for hwmon in _safe_list(hwmon_path, directory_lister):
        base = f"{hwmon_path}/{hwmon}"
        for child in _safe_list(base, directory_lister):
            if fnmatch.fnmatch(str(child), "temp*_input"):
                raw_temp = _safe_read(f"{base}/{child}", text_reader)
                temp_c = _to_float(raw_temp, scale=1000.0)
                if raw_temp is not None and temp_c is None:
                    findings.append(_finding("malformed_thermal_value", "warning", f"{hwmon}/{child}"))
                elif temp_c is not None:
                    zones.append({"id": f"{hwmon}/{child}", "label": f"{hwmon}:{child}", "temperature_c": temp_c, "control_available": False, "telemetry_only": True})
    if not zones:
        status = "partial" if findings else "unavailable"
        warnings: tuple[str, ...] = ("sensor_unavailable:thermal",) if not findings else ("thermal_values_malformed",)
    else:
        status = "partial" if findings else "available"
        warnings = ("thermal_values_malformed",) if findings else ()
    return _result("thermal_sensors", status, observed_at=observed_at, source="read_only:/sys/class/thermal,/sys/class/hwmon", values={"zones": zones, "control_available": False, "thermal_actuation_deferred": True}, findings=findings, warnings=warnings)


def collect_fan_pwm_observation(
    *,
    hwmon_path: str = "/sys/class/hwmon",
    directory_lister: DirectoryLister | None = None,
    text_reader: TextReader | None = None,
    observed_at: str | None = None,
) -> HostCollectorResult:
    fans: list[dict[str, Any]] = []
    pwm_signals: list[dict[str, Any]] = []
    findings: list[HostCollectorFinding] = []
    for hwmon in _safe_list(hwmon_path, directory_lister):
        base = f"{hwmon_path}/{hwmon}"
        for child in _safe_list(base, directory_lister):
            child_text = str(child)
            if fnmatch.fnmatch(child_text, "fan*_input"):
                raw = _safe_read(f"{base}/{child_text}", text_reader)
                rpm = _to_float(raw)
                if raw is not None and rpm is None:
                    findings.append(_finding("malformed_fan_rpm_value", "warning", f"{hwmon}/{child_text}"))
                elif rpm is not None:
                    fans.append({"id": f"{hwmon}/{child_text}", "rpm": rpm, "telemetry_only": True, "control_available": False})
            elif fnmatch.fnmatch(child_text, "pwm*") and "enable" not in child_text:
                pwm_signals.append({"id": f"{hwmon}/{child_text}", "pwm_signal_observed": True, "possible_controller_observed": True, "control_available": False, "control_deferred": True, "requires_future_allowlist": True, "requires_privilege_broker": True, "telemetry_only": True})
    values = {
        "fans": fans,
        "pwm_signals": pwm_signals,
        "pwm_signal_observed": bool(pwm_signals),
        "control_available": False,
        "control_deferred": True,
        "requires_future_allowlist": True,
        "requires_privilege_broker": True,
        "telemetry_only": True,
    }
    if not fans and not pwm_signals:
        status = "partial" if findings else "unavailable"
        warnings: tuple[str, ...] = ("sensor_unavailable:fan_pwm",) if not findings else ("fan_pwm_values_malformed",)
    else:
        status = "partial" if findings else "available"
        warnings = ("fan_pwm_values_malformed",) if findings else ()
    return _result("fan_pwm", status, observed_at=observed_at, source="read_only:/sys/class/hwmon", values=values, findings=findings, warnings=warnings, risks=("pwm_presence_is_not_control_authority",) if pwm_signals else ())


def collect_basic_host_observations(*, observed_at: str | None = None) -> tuple[HostCollectorResult, ...]:
    """Run the safe standard-library/read-only filesystem collector subset."""

    stamp = observed_at or _now_iso()
    return (
        collect_platform_observation(observed_at=stamp),
        collect_disk_observation(observed_at=stamp),
        collect_memory_observation(observed_at=stamp),
        collect_cpu_observation(observed_at=stamp),
        collect_process_observation(observed_at=stamp),
        collect_network_interface_observation(observed_at=stamp),
        collect_service_manager_observation(observed_at=stamp),
        collect_thermal_sensor_observation(observed_at=stamp),
        collect_fan_pwm_observation(observed_at=stamp),
    )


def validate_host_collector_result(result: HostCollectorResult) -> HostCollectorValidationResult:
    findings: list[str] = []
    if not result.collector_id:
        findings.append("missing_collector_id")
    if result.status not in COLLECTOR_STATUSES:
        findings.append("unknown_status")
    if not result.observed_at:
        findings.append("missing_observed_at")
    if not result.source:
        findings.append("missing_source")
    if not result.telemetry_only:
        findings.append("collector_not_telemetry_only")
    if result.host_mutation_performed:
        findings.append("host_mutation_performed")
    if result.network_performed:
        findings.append("network_performed")
    if result.privileged_action_performed:
        findings.append("privileged_action_performed")
    for key, value in result.forbidden_markers.items():
        if key in FORBIDDEN_COLLECTOR_MARKERS and bool(value):
            findings.append(f"forbidden_marker:{key}")
    text = repr(result.to_dict()).lower()
    marker_terms = {
        "fan_pwm_write_marker": "fan_pwm_write_marker",
        "thermal_write_marker": "thermal_write_marker",
        "process_kill_marker": "process_kill_marker",
        "service_restart_marker": "service_restart_marker",
        "package_install_marker": "package_install_marker",
        "driver_install_marker": "driver_install_marker",
    }
    for term, code in marker_terms.items():
        if term in text and not result.forbidden_markers.get(term, False):
            findings.append(f"forbidden_marker_text:{code}")
    return HostCollectorValidationResult(ok=not findings, findings=tuple(findings))
