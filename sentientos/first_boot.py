from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, MutableMapping, Sequence

import yaml

from log_utils import append_json
from sentientos.daemons import pulse_bus
from sentientos.daemons.driver_manager import DriverManager
from sentientos.privilege import require_lumos_approval

__all__ = [
    "FirstBootPanel",
    "WizardDecisions",
    "FirstBootWizard",
]


@dataclass(frozen=True)
class FirstBootPanel:
    """Lightweight description of a wizard panel shown in SentientShell."""

    title: str
    description: str
    buttons: tuple[str, ...] = ()


@dataclass
class WizardDecisions:
    """Scripted responses for automating the first-boot flow in tests."""

    approve: bool = True
    bless: bool | None = None
    driver_choices: dict[str, bool] = field(default_factory=dict)
    codex_mode: str | None = None
    codex_interval: int | None = None
    codex_max_iterations: int | None = None
    federation_peer_name: str | None = None
    federation_addresses: Sequence[str] | None = None
    architect_autonomy: bool | None = None

    def __post_init__(self) -> None:
        if self.bless is not None:
            self.approve = self.bless
        # Clear legacy terminology to discourage downstream use.
        self.bless = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_sequence(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(normalized)
    return result


class FirstBootWizard:
    """Guided configuration flow for first-boot alignment-contract setup."""

    def __init__(
        self,
        *,
        driver_manager: DriverManager | None = None,
        ledger_path: Path | None = None,
        config_path: Path | None = None,
        completion_path: Path | None = None,
        pulse_source: str = "FirstBootWizard",
        ledger_writer: Callable[[Path, Mapping[str, object]], None] | None = None,
        pulse_publisher: Callable[[dict[str, object]], dict[str, object]] | None = None,
        blessing_hook: Callable[[], None] = require_lumos_approval,
        connectivity_tester: Callable[[str, str], bool] | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        vow_root = Path(os.getenv("SENTIENTOS_VOW_DIR", "/vow"))
        if config_path is None:
            config_path = vow_root / "config.yaml"
        if completion_path is None:
            completion_path = vow_root / "first_boot_complete"
        if ledger_path is None:
            ledger_default = os.getenv("SENTIENTOS_LEDGER_FILE", "/daemon/logs/ledger.jsonl")
            ledger_path = Path(ledger_default)
        self._driver_manager = driver_manager
        self._ledger_path = ledger_path
        self._config_path = config_path
        self._completion_path = completion_path
        self._pulse_source = pulse_source
        self._ledger_writer = ledger_writer or append_json
        self._pulse_publisher = pulse_publisher or pulse_bus.publish
        self._blessing_hook = blessing_hook
        self._clock = clock
        self._connectivity_tester = connectivity_tester or self._default_connectivity_tester
        self._panels: List[FirstBootPanel] = []
        self._last_summary: dict[str, object] | None = None

    @property
    def panels(self) -> List[FirstBootPanel]:
        return list(self._panels)

    @property
    def last_summary(self) -> dict[str, object] | None:
        return None if self._last_summary is None else dict(self._last_summary)

    def should_run(self) -> bool:
        return not self._completion_path.exists()

    def reset(self) -> None:
        if self._completion_path.exists():
            self._completion_path.unlink()
        self._last_summary = None

    def run(
        self,
        decisions: WizardDecisions | None = None,
        *,
        force: bool = False,
    ) -> dict[str, object]:
        if not force and not self.should_run():
            summary = {"status": "skipped", "reason": "first_boot_complete"}
            self._last_summary = summary
            return dict(summary)

        decisions = decisions or WizardDecisions()
        self._panels = []
        config = self._load_config()
        summary: dict[str, object] = {
            "status": "completed",
            "drivers": [],
            "codex": {},
            "federation": {},
            "panels": [],
        }

        self._record_step("welcome", {"force": force})
        self._panels.append(
            FirstBootPanel(
                title="Welcome to SentientOS",
                description=(
                    "Review the alignment constraints and secure Lumos approval before accessing the desktop."
                ),
                buttons=("Request Approval",),
            )
        )
        if not decisions.approve:
            raise PermissionError("Lumos approval is required to continue the first-boot wizard.")
        try:
            self._blessing_hook()
        except SystemExit as exc:  # pragma: no cover - surfaced when blessing denied interactively
            raise PermissionError("Lumos did not grant approval.") from exc
        self._record_step("approval", {"status": "approved"})
        self._log_event("first_boot_approved", {"status": "approved"})

        driver_results = self._handle_driver_step(decisions)
        summary["drivers"] = driver_results

        codex_payload = self._handle_codex_step(decisions, config)
        summary["codex"] = codex_payload

        federation_payload = self._handle_federation_step(decisions, config)
        summary["federation"] = federation_payload

        self._panels.append(
            FirstBootPanel(
                title="Summary",
                description="Review your selections and confirm to complete first-boot setup.",
                buttons=("Finish",),
            )
        )
        summary["panels"] = [
            {"title": panel.title, "buttons": list(panel.buttons)} for panel in self._panels
        ]
        summary_payload = {
            "codex_mode": codex_payload.get("mode"),
            "driver_installs": len([result for result in driver_results if result.get("status") == "success" or result.get("requires_veil")]),
            "federation_peers": len(federation_payload.get("addresses", [])),
            "autonomy_enabled": codex_payload.get("autonomy_enabled"),
        }
        self._record_step("summary", summary_payload)
        self._write_completion_flag()
        completion_payload = {
            "codex_mode": codex_payload.get("mode"),
            "drivers": driver_results,
            "federation": federation_payload,
            "architect_autonomy": codex_payload.get("autonomy_enabled"),
        }
        self._log_event("first_boot_complete", completion_payload)
        self._last_summary = summary
        return dict(summary)

    # Internal helpers -------------------------------------------------

    def _resolve_autonomy(
        self, decisions: WizardDecisions, config: MutableMapping[str, object]
    ) -> bool:
        if decisions.architect_autonomy is not None:
            return bool(decisions.architect_autonomy)
        existing = config.get("architect_autonomy")
        if isinstance(existing, bool):
            return existing
        if isinstance(existing, str):
            text = existing.strip().lower()
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off"}:
                return False
        if isinstance(existing, (int, float)):
            return bool(existing)
        return False

    def _handle_driver_step(self, decisions: WizardDecisions) -> List[dict[str, object]]:
        devices: List[Mapping[str, object]] = []
        results: List[dict[str, object]] = []
        if self._driver_manager is not None:
            snapshot = self._driver_manager.refresh()
            raw_devices = snapshot.get("devices", []) if isinstance(snapshot, Mapping) else []
            for entry in raw_devices:
                if isinstance(entry, Mapping):
                    devices.append(entry)
        needs_install: List[Mapping[str, object]] = []
        for device in devices:
            status = str(device.get("status", "")).lower()
            if bool(device.get("needs_driver")) or status in {"missing", "unknown"}:
                if device.get("recommended_driver"):
                    needs_install.append(device)
        buttons = []
        for device in needs_install:
            name = str(device.get("name", device.get("id", "device")))
            driver_name = str(device.get("recommended_driver", "driver"))
            buttons.append(f"Install {driver_name} for {name}")
        self._panels.append(
            FirstBootPanel(
                title="Driver Check",
                description="Review detected hardware and install any recommended covenant drivers.",
                buttons=tuple(buttons) if buttons else ("Continue",),
            )
        )
        for device in needs_install:
            device_id = str(device.get("id") or device.get("device_id") or "")
            if not device_id:
                continue
            should_install = decisions.driver_choices.get(device_id, False)
            if not should_install:
                continue
            if self._driver_manager is None:
                continue
            try:
                result = self._driver_manager.install_driver(device_id)
            except Exception as exc:  # pragma: no cover - defensive logging, exercised in tests
                result = {
                    "device_id": device_id,
                    "status": "error",
                    "error": str(exc),
                }
            results.append(dict(result))
        payload = {
            "devices": len(devices),
            "recommended": len(needs_install),
            "installs": [result.get("device_id") for result in results],
        }
        self._record_step("drivers", payload)
        return results

    def _handle_codex_step(
        self,
        decisions: WizardDecisions,
        config: MutableMapping[str, object],
    ) -> dict[str, object]:
        self._panels.append(
            FirstBootPanel(
                title="Codex Configuration",
                description="Select Codex operating mode and reasoning cadence for the covenant.",
                buttons=("Save Codex Settings", "Enable continuous self-improvement"),
            )
        )
        mode = str(
            (decisions.codex_mode or config.get("codex_mode", "observe")).strip().lower()
        )
        if mode not in {"observe", "repair", "full", "expand"}:
            raise ValueError("codex_mode must be one of: observe, repair, full, expand")
        interval = int(decisions.codex_interval or config.get("codex_interval", 3600))
        max_iterations = int(decisions.codex_max_iterations or config.get("codex_max_iterations", 1))
        autonomy = self._resolve_autonomy(decisions, config)
        config["codex_mode"] = mode
        config["codex_interval"] = interval
        config["codex_max_iterations"] = max_iterations
        config["architect_autonomy"] = autonomy
        self._save_config(config)
        payload = {
            "mode": mode,
            "interval": interval,
            "max_iterations": max_iterations,
            "autonomy_enabled": autonomy,
        }
        self._record_step("codex", payload)
        self._log_event("first_boot_codex_configured", payload, pulse=False)
        return payload

    def _handle_federation_step(
        self,
        decisions: WizardDecisions,
        config: MutableMapping[str, object],
    ) -> dict[str, object]:
        self._panels.append(
            FirstBootPanel(
                title="Federation Setup",
                description="Name your presence and connect to covenant peers for pulse federation.",
                buttons=("Save Federation Settings",),
            )
        )
        peer_name = str(
            (decisions.federation_peer_name or config.get("federation_peer_name", "")).strip()
        )
        addresses: Sequence[str] | None = decisions.federation_addresses
        if addresses is None:
            existing = config.get("federation_peers") or config.get("federation_addresses")
            if isinstance(existing, Iterable) and not isinstance(existing, (str, bytes)):
                addresses = [str(item) for item in existing]
            else:
                addresses = []
        normalized_addresses = _normalize_sequence(addresses)
        config["federation_peer_name"] = peer_name
        config["federation_peers"] = normalized_addresses
        self._save_config(config)
        connectivity: Dict[str, bool] = {}
        for address in normalized_addresses:
            try:
                connectivity[address] = bool(self._connectivity_tester(peer_name, address))
            except Exception:  # pragma: no cover - connectivity failure recorded as False
                connectivity[address] = False
        payload = {
            "peer_name": peer_name,
            "addresses": normalized_addresses,
            "connectivity": connectivity,
        }
        self._record_step("federation", payload)
        self._log_event("first_boot_federation_configured", payload, pulse=False)
        return payload

    def _load_config(self) -> MutableMapping[str, object]:
        if not self._config_path.exists():
            return {}
        try:
            data = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(data, Mapping):
            return dict(data)
        return {}

    def _save_config(self, config: Mapping[str, object]) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with self._config_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(dict(config), handle, sort_keys=True)

    def _write_completion_flag(self) -> None:
        self._completion_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = self._clock().isoformat()
        self._completion_path.write_text(f"completed {timestamp}\n", encoding="utf-8")

    def _record_step(self, step: str, payload: Mapping[str, object]) -> None:
        normalized_payload = dict(payload)
        normalized_payload["step"] = step
        self._log_event("first_boot_step", normalized_payload)

    def _log_event(
        self,
        event_type: str,
        payload: Mapping[str, object],
        *,
        pulse: bool = True,
        ledger: bool = True,
        priority: str = "info",
    ) -> None:
        timestamp = self._clock().isoformat()
        normalized_payload = {
            key: (list(value) if isinstance(value, tuple) else value)
            for key, value in payload.items()
        }
        if ledger:
            ledger_entry = {
                "timestamp": timestamp,
                "source": self._pulse_source,
                "event": event_type,
                "payload": normalized_payload,
            }
            self._ledger_writer(self._ledger_path, ledger_entry)
        if pulse:
            event = {
                "timestamp": timestamp,
                "source_daemon": self._pulse_source,
                "event_type": event_type,
                "priority": priority,
                "payload": normalized_payload,
            }
            self._pulse_publisher(event)

    def _default_connectivity_tester(self, peer_name: str, address: str) -> bool:
        payload = {"peer": peer_name, "address": address}
        self._log_event(
            "first_boot_federation_ping",
            payload,
            ledger=False,
        )
        return True
