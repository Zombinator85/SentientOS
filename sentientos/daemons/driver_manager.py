"""Hardware driver manager with covenant-aware safety logging.

The driver manager inspects GPU, audio, and network interfaces, records
recommendations for missing drivers, and coordinates veil-protected install
requests. All actions emit pulses on the shared bus and are persisted to the
ledger so that shell dashboards and codex expansions can reason about the
current hardware state.
"""

from __future__ import annotations

import logging
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence, cast
from uuid import uuid4

from logging_config import get_log_path
from log_utils import append_json
from sentientos.daemons import pulse_bus

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class DeviceReport:
    """Snapshot of a detected hardware device."""

    device_id: str
    kind: str
    name: str
    vendor: str
    current_driver: str | None = None
    modules: tuple[str, ...] = ()


@dataclass(frozen=True)
class DriverCandidate:
    """Candidate driver that may satisfy a hardware requirement."""

    vendor: str
    kind: str
    name: str
    modules: tuple[str, ...]
    packages: tuple[str, ...]
    identifiers: tuple[str, ...]
    requires_veil: bool
    priority: int = 0


@dataclass
class DriverStatus:
    """Internal state tracked for every detected device."""

    device_id: str
    kind: str
    name: str
    vendor: str
    current_driver: str | None
    recommended_driver: str | None = None
    packages: tuple[str, ...] = ()
    requires_veil: bool = False
    status: str = "unknown"
    last_action: str | None = None
    needs_driver: bool = False
    last_checked: datetime | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.device_id,
            "kind": self.kind,
            "name": self.name,
            "vendor": self.vendor,
            "current_driver": self.current_driver,
            "recommended_driver": self.recommended_driver,
            "packages": list(self.packages),
            "requires_veil": self.requires_veil,
            "status": self.status,
            "last_action": self.last_action,
            "needs_driver": self.needs_driver,
            "metadata": dict(self.metadata),
        }
        if self.last_checked is not None:
            payload["last_checked"] = self.last_checked.isoformat()
        return payload


_DEFAULT_DRIVER_CATALOG: tuple[DriverCandidate, ...] = (
    DriverCandidate(
        vendor="NVIDIA",
        kind="gpu",
        name="nvidia-driver 535",
        modules=("nvidia", "nvidia_drm"),
        packages=("nvidia-driver-535",),
        identifiers=("nvidia", "geforce", "rtx", "gtx", "tesla", "quadro"),
        requires_veil=True,
        priority=100,
    ),
    DriverCandidate(
        vendor="AMD",
        kind="gpu",
        name="amdgpu (mesa)",
        modules=("amdgpu",),
        packages=("mesa-vulkan-drivers",),
        identifiers=("amd", "radeon", "ati"),
        requires_veil=True,
        priority=90,
    ),
    DriverCandidate(
        vendor="Intel",
        kind="gpu",
        name="intel i915",
        modules=("i915",),
        packages=("intel-media-driver",),
        identifiers=("intel", "iris", "uhd"),
        requires_veil=True,
        priority=80,
    ),
    DriverCandidate(
        vendor="ALSA",
        kind="audio",
        name="ALSA (snd_hda_intel)",
        modules=("snd_hda_intel",),
        packages=("alsa-base",),
        identifiers=("hda", "audio", "realtek", "intel", "alsa"),
        requires_veil=False,
        priority=60,
    ),
    DriverCandidate(
        vendor="PulseAudio",
        kind="audio",
        name="PulseAudio Userspace",
        modules=(),
        packages=("pulseaudio",),
        identifiers=("pulseaudio", "pulse audio"),
        requires_veil=False,
        priority=10,
    ),
    DriverCandidate(
        vendor="Intel",
        kind="nic",
        name="Intel e1000e firmware",
        modules=("e1000e", "igb", "ixgbe"),
        packages=("intel-firmware",),
        identifiers=("intel", "e1000", "igb", "ixgbe"),
        requires_veil=True,
        priority=40,
    ),
    DriverCandidate(
        vendor="Realtek",
        kind="nic",
        name="Realtek r8169 firmware",
        modules=("r8169", "r8168", "rtl8168"),
        packages=("realtek-firmware",),
        identifiers=("realtek", "rtl", "r8168", "r8169"),
        requires_veil=True,
        priority=40,
    ),
)

_ALLOWED_DRIVER_VENDORS = {
    "nvidia",
    "amd",
    "intel",
    "alsa",
    "pulseaudio",
    "realtek",
    "broadcom",
    "qualcomm",
}


class DriverManager:
    """Daemon responsible for driver discovery and covenant-safe installs."""

    def __init__(
        self,
        *,
        ledger_path: Path | None = None,
        pulse_source: str = "DriverManager",
        ledger_writer: Callable[[Path, Mapping[str, object]], None] | None = None,
        pulse_publisher: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None,
        hardware_probe: Callable[[], Sequence[DeviceReport | Mapping[str, object]]] | None = None,
        driver_catalog: Sequence[DriverCandidate] | None = None,
        command_runner: Callable[[Sequence[str]], str] | None = None,
        veil_requester: Callable[[DriverStatus, DriverCandidate, str], None] | None = None,
        driver_installer: Callable[[DriverStatus, DriverCandidate], Mapping[str, object]] | None = None,
        clock: Callable[[], datetime] = _utcnow,
        subscribe_to_pulse: bool = True,
        autoprobe: bool = False,
    ) -> None:
        self._ledger_path = ledger_path or get_log_path("driver_manager.jsonl")
        self._pulse_source = pulse_source
        self._ledger_writer = ledger_writer or (lambda path, entry: append_json(path, dict(entry)))
        self._pulse_publisher = pulse_publisher or pulse_bus.publish
        self._command_runner = command_runner or _default_command_runner
        self._hardware_probe = hardware_probe or self._default_hardware_probe
        self._driver_installer = driver_installer or self._default_driver_installer
        self._veil_requester = veil_requester or self._default_veil_requester
        self._clock = clock
        self._catalog = tuple(driver_catalog or _DEFAULT_DRIVER_CATALOG)
        self._candidates = {candidate.name: candidate for candidate in self._catalog}
        self._devices: dict[str, DriverStatus] = {}
        self._suggested: dict[str, str] = {}
        self._veil_queue: list[dict[str, object]] = []
        self._anomaly_counts: Counter[str] = Counter()
        self._subscription = (
            pulse_bus.subscribe(self._handle_pulse)
            if subscribe_to_pulse
            else None
        )
        if autoprobe:
            self.refresh()

    @property
    def ledger_path(self) -> Path:
        return self._ledger_path

    def stop(self) -> None:
        if self._subscription and self._subscription.active:
            self._subscription.unsubscribe()
            self._subscription = None

    def refresh(self) -> dict[str, object]:
        reports: list[DeviceReport] = []
        for item in self._hardware_probe():
            reports.append(self._coerce_report(item))
        seen: set[str] = set()
        for report in reports:
            status = self._update_status_from_report(report)
            seen.add(status.device_id)
        for device_id in list(self._devices):
            if device_id not in seen:
                status = self._devices[device_id]
                status.status = "offline"
                status.last_checked = self._clock()
        return self.snapshot()

    def snapshot(self) -> dict[str, object]:
        devices = [
            self._devices[key].to_dict()
            for key in sorted(self._devices, key=lambda item: item)
        ]
        return {
            "timestamp": self._clock().isoformat(),
            "devices": devices,
            "veil_pending": [dict(entry) for entry in self._veil_queue],
        }

    def pending_veil_requests(self) -> list[dict[str, object]]:
        return [dict(entry) for entry in self._veil_queue]

    def handle_external_task(self, task: str) -> bool:
        normalized = task.strip().lower()
        if not normalized or "driver" not in normalized:
            return False
        matched = False
        for status in list(self._devices.values()):
            vendor = status.vendor.lower()
            name = status.name.lower()
            if vendor in normalized or name in normalized:
                candidate = self._lookup_candidate(status)
                if candidate is None:
                    continue
                matched = True
                self._emit_suggestion(status, candidate, reason="external_task")
        return matched

    def install_driver(self, device_id: str) -> dict[str, object]:
        if device_id not in self._devices:
            raise KeyError(f"Unknown device: {device_id}")
        status = self._devices[device_id]
        driver_name = status.recommended_driver
        if not driver_name:
            raise RuntimeError("No recommended driver available")
        candidate = self._lookup_candidate(status)
        if candidate is None:
            raise RuntimeError("Recommended driver not recognized")
        vendor = candidate.vendor.lower()
        if vendor not in _ALLOWED_DRIVER_VENDORS:
            raise PermissionError("Driver not permitted by covenant whitelist")

        status.last_action = "install_requested"
        payload: dict[str, object] = {
            "device": status.to_dict(),
            "driver": driver_name,
            "packages": list(candidate.packages),
        }
        try:
            result = self._driver_installer(status, candidate)
        except Exception as exc:  # pragma: no cover - exercised in tests
            status.status = "error"
            status.last_action = "install_failed"
            status.needs_driver = True
            self._log_event(
                "driver_failure",
                status,
                driver_name,
                status_text="error",
                details={"error": str(exc)},
            )
            payload["error"] = str(exc)
            self._publish("driver_failure", payload, priority="critical")
            raise
        install_status = "queued"
        if isinstance(result, Mapping):
            install_status = str(result.get("status", "queued"))
        if candidate.requires_veil:
            install_status = "veil_pending"
            token = f"veil-{uuid4().hex[:8]}"
            self._queue_veil(status, candidate, token)
        elif install_status in {"success", "installed"}:
            status.needs_driver = False
            status.current_driver = driver_name
        status.status = install_status
        self._log_event(
            "driver_install",
            status,
            driver_name,
            status_text=install_status,
            details={"packages": list(candidate.packages)},
        )
        payload["status"] = install_status
        payload["requires_veil"] = candidate.requires_veil
        self._publish(
            "driver_install",
            payload,
            priority="warning" if candidate.requires_veil else "info",
        )
        return {
            "device_id": status.device_id,
            "device": status.name,
            "driver": driver_name,
            "status": install_status,
            "requires_veil": candidate.requires_veil,
        }

    # Internal helpers -------------------------------------------------

    def _lookup_candidate(self, status: DriverStatus) -> DriverCandidate | None:
        if status.recommended_driver and status.recommended_driver in self._candidates:
            return self._candidates[status.recommended_driver]
        return self._recommend_driver(status)

    def _coerce_report(self, report: DeviceReport | Mapping[str, object]) -> DeviceReport:
        if isinstance(report, DeviceReport):
            return report
        if not isinstance(report, Mapping):
            raise TypeError("hardware_probe must yield DeviceReport or mappings")
        device_id = str(
            report.get("device_id")
            or report.get("id")
            or f"device-{uuid4().hex[:8]}"
        )
        kind = str(report.get("kind", "unknown")).lower()
        name = str(report.get("name", device_id))
        vendor = str(report.get("vendor", name))
        driver = report.get("current_driver")
        driver_name = driver.strip() if isinstance(driver, str) else None
        modules_field = report.get("modules")
        modules: tuple[str, ...]
        if isinstance(modules_field, Iterable) and not isinstance(modules_field, (str, bytes)):
            modules = tuple(
                sorted(
                    {
                        str(module).strip().lower()
                        for module in modules_field
                        if str(module).strip()
                    }
                )
            )
        else:
            modules = ()
        normalized_vendor = self._normalize_vendor_name(vendor, name)
        return DeviceReport(
            device_id=device_id,
            kind=kind,
            name=name,
            vendor=normalized_vendor,
            current_driver=driver_name,
            modules=modules,
        )

    def _normalize_vendor_name(self, vendor: str, name: str) -> str:
        text = (vendor or name).strip()
        lowered = text.lower()
        if "nvidia" in lowered:
            return "NVIDIA"
        if "amd" in lowered or "ati" in lowered or "advanced micro devices" in lowered:
            return "AMD"
        if "intel" in lowered:
            return "Intel"
        if "realtek" in lowered:
            return "Realtek"
        if "broadcom" in lowered:
            return "Broadcom"
        if "qualcomm" in lowered or "atheros" in lowered:
            return "Qualcomm"
        if "audio" in lowered or "alsa" in lowered:
            return "ALSA"
        return text.split()[0].strip().title() if text else "Unknown"

    def _recommend_driver(self, status: DriverStatus) -> DriverCandidate | None:
        vendor_text = status.vendor.lower()
        name_text = status.name.lower()
        best: DriverCandidate | None = None
        for candidate in self._catalog:
            if candidate.kind != status.kind:
                continue
            if self._matches_candidate(vendor_text, name_text, candidate):
                if best is None or candidate.priority > best.priority:
                    best = candidate
        return best

    def _matches_candidate(
        self,
        vendor_text: str,
        name_text: str,
        candidate: DriverCandidate,
    ) -> bool:
        vendor_lower = candidate.vendor.lower()
        if vendor_lower and vendor_lower in vendor_text:
            return True
        for identifier in candidate.identifiers:
            ident = identifier.lower()
            if ident and (ident in vendor_text or ident in name_text):
                return True
        return False

    def _update_status_from_report(self, report: DeviceReport) -> DriverStatus:
        status = self._devices.get(report.device_id)
        if status is None:
            status = DriverStatus(
                device_id=report.device_id,
                kind=report.kind,
                name=report.name,
                vendor=report.vendor,
                current_driver=report.current_driver,
            )
            self._devices[report.device_id] = status
        else:
            status.kind = report.kind
            status.name = report.name
            status.vendor = report.vendor
            status.current_driver = report.current_driver
        status.last_checked = self._clock()

        modules_detected = {module.lower() for module in report.modules}
        if report.current_driver:
            modules_detected.add(report.current_driver.lower())
        status.metadata["modules_detected"] = sorted(modules_detected)

        candidate = self._recommend_driver(status)
        if candidate is None:
            status.recommended_driver = None
            status.packages = ()
            status.requires_veil = False
            status.needs_driver = False
            status.status = "ready" if report.current_driver else "unknown"
            self._suggested.pop(status.device_id, None)
            return status

        status.recommended_driver = candidate.name
        status.packages = candidate.packages
        status.requires_veil = candidate.requires_veil
        status.metadata["candidate_modules"] = list(candidate.modules)
        status.metadata["candidate_identifiers"] = list(candidate.identifiers)

        has_module = self._has_required_module(modules_detected, candidate)
        status.needs_driver = not has_module
        if status.needs_driver:
            if status.status != "veil_pending":
                status.status = "missing"
            if self._suggested.get(status.device_id) != candidate.name:
                self._emit_suggestion(status, candidate, reason="missing_driver")
                self._suggested[status.device_id] = candidate.name
        else:
            status.status = "ready"
            status.last_action = "detected"
            self._suggested.pop(status.device_id, None)
        return status

    def _has_required_module(
        self,
        modules_detected: set[str],
        candidate: DriverCandidate,
    ) -> bool:
        if not candidate.modules:
            return True
        lowered = {module.lower() for module in modules_detected}
        for module in candidate.modules:
            token = module.lower()
            for entry in lowered:
                if token == entry or token in entry or entry in token:
                    return True
        return False

    def _emit_suggestion(
        self,
        status: DriverStatus,
        candidate: DriverCandidate,
        *,
        reason: str,
    ) -> None:
        status.last_action = "suggested"
        self._log_event(
            "driver_suggestion",
            status,
            candidate.name,
            status_text="pending",
            details={"reason": reason},
        )
        payload: dict[str, object] = {
            "device": status.to_dict(),
            "driver": candidate.name,
            "packages": list(candidate.packages),
            "reason": reason,
        }
        self._publish("driver_suggestion", payload, priority="warning")

    def _log_event(
        self,
        event: str,
        status: DriverStatus,
        driver: str | None,
        *,
        status_text: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        entry: dict[str, object] = {
            "ts": self._clock().isoformat(),
            "event": event,
            "device": status.name,
            "driver": driver or "",
            "status": status_text,
        }
        if details:
            entry["details"] = dict(details)
        self._ledger_writer(self._ledger_path, entry)

    def _publish(
        self,
        event_type: str,
        payload: Mapping[str, object],
        *,
        priority: str = "info",
    ) -> Mapping[str, object]:
        event: dict[str, object] = {
            "timestamp": self._clock().isoformat(),
            "source_daemon": self._pulse_source,
            "event_type": event_type,
            "priority": priority,
            "payload": dict(payload),
        }
        return self._pulse_publisher(event)

    def _queue_veil(
        self,
        status: DriverStatus,
        candidate: DriverCandidate,
        token: str,
    ) -> None:
        metadata: dict[str, object] = {
            "device_id": status.device_id,
            "device": status.name,
            "driver": candidate.name,
            "packages": list(candidate.packages),
            "ts": token,
        }
        try:
            self._veil_requester(status, candidate, token)
        finally:
            self._update_veil_queue(metadata)

    def _update_veil_queue(self, metadata: Mapping[str, object]) -> None:
        device_id = str(metadata.get("device_id", ""))
        self._veil_queue = [
            entry
            for entry in self._veil_queue
            if entry.get("device_id") != device_id
        ]
        self._veil_queue.append(dict(metadata))

    def _default_driver_installer(
        self,
        status: DriverStatus,
        candidate: DriverCandidate,
    ) -> Mapping[str, object]:
        return {"status": "queued"}

    def _default_veil_requester(
        self,
        status: DriverStatus,
        candidate: DriverCandidate,
        token: str,
    ) -> None:
        # The internal queue is updated separately; this hook allows tests or
        # external systems to record additional metadata.
        return None

    def _handle_pulse(self, event: Mapping[str, object]) -> None:
        event_type = str(event.get("event_type", "")).lower()
        if event_type == "predictive_anomaly":
            payload = event.get("payload", {})
            if isinstance(payload, Mapping):
                category = str(payload.get("category", "")).lower()
            else:
                category = ""
            if category in {"rendering", "network", "audio"}:
                self._anomaly_counts[category] += 1
                if self._anomaly_counts[category] >= 2:
                    self._anomaly_counts[category] = 0
                    self.refresh()
            return
        if event_type in {"codex_expand_task", "driver_task", "expand_task"}:
            payload = event.get("payload", {})
            task = ""
            if isinstance(payload, Mapping):
                raw = payload.get("task") or payload.get("description")
                if isinstance(raw, str):
                    task = raw
            if task and self.handle_external_task(task):
                self.refresh()

    # System interrogation ------------------------------------------------

    def _default_hardware_probe(self) -> Sequence[DeviceReport]:
        lspci_output = self._safe_run(["lspci", "-nnk"])
        lsmod_output = self._safe_run(["lsmod"])
        nvidia_output = self._safe_run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version",
                "--format=csv,noheader",
            ]
        )
        modules_loaded = _parse_lsmod(lsmod_output)
        nvidia_versions = _parse_nvidia_smi(nvidia_output)

        reports: list[dict[str, object]] = []
        counters = {"gpu": 0, "audio": 0, "nic": 0}
        current: dict[str, object] | None = None
        for raw_line in lspci_output.splitlines():
            line = raw_line.strip("\n")
            if not line:
                continue
            if not line.startswith("\t"):
                descriptor = line.split(": ", 1)[1] if ": " in line else line
                kind = _classify_device_kind(descriptor)
                if kind is None:
                    current = None
                    continue
                name = _extract_device_name(descriptor)
                vendor = self._normalize_vendor_name(name, name)
                device_id = f"{kind}-{counters[kind]}"
                counters[kind] += 1
                current = {
                    "id": device_id,
                    "kind": kind,
                    "name": name,
                    "vendor": vendor,
                    "current_driver": None,
                    "modules": [],
                }
                reports.append(current)
            else:
                if current is None:
                    continue
                stripped = line.strip()
                if stripped.startswith("Kernel driver in use:"):
                    driver = stripped.split(":", 1)[1].strip()
                    if driver:
                        current["current_driver"] = driver
                        module_list = cast(list[str], current.setdefault("modules", []))
                        module_list.append(driver)
                elif stripped.startswith("Kernel modules:"):
                    modules_text = stripped.split(":", 1)[1]
                    modules = [
                        module.strip()
                        for module in modules_text.split(",")
                        if module.strip()
                    ]
                    module_list = cast(list[str], current.setdefault("modules", []))
                    module_list.extend(modules)

        enriched: list[DeviceReport] = []
        for raw in reports:
            kind = str(raw.get("kind", ""))
            modules = {
                str(module).strip().lower()
                for module in cast(Iterable[object], raw.get("modules", []))
                if str(module).strip()
            }
            for module in _candidate_modules_for_kind(kind):
                if module in modules_loaded:
                    modules.add(module)
            vendor_lower = str(raw.get("vendor", "")).lower()
            name_lower = str(raw.get("name", "")).lower()
            if vendor_lower == "nvidia" and nvidia_versions:
                for gpu_name, version in nvidia_versions.items():
                    if gpu_name in name_lower or name_lower in gpu_name:
                        raw["current_driver"] = f"nvidia-driver {version}"
                        modules.add("nvidia")
                        break
            raw["modules"] = tuple(sorted(modules))
            enriched.append(self._coerce_report(raw))
        return enriched

    def _safe_run(self, args: Sequence[str]) -> str:
        try:
            return self._command_runner(args)
        except Exception as exc:  # pragma: no cover - avoids noisy failures
            logger.debug("driver manager command failed: %s (%s)", args, exc)
            return ""


def _default_command_runner(args: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(args),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return ""
    return completed.stdout


def _parse_lsmod(output: str) -> set[str]:
    modules: set[str] = set()
    for line in output.splitlines()[1:]:
        parts = line.split()
        if parts:
            modules.add(parts[0].strip().lower())
    return modules


def _parse_nvidia_smi(output: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = [part.strip() for part in stripped.split(",") if part.strip()]
        if len(parts) >= 2:
            mapping[parts[0].lower()] = parts[1]
    return mapping


def _classify_device_kind(descriptor: str) -> str | None:
    text = descriptor.lower()
    if "vga compatible controller" in text or "3d controller" in text:
        return "gpu"
    if "audio" in text:
        return "audio"
    if "ethernet controller" in text or "network controller" in text:
        return "nic"
    return None


def _extract_device_name(descriptor: str) -> str:
    return descriptor.split(":", 1)[-1].strip()


def _candidate_modules_for_kind(kind: str) -> set[str]:
    if kind == "gpu":
        return {"nvidia", "amdgpu", "i915", "nouveau"}
    if kind == "audio":
        return {"snd_hda_intel", "snd_soc", "snd_usb_audio", "snd_aloop"}
    if kind == "nic":
        return {"e1000e", "igb", "ixgbe", "r8169", "r8168", "atlantic"}
    return set()

