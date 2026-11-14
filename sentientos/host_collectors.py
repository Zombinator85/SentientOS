"""Read-only host observation collectors for Host Embodiment Phase 2.

Collectors in this module observe local metadata only. They do not mutate host
state, open network connections, invoke providers, assemble prompts, install
packages or drivers, kill processes, restart services, or write fan/PWM/thermal
controls.
"""

from __future__ import annotations

import ctypes
import csv
import fnmatch
import importlib
import io
import math
import os
import platform
import shutil
import subprocess
import time
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
CPUUtilizationProvider = Callable[[], Any]
DirectoryLister = Callable[[str], Sequence[str]]
TextReader = Callable[[str], str | None]
WindowsFeatureProvider = Callable[[int], bool]


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


def _psutil_memory_provider() -> Mapping[str, Any] | None:
    """Read current system memory through the explicitly optional psutil package."""

    try:
        psutil = importlib.import_module("psutil")
    except ImportError:
        return None
    memory = psutil.virtual_memory()
    return {
        "total_bytes": int(memory.total),
        "available_bytes": int(memory.available),
        "used_percent": float(memory.percent),
    }


def _windows_memory_status() -> Mapping[str, Any]:
    """Read system-wide physical memory counters with GlobalMemoryStatusEx."""
    from ctypes import wintypes

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(  # type: ignore[attr-defined]
            ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx_failed")
    total = int(status.ullTotalPhys)
    available = int(status.ullAvailPhys)
    if total <= 0 or not 0 <= available <= total:
        raise ValueError("GlobalMemoryStatusEx_values_invalid")
    return {"total_bytes": total, "available_bytes": available,
        "used_percent": round(100.0 * (total - available) / total, 6)}


def collect_memory_observation(*, memory_provider: MemoryProvider | None = None,
        system: str | None = None,
        windows_memory_provider: MemoryProvider | None = None,
        observed_at: str | None = None) -> HostCollectorResult:
    provider = memory_provider or _psutil_memory_provider
    source = "injected_memory_provider" if memory_provider is not None else "psutil:virtual_memory"
    os_family = (system or platform.system() or "unknown").lower()
    try:
        supplied = dict(provider() or {})
    except Exception as exc:  # deterministic tests may inject failing providers
        if memory_provider is None and isinstance(exc, ImportError):
            supplied = {}
        elif memory_provider is None and os_family == "windows":
            supplied = {}
        else:
            return _result("memory", "error", observed_at=observed_at, source=source, findings=(_finding("memory_provider_error", "warning", str(exc)),), warnings=("memory_unavailable",))
    values: dict[str, Any] = dict(supplied)
    if not values and memory_provider is None and os_family == "windows":
        windows_provider = windows_memory_provider or _windows_memory_status
        source = ("injected_windows_memory_provider" if windows_memory_provider
            is not None else "windows_api:GlobalMemoryStatusEx")
        try:
            values = dict(windows_provider() or {})
        except Exception as exc:
            return _result("memory", "unavailable", observed_at=observed_at,
                source=source, findings=(_finding("memory_details_unavailable", "info",
                    type(exc).__name__),), warnings=("sensor_unavailable:memory",))
    if values:
        return _result(
            "memory",
            "available" if "used_percent" in values else "partial",
            observed_at=observed_at,
            source=source,
            values=values,
            findings=() if "used_percent" in values else (_finding("memory_usage_unavailable", "info", "Total RAM observed but utilization was not computed."),),
        )
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


def _psutil_cpu_utilization() -> float:
    """Return a bounded-time CPU sample; an interval avoids psutil's first-call sentinel."""

    psutil = importlib.import_module("psutil")
    return float(psutil.cpu_percent(interval=0.1))


def _windows_system_times() -> tuple[int, int, int]:
    """Return machine-wide idle, kernel, and user time counters in 100 ns units."""
    from ctypes import wintypes

    idle = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(  # type: ignore[attr-defined]
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        raise OSError("GetSystemTimes_failed")

    def ticks(value: Any) -> int:
        return (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)

    return ticks(idle), ticks(kernel), ticks(user)


def _windows_cpu_utilization(*, system_times_provider: Callable[[], tuple[int, int, int]] | None = None,
        interval_seconds: float = 0.1) -> float:
    """Compute host-wide busy percent from two read-only Windows API samples."""
    provider = system_times_provider or _windows_system_times
    before = provider()
    time.sleep(interval_seconds)
    after = provider()
    idle_delta = after[0] - before[0]
    kernel_delta = after[1] - before[1]
    user_delta = after[2] - before[2]
    total_delta = kernel_delta + user_delta
    if (min(idle_delta, kernel_delta, user_delta) < 0 or total_delta <= 0
            or idle_delta > total_delta):
        raise ValueError("GetSystemTimes_delta_invalid")
    return 100.0 * (total_delta - idle_delta) / total_delta


def collect_cpu_observation(
    *, cpu_utilization_provider: CPUUtilizationProvider | None = None,
    system: str | None = None,
    windows_cpu_utilization_provider: CPUUtilizationProvider | None = None,
    observed_at: str | None = None
) -> HostCollectorResult:
    values: dict[str, Any] = {"cpu_count": os.cpu_count(), "processor": platform.processor() or "unknown", "utilization_percent": None}
    findings = []
    source = "standard_library:os,platform"
    os_family = (system or platform.system() or "unknown").lower()
    if cpu_utilization_provider is not None:
        provider = cpu_utilization_provider
        provider_source = "injected_cpu_utilization_provider"
    elif os_family == "windows":
        provider = windows_cpu_utilization_provider or _windows_cpu_utilization
        provider_source = ("injected_windows_cpu_utilization" if
            windows_cpu_utilization_provider is not None else "windows_api:GetSystemTimes")
    else:
        provider = _psutil_cpu_utilization
        provider_source = "psutil:cpu_percent(interval=0.1)"
    try:
        utilization = provider()
        if isinstance(utilization, (int, float)) and not isinstance(utilization, bool):
            utilization = float(utilization)
            if math.isfinite(utilization) and 0 <= utilization <= 100:
                values["utilization_percent"] = round(utilization, 6)
                source = provider_source
            else:
                findings.append(_finding("cpu_utilization_invalid", "warning", "CPU utilization sample was outside the finite 0–100 percent range."))
        elif utilization is not None:
            findings.append(_finding("cpu_utilization_invalid", "warning", "CPU utilization sample was not numeric."))
    except ImportError:
        pass
    except Exception as exc:  # contain optional sensor and deterministic test provider failures
        findings.append(_finding("cpu_utilization_provider_error", "warning", type(exc).__name__))
    if values["utilization_percent"] is None and not any(f.code.startswith("cpu_utilization_") for f in findings):
        findings.append(_finding("cpu_utilization_unavailable", "info", "Install the optional runtime dependency to collect a bounded CPU utilization sample."))
    try:
        load1, load5, load15 = os.getloadavg()
        values.update({"load_average_1m": load1, "load_average_5m": load5, "load_average_15m": load15})
        status = "partial"
    except (OSError, AttributeError):
        status = "partial" if values["cpu_count"] is not None else "unavailable"
        findings.append(_finding("load_average_unavailable", "info", "Load average unavailable on this platform."))
    if values["utilization_percent"] is not None:
        status = "available"
    return _result("cpu", status, observed_at=observed_at, source=source, values=values, findings=findings)


def _x86_architecture(value: str) -> bool:
    return value.strip().lower() in {"amd64", "x86_64", "x64", "i386", "i686", "x86"}


def _windows_processor_feature(feature: int) -> bool:
    """Query a documented, read-only processor-feature API without a shell."""

    return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(feature))  # type: ignore[attr-defined]


def collect_cpu_feature_observation(
    *,
    system: str | None = None,
    architecture: str | None = None,
    cpuinfo_path: str = "/proc/cpuinfo",
    text_reader: TextReader | None = None,
    windows_feature_provider: WindowsFeatureProvider | None = None,
    observed_at: str | None = None,
) -> HostCollectorResult:
    """Observe AVX-family facts from kernel metadata or a direct Windows API.

    Absence is false only after a complete applicable query.  Unsupported or
    unreadable sources leave the feature keys absent, which inventory adapts as
    explicit unknown rather than false.
    """

    os_family = (system or platform.system() or "unknown").lower()
    machine = architecture or platform.machine() or "unknown"
    base = {"architecture": machine}
    if not _x86_architecture(machine):
        return _result(
            "cpu_features", "unavailable", observed_at=observed_at,
            source=f"read_only:{os_family}:cpu_features", values=base,
            findings=(_finding("x86_features_not_applicable", "info", machine),),
            warnings=("cpu_features_not_applicable",),
        )
    if os_family == "linux":
        text = _safe_read(cpuinfo_path, text_reader)
        if text is None:
            return _result("cpu_features", "unavailable", observed_at=observed_at,
                           source="read_only:/proc/cpuinfo", values=base,
                           findings=(_finding("cpu_feature_source_unavailable", "warning", cpuinfo_path),),
                           warnings=("sensor_unavailable:cpu_features",))
        records = []
        for line in text.splitlines():
            key, separator, raw = line.partition(":")
            if separator and key.strip().lower() in {"flags", "features"}:
                records.append(frozenset(raw.strip().lower().split()))
        if not records:
            return _result("cpu_features", "unavailable", observed_at=observed_at,
                           source="read_only:/proc/cpuinfo", values=base,
                           findings=(_finding("cpu_feature_record_missing", "warning", cpuinfo_path),),
                           warnings=("sensor_unavailable:cpu_features",))
        # A feature is usable across the host only when every exposed processor
        # record reports it.  A successfully parsed record makes absence false.
        common = set.intersection(*(set(record) for record in records))
        values = {**base, "avx": "avx" in common, "avx2": "avx2" in common, "avx512": "avx512f" in common}
        return _result("cpu_features", "available", observed_at=observed_at,
                       source="read_only:/proc/cpuinfo:flags", values=values)
    if os_family == "windows":
        provider = windows_feature_provider or _windows_processor_feature
        # Windows PROCESSOR_FEATURE_ID values: AVX=39, AVX2=40, AVX512F=41.
        try:
            values = {**base, "avx": bool(provider(39)), "avx2": bool(provider(40)), "avx512": bool(provider(41))}
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            return _result("cpu_features", "unavailable", observed_at=observed_at,
                           source="windows_api:IsProcessorFeaturePresent", values=base,
                           findings=(_finding("windows_cpu_feature_api_unavailable", "warning"),),
                           warnings=("sensor_unavailable:cpu_features",))
        return _result("cpu_features", "available", observed_at=observed_at,
                       source="windows_api:IsProcessorFeaturePresent", values=values)
    return _result("cpu_features", "unavailable", observed_at=observed_at,
                   source=f"read_only:{os_family}:cpu_features", values=base,
                   findings=(_finding("cpu_feature_platform_unsupported", "info", os_family),),
                   warnings=("sensor_unavailable:cpu_features",))


_PCI_VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}


def collect_accelerator_observation(
    *,
    system: str | None = None,
    drm_path: str = "/sys/class/drm",
    directory_lister: DirectoryLister | None = None,
    text_reader: TextReader | None = None,
    observed_at: str | None = None,
) -> HostCollectorResult:
    """Enumerate display accelerators through read-only Linux DRM sysfs."""

    os_family = (system or platform.system() or "unknown").lower()
    if os_family != "linux":
        return _result("accelerator", "unavailable", observed_at=observed_at,
                       source=f"read_only:{os_family}:accelerator", findings=(_finding("accelerator_platform_source_unavailable", "info", os_family),),
                       warnings=("sensor_unavailable:accelerator",))
    if directory_lister is None and not Path(drm_path).is_dir():
        return _result("accelerator", "unavailable", observed_at=observed_at,
                       source="read_only:/sys/class/drm", findings=(_finding("drm_enumeration_unavailable", "warning", drm_path),),
                       warnings=("sensor_unavailable:accelerator",))
    try:
        listed = (tuple(str(item) for item in directory_lister(drm_path)) if directory_lister is not None
                  else tuple(item.name for item in Path(drm_path).iterdir()))
    except OSError:
        return _result("accelerator", "unavailable", observed_at=observed_at,
                       source="read_only:/sys/class/drm", findings=(_finding("drm_enumeration_failed", "warning", drm_path),),
                       warnings=("sensor_unavailable:accelerator",))
    entries = sorted(entry for entry in listed if entry.startswith("card") and entry[4:].isdigit())
    devices: list[dict[str, Any]] = []
    for entry in entries:
        base = f"{drm_path}/{entry}/device"
        vendor_id = (_safe_read(f"{base}/vendor", text_reader) or "").strip().lower() or None
        device_id = (_safe_read(f"{base}/device", text_reader) or "").strip().lower() or None
        raw_vram = _safe_read(f"{base}/mem_info_vram_total", text_reader)
        try:
            vram = int(raw_vram.strip()) if raw_vram is not None else None
            if vram is not None and vram < 0:
                vram = None
        except ValueError:
            vram = None
        devices.append({"device_key": entry, "vendor_id": vendor_id,
                        "vendor": _PCI_VENDORS.get(vendor_id) if vendor_id else None,
                        "family": device_id, "vram_bytes": vram})
    values: dict[str, Any] = {"observed": bool(devices), "devices": devices, "enumeration_complete": True}
    findings: list[HostCollectorFinding] = []
    if len(devices) == 1:
        for key in ("vendor", "family", "vram_bytes"):
            if devices[0][key] is not None:
                values[key] = devices[0][key]
        if devices[0]["vram_bytes"] is None:
            findings.append(_finding("accelerator_vram_unknown", "info"))
    elif len(devices) > 1:
        findings.append(_finding("accelerator_singular_facts_ambiguous", "info"))
    return _result("accelerator", "available" if not findings else "partial", observed_at=observed_at,
                   source="read_only:/sys/class/drm", values=values, findings=findings,
                   warnings=tuple(finding.code for finding in findings),
                   risks=("hardware_identity_is_not_runtime_availability",) if devices else ())


_NVIDIA_SMI_QUERY = (
    "index,utilization.gpu,utilization.memory,memory.total,memory.used,"
    "temperature.gpu,power.draw")
_NVIDIA_SMI_TIMEOUT_SECONDS = 0.75
_NVIDIA_SMI_OUTPUT_LIMIT_BYTES = 65_536


def _run_nvidia_smi_query() -> str:
    """Run only a bounded device-wide nvidia-smi telemetry query."""
    executable = shutil.which("nvidia-smi")
    if not executable:
        raise FileNotFoundError("nvidia_smi_not_found")
    options: dict[str, Any] = {}
    if os.name == "nt":
        startup_info = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        startup_info.wShowWindow = subprocess.SW_HIDE  # type: ignore[attr-defined]
        options["startupinfo"] = startup_info
        options["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    completed = subprocess.run(
        [executable, f"--query-gpu={_NVIDIA_SMI_QUERY}",
         "--format=csv,noheader,nounits"],
        shell=False, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=_NVIDIA_SMI_TIMEOUT_SECONDS, check=False,
        **options,
    )
    if completed.returncode != 0:
        raise OSError("nvidia_smi_query_failed")
    if len(completed.stdout.encode("utf-8", "replace")) > _NVIDIA_SMI_OUTPUT_LIMIT_BYTES:
        raise ValueError("nvidia_smi_output_oversized")
    return completed.stdout


def _nvidia_smi_observation(raw: str, *, observed_at: str | None,
        elapsed: float | None) -> HostCollectorResult:
    source = "nvidia-smi:device-wide-query"
    if not isinstance(raw, str) or len(raw.encode("utf-8", "replace")) > _NVIDIA_SMI_OUTPUT_LIMIT_BYTES:
        return _result("nvidia_gpu", "unavailable", observed_at=observed_at,
            source=source, findings=(_finding("nvidia_smi_output_invalid", "warning"),),
            warnings=("sensor_unavailable:nvidia_gpu",),
            privacy_notes=("Samples are device-wide; no process list or process attribution is queried.",))
    devices: list[dict[str, Any]] = []
    findings: list[HostCollectorFinding] = []

    def metric(raw_value: str, *, integer: bool = False) -> float | int | None:
        value = raw_value.strip()
        if not value or value.casefold() in {"n/a", "[n/a]", "not supported", "[not supported]"}:
            return None
        try:
            number = float(value)
        except ValueError:
            return None
        if not math.isfinite(number):
            return None
        return int(number) if integer and number.is_integer() else number

    try:
        rows = csv.reader(io.StringIO(raw, newline=""), strict=True)
        for row in rows:
            if not row or all(not value.strip() for value in row):
                continue
            if len(row) != 7 or len(devices) >= 32:
                raise ValueError("nvidia_smi_row_shape_invalid")
            index_value = metric(row[0], integer=True)
            gpu_util = metric(row[1])
            memory_util = metric(row[2])
            total_mib = metric(row[3])
            used_mib = metric(row[4])
            temperature = metric(row[5])
            power = metric(row[6])
            if (index_value is None or isinstance(index_value, bool)
                    or index_value < 0 or any(device["index"] == index_value
                        for device in devices)):
                raise ValueError("nvidia_smi_device_index_invalid")
            missing: list[str] = []
            if gpu_util is None or not 0 <= gpu_util <= 100:
                gpu_util = None
                missing.append("utilization")
            if memory_util is None or not 0 <= memory_util <= 100:
                memory_util = None
                if "utilization" not in missing:
                    missing.append("memory_utilization")
            total_bytes = (int(total_mib * 1024 * 1024)
                if total_mib is not None and total_mib > 0 else None)
            used_bytes = (int(used_mib * 1024 * 1024)
                if used_mib is not None and used_mib >= 0 else None)
            if total_bytes is None or used_bytes is None or used_bytes > total_bytes:
                total_bytes = used_bytes = None
                missing.append("memory")
            if temperature is None:
                missing.append("temperature")
            elif not 0 <= temperature <= 150:
                temperature = None
                missing.append("temperature")
            if power is None:
                missing.append("power")
            elif power < 0:
                power = None
                missing.append("power")
            if not isinstance(index_value, int):
                raise ValueError("nvidia_smi_device_index_invalid")
            device = {"index": index_value,
                "gpu_utilization_percent": gpu_util,
                "memory_utilization_percent": memory_util,
                "vram_total_bytes": total_bytes,
                "vram_used_bytes": used_bytes,
                "vram_free_bytes": total_bytes - used_bytes
                    if total_bytes is not None and used_bytes is not None else None,
                "vram_utilization_percent": round(100.0 * used_bytes / total_bytes, 6)
                    if total_bytes is not None and used_bytes is not None else None,
                "temperature_c": temperature,
                "power_watts": power,
                "unavailable_measurements": missing}
            devices.append(device)
            findings.extend(_finding("nvidia_smi_measurement_unavailable", "info",
                f"device:{index_value}:{name}") for name in missing)
    except (csv.Error, TypeError, ValueError, OverflowError):
        return _result("nvidia_gpu", "unavailable", observed_at=observed_at,
            source=source, findings=(_finding("nvidia_smi_output_invalid", "warning"),),
            warnings=("sensor_unavailable:nvidia_gpu",),
            privacy_notes=("Samples are device-wide; no process list or process attribution is queried.",))
    values = {"devices": devices, "device_count": len(devices),
        "collector_overhead_seconds": elapsed, "sample_scope": "device_wide",
        "per_process_attribution_available": False}
    has_measurement = any(any(value is not None for key, value in device.items()
        if key not in {"index", "unavailable_measurements"}) for device in devices)
    status = "unavailable" if not devices else (
        "partial" if findings or not has_measurement else "available")
    warnings = (("sensor_unavailable:nvidia_gpu",) if status == "unavailable" else ())
    return _result("nvidia_gpu", status, observed_at=observed_at,
        source=source, values=values, findings=findings, warnings=warnings,
        privacy_notes=("Samples are device-wide; no process list or process attribution is queried.",))


def collect_nvidia_gpu_observation(
    *,
    nvml_provider: Any = None,
    nvidia_smi_query_provider: Callable[[], str] | None = None,
    observed_at: str | None = None,
    monotonic: Callable[[], float] = time.perf_counter,
) -> HostCollectorResult:
    """Collect read-only NVIDIA device telemetry through optional NVML.

    NVML supplies device-wide samples here. This collector does not infer
    per-process attribution, select a GPU for inference, or control the device.
    Missing API calls remain unavailable in the returned measurement fields.
    """
    started = monotonic()
    if nvml_provider is None:
        try:
            nvml_provider = importlib.import_module("pynvml")
        except (ImportError, ModuleNotFoundError):
            query_provider = nvidia_smi_query_provider or _run_nvidia_smi_query
            try:
                raw = query_provider()
                fallback_elapsed = monotonic() - started
            except Exception:
                return _result(
                    "nvidia_gpu", "unavailable", observed_at=observed_at,
                    source="optional_python:nvidia-ml-py/NVML;nvidia-smi:unavailable",
                    findings=(_finding("nvml_dependency_unavailable", "info"),
                        _finding("nvidia_smi_observation_unavailable", "info")),
                    warnings=("sensor_unavailable:nvidia_gpu",),
                    privacy_notes=("No GPU control or per-process inspection is performed.",),
                )
            return _nvidia_smi_observation(raw, observed_at=observed_at,
                elapsed=fallback_elapsed if math.isfinite(fallback_elapsed)
                    and fallback_elapsed >= 0 else None)

    initialized = False
    devices: list[dict[str, Any]] = []
    findings: list[HostCollectorFinding] = []
    try:
        nvml_provider.nvmlInit()
        initialized = True
        count = nvml_provider.nvmlDeviceGetCount()
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("nvml_device_count_invalid")
        for index in range(count):
            device_findings: list[str] = []
            try:
                handle = nvml_provider.nvmlDeviceGetHandleByIndex(index)
            except Exception:
                findings.append(_finding("nvml_device_handle_unavailable", "warning", str(index)))
                continue

            try:
                raw_name = nvml_provider.nvmlDeviceGetName(handle)
                name = raw_name.decode("utf-8", "replace") if isinstance(raw_name, bytes) else str(raw_name)
            except Exception:
                name = None
                device_findings.append("name")

            metrics: dict[str, Any] = {}
            try:
                utilization = nvml_provider.nvmlDeviceGetUtilizationRates(handle)
                for field in ("gpu", "memory"):
                    value = getattr(utilization, field)
                    if (isinstance(value, bool) or not isinstance(value, (int, float))
                            or not math.isfinite(float(value)) or not 0 <= float(value) <= 100):
                        raise ValueError("nvml_utilization_invalid")
                    metrics[field + "_utilization_percent"] = float(value)
            except Exception:
                metrics["gpu_utilization_percent"] = None
                metrics["memory_utilization_percent"] = None
                device_findings.append("utilization")

            try:
                memory = nvml_provider.nvmlDeviceGetMemoryInfo(handle)
                total, used, free = (int(memory.total), int(memory.used), int(memory.free))
                if total <= 0 or min(used, free) < 0 or used + free > total:
                    raise ValueError("nvml_memory_values_invalid")
                metrics.update({
                    "vram_total_bytes": total,
                    "vram_used_bytes": used,
                    "vram_free_bytes": free,
                    "vram_utilization_percent": round(100.0 * used / total, 6),
                })
            except Exception:
                metrics.update({"vram_total_bytes": None, "vram_used_bytes": None,
                                "vram_free_bytes": None, "vram_utilization_percent": None})
                device_findings.append("memory")

            try:
                temperature = float(nvml_provider.nvmlDeviceGetTemperature(
                    handle, nvml_provider.NVML_TEMPERATURE_GPU))
                if not math.isfinite(temperature) or not 0 <= temperature <= 150:
                    raise ValueError("nvml_temperature_invalid")
                metrics["temperature_c"] = temperature
            except Exception:
                metrics["temperature_c"] = None
                device_findings.append("temperature")

            try:
                power_watts = float(nvml_provider.nvmlDeviceGetPowerUsage(handle)) / 1000.0
                if not math.isfinite(power_watts) or power_watts < 0:
                    raise ValueError("nvml_power_invalid")
                metrics["power_watts"] = power_watts
            except Exception:
                metrics["power_watts"] = None
                device_findings.append("power")

            devices.append({"index": index, "name": name, **metrics,
                            "unavailable_measurements": device_findings})
            findings.extend(_finding("nvml_measurement_unavailable", "info", f"device:{index}:{field}")
                            for field in device_findings)
    except Exception:
        findings.append(_finding("nvml_observation_failed", "warning"))
    finally:
        if initialized:
            try:
                nvml_provider.nvmlShutdown()
            except Exception:
                findings.append(_finding("nvml_shutdown_failed", "warning"))

    elapsed_value = monotonic() - started
    elapsed_valid = math.isfinite(elapsed_value) and elapsed_value >= 0
    elapsed: float | None = float(elapsed_value) if elapsed_valid else None
    if not elapsed_valid:
        findings.append(_finding("collector_overhead_unavailable", "warning"))
    values = {"devices": devices, "device_count": len(devices),
              "collector_overhead_seconds": elapsed, "sample_scope": "device_wide",
              "per_process_attribution_available": False}
    has_measurement = any(
        any(value is not None for key, value in device.items()
            if key not in {"index", "name", "unavailable_measurements"})
        for device in devices)
    if has_measurement:
        status = "partial" if findings else "available"
    elif devices:
        status = "partial"
    else:
        status = "unavailable"
    warnings = tuple(sorted({finding.code for finding in findings if finding.severity == "warning"}))
    return _result(
        "nvidia_gpu", status, observed_at=observed_at,
        source="optional_python:nvidia-ml-py/NVML",
        values=values, findings=findings, warnings=warnings,
        privacy_notes=("Samples are device-wide and are not attributed to a process.",),
    )


def collect_process_observation(
    *,
    proc_path: str = "/proc",
    directory_lister: DirectoryLister | None = None,
    system: str | None = None,
    windows_process_count_provider: Callable[[], int] | None = None,
    observed_at: str | None = None,
) -> HostCollectorResult:
    os_family = (system or platform.system() or "unknown").lower()
    if os_family == "windows":
        provider = windows_process_count_provider or _windows_process_count
        try:
            count = provider()
            if type(count) is not int or count < 0:
                raise ValueError("windows_process_count_invalid")
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            return _result("process", "unavailable", observed_at=observed_at,
                source="windows_api:psapi.EnumProcesses",
                findings=(_finding("process_count_unavailable", "info"),),
                warnings=("sensor_unavailable:process_count",),
                privacy_notes=("Process identifiers and command lines are not retained.",))
        return _result("process", "available", observed_at=observed_at,
            source=("injected_windows_process_count" if windows_process_count_provider
                is not None else "windows_api:psapi.EnumProcesses"),
            values={"process_count": count},
            privacy_notes=("Only the process count is retained; identifiers and command lines are not inspected.",))
    if os_family != "linux":
        return _result("process", "unavailable", observed_at=observed_at,
            source=f"read_only:{os_family}:process_count",
            findings=(_finding("process_count_platform_unsupported", "info", os_family),),
            warnings=("sensor_unavailable:process_count",),
            privacy_notes=("No process identifiers or command lines are inspected.",))
    entries = _safe_list(proc_path, directory_lister)
    if not entries:
        return _result("process", "unavailable", observed_at=observed_at, source="read_only:/proc directory names", findings=(_finding("process_count_unavailable", "info", "Process count unavailable without privileged or platform-specific probing."),), warnings=("sensor_unavailable:process_count",), privacy_notes=("No process command lines are inspected.",))
    count = sum(1 for entry in entries if str(entry).isdigit())
    status = "available" if count else "unavailable"
    return _result("process", status, observed_at=observed_at, source="read_only:/proc directory names", values={"process_count": count}, privacy_notes=("Only numeric process directory names are counted; command lines are not read.",))


def _windows_process_count() -> int:
    """Count Windows processes with the read-only PSAPI enumeration call."""
    dword = ctypes.c_ulong
    capacity = 4096
    while capacity <= 1_048_576:
        process_ids = (dword * capacity)()
        bytes_returned = dword()
        ok = ctypes.windll.psapi.EnumProcesses(  # type: ignore[attr-defined]
            process_ids, ctypes.sizeof(process_ids), ctypes.byref(bytes_returned))
        if not ok:
            raise OSError("EnumProcesses_failed")
        if bytes_returned.value % ctypes.sizeof(dword):
            raise ValueError("EnumProcesses_byte_count_invalid")
        count = bytes_returned.value // ctypes.sizeof(dword)
        if count < capacity:
            return count
        capacity *= 2
    raise ValueError("EnumProcesses_capacity_exceeded")


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
        collect_cpu_feature_observation(observed_at=stamp),
        collect_accelerator_observation(observed_at=stamp),
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
