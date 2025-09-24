"""High level SentientOS desktop shell primitives.

This module provides a Windows-like UX facade that coordinates the
Codex expansion console, Lumos dashboard, installer integration, and a
sandboxed file explorer.  The goal is to keep the underlying daemons
intact while exposing familiar controls for human operators and tests.
"""

from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from typing import Callable, Deque, Dict, List, Mapping, Sequence
from uuid import uuid4

from logging_config import get_log_path
from log_utils import append_json, read_json
from sentientos.daemons import driver_manager as driver_manager_module, pulse_bus
from sentientos.first_boot import FirstBootWizard, WizardDecisions

try:  # Lazy import to avoid expensive startup during tests.
    from daemon import codex_daemon
except Exception:  # pragma: no cover - codex daemon optional in minimal envs
    codex_daemon = None  # type: ignore[assignment]

__all__ = [
    "ShellApplication",
    "ShellConfig",
    "ShellEventLogger",
    "StartMenu",
    "Taskbar",
    "FileExplorer",
    "CodexConsole",
    "LumosDashboard",
    "SentientShell",
]


_ALLOWED_CODEX_MODES = {"observe", "repair", "full", "expand"}
_BANNED_PATH_SEGMENTS = {"vow", "daemon", "glow"}
_DEFAULT_REASONING_ROOT = Path("/daemon/logs/codex_reasoning")
_DEFAULT_REQUEST_ROOT = Path("/glow/codex_requests")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ShellEventLogger:
    """Centralised ledger + pulse publisher for shell actions."""

    def __init__(
        self,
        *,
        ledger_path: Path | None = None,
        pulse_source: str = "SentientShell",
        ledger_writer: Callable[[Path, Mapping[str, object]], None] | None = None,
        pulse_publisher: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None,
        clock: Callable[[], datetime] = _utcnow,
        pulse_fallback_path: Path | None = None,
    ) -> None:
        self._ledger_path = ledger_path or get_log_path("shell_ledger.jsonl")
        self._pulse_source = pulse_source
        self._ledger_writer = ledger_writer or (lambda path, entry: append_json(path, dict(entry)))
        self._pulse_publisher = pulse_publisher or pulse_bus.publish
        self._clock = clock
        self._pulse_fallback_path = pulse_fallback_path or get_log_path("shell_pulse_fallback.jsonl")

    @property
    def ledger_path(self) -> Path:
        return self._ledger_path

    def record(
        self,
        event_type: str,
        payload: Mapping[str, object] | None = None,
        *,
        priority: str = "info",
    ) -> dict[str, object]:
        """Record ``event_type`` in the audit ledger and pulse bus."""

        if not event_type:
            raise ValueError("event_type is required")
        if payload is None:
            payload = {}
        elif not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")

        timestamp = self._clock().isoformat()
        ledger_entry = {
            "timestamp": timestamp,
            "source": self._pulse_source,
            "event_type": event_type,
            "priority": priority,
            "payload": dict(payload),
        }
        self._ledger_writer(self._ledger_path, ledger_entry)

        pulse_event = {
            "timestamp": timestamp,
            "source_daemon": self._pulse_source,
            "event_type": event_type,
            "priority": priority,
            "payload": dict(payload),
        }
        try:
            self._pulse_publisher(pulse_event)
        except Exception as exc:  # pragma: no cover - fallback path used rarely
            fallback_entry = {
                "timestamp": timestamp,
                "source": self._pulse_source,
                "event_type": event_type,
                "priority": priority,
                "payload": dict(payload),
                "delivery": "fallback",
                "error": str(exc),
            }
            self._ledger_writer(self._pulse_fallback_path, fallback_entry)
        return ledger_entry


class ShellConfig:
    """Mutable configuration persisted for shell preferences."""

    def __init__(self, *, path: Path | None = None) -> None:
        self._path = path or get_log_path("shell_config.json")
        self._data: Dict[str, object] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if not self._path.exists():
            self._data = {
                "codex_mode": "observe",
                "federation_peers": [],
                "auto_apply_predictive": False,
                "auto_apply_federated": False,
                "assistive_enabled": False,
            }
            return
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            self._data = {
                "codex_mode": "observe",
                "federation_peers": [],
                "auto_apply_predictive": False,
                "auto_apply_federated": False,
                "assistive_enabled": False,
            }

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")

    def set_codex_mode(self, mode: str) -> None:
        normalized = mode.strip().lower()
        if normalized not in _ALLOWED_CODEX_MODES:
            raise ValueError(f"codex_mode must be one of: {', '.join(sorted(_ALLOWED_CODEX_MODES))}")
        self._data["codex_mode"] = normalized
        self._persist()

    def set_federation_peers(self, peers: Sequence[str]) -> None:
        self._data["federation_peers"] = sorted({peer.strip() for peer in peers if peer.strip()})
        self._persist()

    def set_auto_apply(self, *, predictive: bool, federated: bool) -> None:
        self._data["auto_apply_predictive"] = bool(predictive)
        self._data["auto_apply_federated"] = bool(federated)
        self._persist()

    def set_assistive_enabled(self, enabled: bool) -> None:
        self._data["assistive_enabled"] = bool(enabled)
        self._persist()

    def snapshot(self) -> Dict[str, object]:
        return dict(self._data)


@dataclass
class ShellApplication:
    """Metadata for applications exposed in the start menu."""

    name: str
    launch: Callable[[], object]
    categories: Sequence[str] = field(default_factory=tuple)
    description: str = ""
    pinned: bool = False
    system: bool = False


class StartMenu:
    """Windows-like launcher supporting apps, settings, and Codex expansions."""

    def __init__(
        self,
        logger: ShellEventLogger,
        *,
        codex_console: "CodexConsole" | None = None,
    ) -> None:
        self._logger = logger
        self._codex_console = codex_console
        self._apps: Dict[str, ShellApplication] = {}
        self._pinned_order: List[str] = []
        self._settings: Dict[str, Callable[[], object]] = {}
        self._open = False
        self._taskbar: Taskbar | None = None

    def bind_taskbar(self, taskbar: "Taskbar") -> None:
        self._taskbar = taskbar

    def register_application(self, app: ShellApplication) -> None:
        key = app.name.lower()
        self._apps[key] = app
        if app.pinned and key not in self._pinned_order:
            self._pinned_order.append(key)

    def register_setting(self, name: str, callback: Callable[[], object]) -> None:
        self._settings[name.lower()] = callback

    def press_super_key(self) -> bool:
        self._open = not self._open
        self._logger.record(
            "start_menu_toggled",
            {"is_open": self._open},
        )
        return self._open

    def list_applications(self) -> List[str]:
        return sorted(app.name for app in self._apps.values())

    def list_pinned(self) -> List[str]:
        return [self._apps[key].name for key in self._pinned_order if key in self._apps]

    def search(self, query: str) -> Dict[str, List[str]]:
        normalized = query.strip().lower()
        apps: List[str] = []
        settings: List[str] = []
        if not normalized:
            return {"apps": apps, "settings": settings}
        for app in self._apps.values():
            haystack = " ".join([app.name, " ".join(app.categories), app.description]).lower()
            if normalized in haystack:
                apps.append(app.name)
        for setting in self._settings:
            if normalized in setting:
                settings.append(setting)
        self._logger.record(
            "start_menu_search",
            {"query": normalized, "results": {"apps": apps, "settings": settings}},
        )
        return {"apps": apps, "settings": settings}

    def launch(self, name: str) -> object:
        if not name:
            raise ValueError("application name required")
        key = name.lower()
        app = self._apps.get(key)
        if app is None:
            raise KeyError(f"Application '{name}' not registered")
        result = app.launch()
        self._logger.record("app_launch", {"application": app.name, "source": "start_menu"})
        if self._taskbar is not None:
            self._taskbar.open_application(app.name, result)
        return result

    def run_codex_expansion(self, prompt: str, *, context: str | None = None) -> Path:
        if self._codex_console is None:
            raise RuntimeError("Codex console is not available")
        request_path = self._codex_console.submit_prompt(prompt, context=context)
        self._logger.record(
            "codex_expansion_requested",
            {"prompt_preview": prompt[:80], "context": bool(context)},
        )
        return request_path

    def open_setting(self, name: str) -> object:
        if not name:
            raise ValueError("setting name required")
        normalized = name.lower()
        callback = self._settings.get(normalized)
        if callback is None:
            raise KeyError(f"Setting '{name}' not registered")
        self._logger.record("setting_opened", {"setting": normalized})
        return callback()


class Taskbar:
    """Minimal taskbar state with clock and tray representation."""

    def __init__(self, logger: ShellEventLogger, *, clock: Callable[[], datetime] = _utcnow) -> None:
        self._logger = logger
        self._clock = clock
        self._running: Dict[str, datetime] = {}
        self._system_tray: Dict[str, object] = {}
        self.position = "bottom"
        self.launcher_alignment = "left"

    def open_application(self, name: str, handle: object | None = None) -> None:
        self._running[name] = self._clock()
        self._logger.record(
            "taskbar_open",
            {"application": name, "handle": str(type(handle).__name__) if handle is not None else "None"},
        )

    def close_application(self, name: str) -> None:
        if name in self._running:
            self._running.pop(name)
            self._logger.record("taskbar_close", {"application": name})

    def running(self) -> List[str]:
        return [name for name, _ in sorted(self._running.items(), key=lambda item: item[1])]

    def system_tray(self) -> Dict[str, object]:
        return dict(self._system_tray)

    def update_tray(self, key: str, value: object) -> None:
        self._system_tray[key] = value
        self._logger.record("taskbar_tray_update", {"key": key, "value": value})

    def clock(self) -> str:
        return self._clock().strftime("%H:%M")


class FileExplorer:
    """Sandboxed explorer mapping home directories to Windows style folders."""

    def __init__(
        self,
        user: str,
        logger: ShellEventLogger,
        *,
        root: Path | None = None,
        time_provider: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._user = user
        self._logger = logger
        self._clock = time_provider
        base_root = root or Path("/home") / user
        self._root = base_root.expanduser().resolve(strict=False)
        self._virtual_map: Dict[str, Path] = {}
        self._init_virtual_structure()

    @property
    def root(self) -> Path:
        return self._root

    def _init_virtual_structure(self) -> None:
        directories = [
            "Desktop",
            "Documents",
            "Downloads",
            "Music",
            "Pictures",
            "Videos",
        ]
        for name in directories:
            path = (self._root / name).resolve(strict=False)
            path.mkdir(parents=True, exist_ok=True)
            self._virtual_map[name] = path
        self._virtual_map["Home"] = self._root

    def _guard_path(self, path: Path, *, allow_restricted: bool) -> Path:
        resolved = path.resolve(strict=False)
        lowered = {segment.lower() for segment in resolved.parts}
        if not allow_restricted and lowered & _BANNED_PATH_SEGMENTS:
            raise PermissionError("Access to system partitions is restricted")
        return resolved

    def list_home(self) -> Dict[str, Path]:
        self._logger.record("file_explorer_list", {"scope": "home"})
        return dict(self._virtual_map)

    def list_directory(self, name: str, *, allow_restricted: bool = False) -> List[str]:
        if name not in self._virtual_map:
            raise KeyError(f"Unknown virtual folder: {name}")
        target = self._guard_path(self._virtual_map[name], allow_restricted=allow_restricted)
        entries = sorted(item.name for item in target.iterdir())
        self._logger.record(
            "file_explorer_open",
            {"folder": name, "entries": len(entries), "timestamp": self._clock().isoformat()},
        )
        return entries

    def open_path(self, path: Path | str, *, allow_restricted: bool = False) -> Path:
        candidate = Path(path)
        resolved = self._guard_path(candidate, allow_restricted=allow_restricted)
        self._logger.record("file_explorer_navigate", {"path": resolved.as_posix()})
        return resolved


class CodexConsole:
    """Frontend helper for Codex expansion prompts and trace review."""

    def __init__(
        self,
        logger: ShellEventLogger,
        *,
        request_dir: Path | None = None,
        trace_dir: Path | None = None,
        codex_module = codex_daemon,
        max_prompt_bytes: int = 50 * 1024,
    ) -> None:
        self._logger = logger
        self._request_dir = request_dir or _DEFAULT_REQUEST_ROOT
        self._trace_dir = trace_dir or _DEFAULT_REASONING_ROOT
        self._codex_module = codex_module
        self._max_prompt_bytes = max_prompt_bytes
        self._request_dir.mkdir(parents=True, exist_ok=True)

    def submit_prompt(self, prompt: str, *, context: str | None = None) -> Path:
        text = prompt.strip()
        if not text:
            raise ValueError("prompt is required")
        encoded = text.encode("utf-8")
        if len(encoded) > self._max_prompt_bytes:
            raise ValueError("prompt exceeds maximum size")
        request_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + f"_{uuid4().hex[:8]}"
        payload = {"task": text}
        if context:
            payload["context"] = context
        path = self._request_dir / f"queue_{request_id}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self._logger.record("codex_prompt_submitted", {"request": path.name})
        return path

    def load_reasoning_traces(self, *, limit: int = 20, offset: int = 0) -> List[dict[str, object]]:
        if limit <= 0:
            return []
        if not self._trace_dir.exists():
            return []
        traces = sorted(
            (path for path in self._trace_dir.glob("trace_*.json") if path.is_file()),
            key=lambda item: item.name,
            reverse=True,
        )
        selected = traces[offset : offset + limit]
        results: List[dict[str, object]] = []
        for trace in selected:
            try:
                results.append(json.loads(trace.read_text(encoding="utf-8")))
            except Exception:
                continue
        self._logger.record(
            "codex_traces_viewed",
            {"count": len(results), "offset": offset, "limit": limit},
        )
        return results

    def trigger_self_repair(self) -> dict | None:
        if self._codex_module is None:
            raise RuntimeError("Codex daemon module not available")
        queue: Queue = Queue()
        result = self._codex_module.run_once(queue)  # type: ignore[operator]
        self._logger.record("codex_self_repair_triggered", {"result": bool(result)})
        return result


class LumosDashboard:
    """Aggregates health, ledger, and codex veil state for quick review."""

    def __init__(
        self,
        logger: ShellEventLogger,
        *,
        ledger_path: Path,
        file_explorer: FileExplorer,
        config: ShellConfig,
        codex_console: CodexConsole,
        driver_manager: driver_manager_module.DriverManager | None = None,
        codex_module = codex_daemon,
        metrics_window: str = "1h",
    ) -> None:
        self._logger = logger
        self._ledger_path = ledger_path
        self._file_explorer = file_explorer
        self._config = config
        self._codex_console = codex_console
        self._driver_manager = driver_manager
        self._codex_module = codex_module
        self._metrics_window = metrics_window
        self._ledger_cache: Deque[dict[str, object]] = deque(maxlen=10)

    def _load_metrics(self) -> dict[str, object]:
        try:
            from sentientos import pulse_query

            metrics = pulse_query.get_metrics(self._metrics_window)
            summary = metrics.get("summary", {}) if isinstance(metrics, Mapping) else {}
        except Exception:
            summary = {}
        return {
            "cpu": summary.get("cpu_pct", 0),
            "ram": summary.get("memory_pct", 0),
            "network": summary.get("network", {}),
        }

    def _load_ledger(self) -> List[dict[str, object]]:
        if self._ledger_cache:
            return list(self._ledger_cache)
        if not self._ledger_path.exists():
            return []
        entries = read_json(self._ledger_path)
        latest = entries[-10:]
        self._ledger_cache.extend(latest)
        return list(self._ledger_cache)

    def _load_driver_status(self) -> dict[str, object]:
        if self._driver_manager is None:
            return {"devices": [], "veil_pending": []}
        try:
            return self._driver_manager.refresh()
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._logger.record("driver_panel_error", {"error": str(exc)})
            return {"devices": [], "veil_pending": []}

    def _scan_veil_requests(self) -> List[dict[str, object]]:
        if self._codex_module is None:
            return []
        suggestions_dir = getattr(self._codex_module, "CODEX_SUGGEST_DIR", None)
        if suggestions_dir is None:
            return []
        requests: List[dict[str, object]] = []
        for path in Path(suggestions_dir).glob("*.veil.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            status = str(data.get("status", "")).lower()
            if status in {"pending", "suggested"}:
                requests.append({"patch_id": data.get("patch_id"), "status": status, "path": path})
        return requests

    def _federation_status(self) -> dict[str, object]:
        snapshot = self._config.snapshot()
        return {
            "connected_peers": snapshot.get("federation_peers", []),
            "auto_apply_predictive": snapshot.get("auto_apply_predictive", False),
            "auto_apply_federated": snapshot.get("auto_apply_federated", False),
        }

    def _load_architect_panel(self) -> dict[str, object]:
        try:
            from architect_daemon import (
                ARCHITECT_REFLECTION_DIR,
                load_architect_status,
            )
        except Exception:
            return {}

        status = load_architect_status()
        cooldown = status.get("cooldown", {})
        if not isinstance(cooldown, Mapping):
            cooldown = {}
        cooldown_payload = {
            "active": bool(status.get("cooldown_active")),
            "until": status.get("cooldown_until_iso", ""),
            "failure_streak": status.get("failure_streak", 0),
        }
        reflection_meta = self._extract_reflection_summary(
            status, ARCHITECT_REFLECTION_DIR
        )
        return {
            "next_cycle": status.get("next_cycle_iso", ""),
            "cooldown": cooldown_payload,
            "autonomy_enabled": bool(status.get("autonomy_enabled", False)),
            "last_reflection_summary": reflection_meta.get("summary"),
            "throttled": bool(
                status.get("throttled", status.get("architect_throttled", False))
            ),
            "cycle_count": status.get("cycle_count", 0),
            "last_reflection": reflection_meta,
        }

    def _load_cycle_summaries(self, limit: int = 20) -> list[dict[str, object]]:
        try:
            from architect_daemon import load_cycle_summaries as _load_cycles
        except Exception:
            return []

        records = _load_cycles(limit=limit)
        cycles: list[dict[str, object]] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            summary = dict(record)
            summary_path = str(summary.pop("path", ""))
            reflections_raw = summary.get("reflections", [])
            backlog_raw = summary.get("backlog_attempts", [])
            conflicts_raw = summary.get("federation_conflicts", [])
            reflections = [
                str(item)
                for item in reflections_raw
                if isinstance(item, str) and item.strip()
            ]
            backlog_attempts: list[dict[str, object]] = []
            for attempt in backlog_raw if isinstance(backlog_raw, list) else []:
                if isinstance(attempt, Mapping):
                    backlog_attempts.append(dict(attempt))
            conflicts: list[dict[str, object]] = []
            for conflict in conflicts_raw if isinstance(conflicts_raw, list) else []:
                if isinstance(conflict, Mapping):
                    conflicts.append(dict(conflict))
            successes = sum(
                1
                for attempt in backlog_attempts
                if str(attempt.get("status")) == "done"
            )
            failures = sum(
                1
                for attempt in backlog_attempts
                if str(attempt.get("status")) in {"failed", "discarded"}
            )
            resolved = sum(
                1
                for conflict in conflicts
                if str(conflict.get("status")) == "resolved"
            )
            total = successes + failures
            success_rate = successes / total if total else 0.0
            cycle_entry = {
                "cycle_id": summary.get("cycle_id"),
                "started_at": summary.get("started_at"),
                "ended_at": summary.get("ended_at"),
                "reflections": reflections,
                "backlog_attempts": backlog_attempts,
                "federation_conflicts": conflicts,
                "cooldown": bool(summary.get("cooldown", False)),
                "anomalies": [
                    str(item)
                    for item in summary.get("anomalies", [])
                    if isinstance(item, str)
                ],
                "notes": str(summary.get("notes", "")),
                "successes": successes,
                "failures": failures,
                "conflicts_resolved": resolved,
                "success_rate": success_rate,
                "summary_path": summary_path,
            }
            cycles.append(cycle_entry)
        return cycles

    def _build_reflection_panel(
        self, metadata: Mapping[str, object] | None
    ) -> dict[str, object]:
        if not isinstance(metadata, Mapping) or not metadata:
            return {}

        def _as_list(name: str) -> list[str]:
            value = metadata.get(name)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return [str(item) for item in value]
            return []

        latest = {
            "summary": str(metadata.get("summary", "")),
            "next_priorities": _as_list("next_priorities"),
            "successes": _as_list("successes"),
            "failures": _as_list("failures"),
            "regressions": _as_list("regressions"),
            "generated_at": str(metadata.get("generated_at", "")),
            "cycle": metadata.get("cycle"),
            "cycle_range": metadata.get("cycle_range", {}),
            "path": str(metadata.get("path", "")),
        }
        return {"latest": latest}

    def _extract_reflection_summary(
        self, status: Mapping[str, object], reflection_dir: Path
    ) -> dict[str, object]:
        metadata: dict[str, object] = {}
        summary_value = status.get("last_reflection_summary")
        if isinstance(summary_value, str) and summary_value.strip():
            metadata["summary"] = summary_value.strip()

        candidates: list[Path] = []
        seen: set[Path] = set()

        path_value = status.get("last_reflection_path")
        if isinstance(path_value, str) and path_value.strip():
            candidate = Path("/") / path_value
            if candidate.suffix != ".json":
                json_candidate = candidate.with_suffix(".json")
                if json_candidate.exists():
                    candidate = json_candidate
            if candidate.exists():
                seen.add(candidate)
                candidates.append(candidate)

        if reflection_dir.exists():
            try:
                files = sorted(
                    reflection_dir.glob("*.json"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            except OSError:
                files = []
            for path in files:
                if path in seen:
                    continue
                candidates.append(path)
                seen.add(path)

        for candidate in candidates:
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, Mapping):
                continue
            summary = data.get("summary")
            if isinstance(summary, str) and summary.strip():
                metadata["summary"] = summary.strip()
            for key in ("next_priorities", "successes", "failures", "regressions"):
                value = data.get(key)
                if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                    metadata[key] = [str(item) for item in value]
            metadata.setdefault("generated_at", data.get("generated_at", ""))
            metadata.setdefault("cycle", data.get("cycle"))
            metadata.setdefault("cycle_range", data.get("cycle_range", {}))
            metadata["path"] = candidate.as_posix()
            break

        if "summary" not in metadata:
            metadata.setdefault("summary", "")
        metadata.setdefault("next_priorities", [])
        metadata.setdefault("successes", [])
        metadata.setdefault("failures", [])
        metadata.setdefault("regressions", [])
        metadata.setdefault("generated_at", "")
        metadata.setdefault("cycle", None)
        metadata.setdefault("cycle_range", {})
        metadata.setdefault("path", "")
        return metadata

    def refresh(self) -> dict[str, object]:
        health = self._load_metrics()
        ledger = self._load_ledger()
        veil_requests = self._scan_veil_requests()
        federation = self._federation_status()
        drivers = self._load_driver_status()
        driver_devices = drivers.get("devices", [])
        if isinstance(driver_devices, list):
            missing = sum(
                1
                for entry in driver_devices
                if isinstance(entry, Mapping) and entry.get("status") == "missing"
            )
        else:
            missing = 0
        architect = self._load_architect_panel()
        reflections_panel = self._build_reflection_panel(
            architect.get("last_reflection")
        )
        cycles = self._load_cycle_summaries()
        dashboard = {
            "health": health,
            "ledger": ledger[-10:],
            "veil_requests": veil_requests,
            "federation": federation,
            "drivers": drivers,
            "architect": architect,
            "reflections": reflections_panel,
            "cycles": cycles,
        }
        self._logger.record(
            "lumos_dashboard_refresh",
            {
                "veil_pending": len(veil_requests),
                "drivers_missing": missing,
                "architect_cooldown_active": bool(
                    architect.get("cooldown", {}).get("active", False)
                ),
                "cycles_count": len(cycles),
            },
        )
        return dashboard

    def export_latest_reflection(self, destination: Path | str) -> Path:
        if not destination:
            raise ValueError("destination is required")

        metadata = self._load_architect_panel().get("last_reflection", {})
        if not isinstance(metadata, Mapping) or not metadata.get("path"):
            raise FileNotFoundError("no_reflection_available")

        source_path = Path(str(metadata["path"]))
        if not source_path.exists():
            raise FileNotFoundError(str(source_path))

        destination_path = Path(destination)
        if destination_path.exists() and destination_path.is_dir():
            destination_path = destination_path / source_path.name
        elif not destination_path.suffix:
            destination_path = destination_path / source_path.name
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(
            source_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        self._logger.record(
            "architect_reflection_exported",
            {
                "source": source_path.as_posix(),
                "destination": destination_path.as_posix(),
            },
        )
        return destination_path

    def install_recommended_driver(self, device_id: str) -> dict[str, object]:
        if self._driver_manager is None:
            raise RuntimeError("Driver manager not available")
        result = self._driver_manager.install_driver(device_id)
        self._logger.record(
            "driver_install_requested_via_dashboard",
            {"device_id": device_id, "status": result.get("status")},
        )
        return result

    def confirm_veil_request(self, patch_id: str) -> dict[str, object]:
        if self._codex_module is None:
            raise RuntimeError("Codex daemon module not available")
        result = self._codex_module.confirm_veil_patch(patch_id)  # type: ignore[operator]
        self._ledger_cache.clear()
        self._logger.record("veil_confirmed_via_dashboard", {"patch_id": patch_id})
        return result

    def reject_veil_request(self, patch_id: str) -> dict[str, object]:
        if self._codex_module is None:
            raise RuntimeError("Codex daemon module not available")
        result = self._codex_module.reject_veil_patch(patch_id)  # type: ignore[operator]
        self._ledger_cache.clear()
        self._logger.record("veil_rejected_via_dashboard", {"patch_id": patch_id})
        return result

    def run_architect_now(self) -> dict[str, object]:
        return self._dashboard.run_architect_now()

    def reset_architect_cooldown(self) -> dict[str, object]:
        return self._dashboard.reset_architect_cooldown()

    def run_architect_now(self) -> dict[str, object]:
        return self._logger.record(
            "architect_run_now", {"requested_via": "dashboard"}
        )

    def reset_architect_cooldown(self) -> dict[str, object]:
        return self._logger.record(
            "architect_reset_cooldown", {"requested_via": "dashboard"}
        )


class SentientShell:
    """Facade wiring together the desktop shell subsystems."""

    def __init__(
        self,
        *,
        user: str | None = None,
        logger: ShellEventLogger | None = None,
        config: ShellConfig | None = None,
        request_dir: Path | None = None,
        trace_dir: Path | None = None,
        codex_module = codex_daemon,
        ci_runner: Callable[[], bool] | None = None,
        pulse_publisher: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None,
        home_root: Path | None = None,
        driver_manager: driver_manager_module.DriverManager | None = None,
        first_boot_wizard: FirstBootWizard | None = None,
    ) -> None:
        from sentientos.installer import AppInstaller  # Local import to avoid cycle

        username = user or os.getenv("USER", "sentient")
        self._logger = logger or ShellEventLogger()
        self._config = config or ShellConfig()
        self._file_explorer = FileExplorer(
            username,
            self._logger,
            root=home_root,
        )
        self._taskbar = Taskbar(self._logger)
        self._codex_console = CodexConsole(
            self._logger,
            request_dir=request_dir,
            trace_dir=trace_dir,
            codex_module=codex_module,
        )
        manager_instance = driver_manager
        if manager_instance is None:
            manager_kwargs: dict[str, object] = {}
            if pulse_publisher is not None:
                manager_kwargs["pulse_publisher"] = pulse_publisher
            manager_instance = driver_manager_module.DriverManager(**manager_kwargs)
        self._driver_manager = manager_instance
        self._dashboard = LumosDashboard(
            self._logger,
            ledger_path=self._logger.ledger_path,
            file_explorer=self._file_explorer,
            config=self._config,
            codex_console=self._codex_console,
            driver_manager=self._driver_manager,
            codex_module=codex_module,
        )
        self._start_menu = StartMenu(self._logger, codex_console=self._codex_console)
        self._start_menu.bind_taskbar(self._taskbar)
        installer_kwargs = {"action_logger": self._logger, "ci_runner": ci_runner}
        if pulse_publisher is not None:
            installer_kwargs["pulse_publisher"] = pulse_publisher
        self._installer = AppInstaller(**installer_kwargs)
        self._assistive_enabled = bool(self._config.snapshot().get("assistive_enabled", False))
        wizard_instance = first_boot_wizard
        if wizard_instance is None:
            wizard_kwargs: dict[str, object] = {"driver_manager": self._driver_manager}
            if pulse_publisher is not None:
                wizard_kwargs["pulse_publisher"] = pulse_publisher
            wizard_instance = FirstBootWizard(**wizard_kwargs)
        self._first_boot_wizard = wizard_instance
        self._first_boot_summary: dict[str, object] | None = None
        if self._first_boot_wizard.should_run():
            summary = self._first_boot_wizard.run()
            self._first_boot_summary = dict(summary)
            self._logger.record(
                "first_boot_wizard_autorun",
                {"status": self._first_boot_summary.get("status")},
            )
        else:
            stored = self._first_boot_wizard.last_summary
            self._first_boot_summary = dict(stored) if stored is not None else None
        self._register_default_apps()

    def _register_default_apps(self) -> None:
        self._start_menu.register_application(
            ShellApplication(
                name="File Explorer",
                launch=self.open_file_explorer,
                categories=["system", "files"],
                description="Browse documents and libraries.",
                pinned=True,
                system=True,
            )
        )
        self._start_menu.register_application(
            ShellApplication(
                name="Lumos Dashboard",
                launch=self.open_lumos_dashboard,
                categories=["system", "monitoring"],
                description="View daemons, pulses, drivers, and veil requests.",
                pinned=True,
                system=True,
            )
        )
        self._start_menu.register_application(
            ShellApplication(
                name="Codex Console",
                launch=lambda: self._codex_console,
                categories=["development", "codex"],
                description="Submit expansions and review traces.",
                pinned=False,
                system=True,
            )
        )
        self._start_menu.register_application(
            ShellApplication(
                name="Install App",
                launch=lambda: "installer",
                categories=["system", "apps"],
                description="Install .deb or .AppImage packages.",
                pinned=False,
                system=True,
            )
        )
        self._start_menu.register_setting("codex mode", lambda: self._config.snapshot().get("codex_mode"))
        self._start_menu.register_setting("federation peers", lambda: self._config.snapshot().get("federation_peers", []))
        self._start_menu.register_setting(
            "assistive technology", lambda: self._config.snapshot().get("assistive_enabled", False)
        )
        self._start_menu.register_setting(
            "re-run first-boot wizard",
            lambda: self.run_first_boot_wizard(force=True),
        )

    @property
    def start_menu(self) -> StartMenu:
        return self._start_menu

    @property
    def taskbar(self) -> Taskbar:
        return self._taskbar

    @property
    def file_explorer(self) -> FileExplorer:
        return self._file_explorer

    @property
    def codex_console(self) -> CodexConsole:
        return self._codex_console

    @property
    def dashboard(self) -> LumosDashboard:
        return self._dashboard

    @property
    def driver_manager(self) -> driver_manager_module.DriverManager:
        return self._driver_manager

    @property
    def first_boot_summary(self) -> dict[str, object] | None:
        if self._first_boot_summary is None:
            return None
        return dict(self._first_boot_summary)

    @property
    def installer(self):
        return self._installer

    def open_file_explorer(self) -> Dict[str, Path]:
        listing = self._file_explorer.list_home()
        self._taskbar.open_application("File Explorer", listing)
        return listing

    def open_lumos_dashboard(self) -> dict[str, object]:
        snapshot = self._dashboard.refresh()
        self._taskbar.open_application("Lumos Dashboard", snapshot)
        return snapshot

    def install_recommended_driver(self, device_id: str) -> dict[str, object]:
        return self._dashboard.install_recommended_driver(device_id)

    def run_first_boot_wizard(
        self,
        decisions: WizardDecisions | None = None,
        *,
        force: bool = False,
    ) -> dict[str, object]:
        if self._first_boot_wizard is None:
            raise RuntimeError("First boot wizard is not available")
        if force:
            self._first_boot_wizard.reset()
        summary = self._first_boot_wizard.run(decisions=decisions, force=force)
        self._first_boot_summary = dict(summary)
        self._logger.record(
            "first_boot_wizard_run",
            {"force": force, "status": self._first_boot_summary.get("status")},
        )
        return dict(summary)

    def press_super_key(self) -> bool:
        return self._start_menu.press_super_key()

    def search(self, query: str) -> Dict[str, List[str]]:
        return self._start_menu.search(query)

    def launch(self, application: str) -> object:
        return self._start_menu.launch(application)

    def run_codex_expansion(self, prompt: str, *, context: str | None = None) -> Path:
        return self._start_menu.run_codex_expansion(prompt, context=context)

    def set_codex_mode(self, mode: str) -> None:
        self._config.set_codex_mode(mode)
        if codex_daemon is not None:
            setattr(codex_daemon, "CODEX_MODE", mode)
        self._logger.record("codex_mode_updated", {"mode": mode})

    def configure_federation_peers(self, peers: Sequence[str]) -> None:
        self._config.set_federation_peers(peers)
        self._logger.record("federation_peers_updated", {"peers": list(peers)})

    def set_auto_apply(self, *, predictive: bool, federated: bool) -> None:
        self._config.set_auto_apply(predictive=predictive, federated=federated)
        if codex_daemon is not None:
            setattr(codex_daemon, "FEDERATED_AUTO_APPLY", bool(federated))
            setattr(codex_daemon, "PREDICTIVE_AUTO_APPLY", bool(predictive))
        self._logger.record(
            "codex_auto_apply_updated",
            {"predictive": predictive, "federated": federated},
        )

    def toggle_assistive(self, enabled: bool) -> None:
        self._assistive_enabled = bool(enabled)
        self._config.set_assistive_enabled(self._assistive_enabled)
        self._logger.record("assistive_toggle", {"enabled": self._assistive_enabled})

    def install_from_button(self, path: Path | str) -> Mapping[str, object]:
        return self._installer.install_via_button(Path(path))

    def install_via_double_click(self, path: Path | str) -> Mapping[str, object]:
        return self._installer.double_click(Path(path))

    def install_via_drag_and_drop(self, path: Path | str) -> Mapping[str, object]:
        return self._installer.drag_and_drop(Path(path))


