"""ArchitectDaemon — autonomous Codex meta-orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import subprocess
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Iterable, Mapping, MutableMapping, Sequence

import yaml

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from daemon import codex_daemon
from log_utils import append_json
from sentientos.daemons import pulse_bus


ARCHITECT_INTERVAL = float(os.getenv("ARCHITECT_INTERVAL", str(6 * 60 * 60)))
ARCHITECT_MAX_ITERATIONS = int(os.getenv("ARCHITECT_MAX_ITERATIONS", "3"))
ARCHITECT_REQUEST_DIR = Path(
    os.getenv("ARCHITECT_REQUEST_DIR", "/glow/codex_requests")
)
ARCHITECT_SESSION_FILE = Path(
    os.getenv("ARCHITECT_SESSION_FILE", "/daemon/logs/architect_session.json")
)
ARCHITECT_LEDGER_PATH = Path(
    os.getenv("ARCHITECT_LEDGER_PATH", "/daemon/logs/architect_ledger.jsonl")
)
ARCHITECT_CONFIG_PATH = Path(os.getenv("ARCHITECT_CONFIG_PATH", "/vow/config.yaml"))
ARCHITECT_COMPLETION_PATH = Path(
    os.getenv("ARCHITECT_COMPLETION_PATH", "/vow/first_boot_complete")
)

_DEFAULT_CI_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("pytest", "-q"),
    ("verify_audits", "--strict"),
)
_DEFAULT_IMMUTABILITY_COMMAND: tuple[str, ...] = (
    "python",
    "scripts/audit_immutability_verifier.py",
)

SAFETY_ENVELOPE = (
    "Covenant Safety Envelope:\n"
    "- Never modify files under /vow or NEWLEGACY.\n"
    "- Respect privileged paths and immutability manifest entries.\n"
    "- Decline tasks that violate sanctuary ethics or human oversight."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_token(text: str) -> str:
    token = text.strip() or "request"
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in token)


def _normalize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    data: dict[str, object] = {}
    for key, val in value.items():
        if isinstance(val, Mapping):
            data[str(key)] = _normalize_mapping(val)
        else:
            data[str(key)] = val
    return data


@dataclass
class ArchitectRequest:
    """Internal representation for an ArchitectDaemon Codex request."""

    architect_id: str
    mode: str
    reason: str
    context: list[dict[str, object]]
    created_at: datetime
    details: dict[str, object] = field(default_factory=dict)
    iterations: int = 0
    max_iterations: int = 1
    status: str = "submitted"
    codex_prefix: str = ""
    prompt_path: Path | None = None
    branch_name: str | None = None
    last_error: str | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "architect_id": self.architect_id,
            "mode": self.mode,
            "reason": self.reason,
            "iterations": self.iterations,
            "max_iterations": self.max_iterations,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "details": dict(self.details),
            "last_error": self.last_error,
        }



class ArchitectDaemon:
    """Meta-orchestrator that coordinates Codex expansion autonomously."""

    def __init__(
        self,
        *,
        request_dir: Path | str | None = None,
        session_file: Path | str | None = None,
        ledger_path: Path | str | None = None,
        config_path: Path | str | None = None,
        completion_path: Path | str | None = None,
        interval: float | None = None,
        max_iterations: int | None = None,
        ledger_sink: Callable[[dict[str, object]], None] | None = None,
        pulse_publisher: Callable[[dict[str, object]], Mapping[str, object]] | None = None,
        clock: Callable[[], datetime] | None = None,
        ci_commands: Sequence[Sequence[str]] | None = None,
        immutability_command: Sequence[str] | None = None,
    ) -> None:
        self.request_dir = Path(request_dir) if request_dir else ARCHITECT_REQUEST_DIR
        self.session_file = Path(session_file) if session_file else ARCHITECT_SESSION_FILE
        self.ledger_path = Path(ledger_path) if ledger_path else ARCHITECT_LEDGER_PATH
        self.config_path = Path(config_path) if config_path else ARCHITECT_CONFIG_PATH
        self.completion_path = (
            Path(completion_path) if completion_path else ARCHITECT_COMPLETION_PATH
        )
        self._default_interval = float(
            interval if interval is not None else ARCHITECT_INTERVAL
        )
        self.interval = float(self._default_interval)
        self._default_max_iterations = int(
            max_iterations if max_iterations is not None else ARCHITECT_MAX_ITERATIONS
        )
        self.max_iterations = int(self._default_max_iterations)
        self._ledger_sink = ledger_sink
        self._pulse_publisher = pulse_publisher or pulse_bus.publish
        self._clock = clock or _utcnow
        self._ci_commands = [tuple(cmd) for cmd in ci_commands] if ci_commands else [
            tuple(cmd) for cmd in _DEFAULT_CI_COMMANDS
        ]
        self._immutability_command = (
            tuple(immutability_command)
            if immutability_command
            else _DEFAULT_IMMUTABILITY_COMMAND
        )

        self.request_dir.mkdir(parents=True, exist_ok=True)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

        self._requests: dict[str, ArchitectRequest] = {}
        self._prefix_index: dict[str, ArchitectRequest] = {}
        self._context_buffer: Deque[dict[str, object]] = deque(maxlen=25)
        self._ledger_buffer: Deque[dict[str, object]] = deque(maxlen=25)
        self._subscription: pulse_bus.PulseSubscription | None = None
        self._activation_subscription: pulse_bus.PulseSubscription | None = None
        self._subscriptions_enabled = False

        self._session = self._load_session()
        last_reflect = self._session.get("last_reflect")
        self._last_reflect = (
            float(last_reflect)
            if isinstance(last_reflect, (int, float, str)) and str(last_reflect).strip()
            else 0.0
        )

        self._config_mtime: float | None = None
        self._config_snapshot: dict[str, object] = {}
        self._config_sync_in_progress = False
        self._codex_mode = "observe"
        self._autonomy_enabled = False
        self._federation_peer_name = ""
        self._federation_peers: tuple[str, ...] = ()

        self._config_snapshot = self._normalize_config({})
        self._apply_config(self._config_snapshot)

        self._boot_completed = self.completion_path.exists()
        self._active = self._boot_completed
        self._activation_emitted = False
        if self._active:
            self.sync_config(force=True, emit=False)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    def start(self) -> None:
        self._subscriptions_enabled = True
        self._ensure_activation_subscription()
        if self.completion_path.exists():
            self._boot_completed = True
            self._activate(reason="startup")

    def stop(self) -> None:
        self._subscriptions_enabled = False
        if self._subscription and self._subscription.active:
            self._subscription.unsubscribe()
        self._subscription = None
        if self._activation_subscription and self._activation_subscription.active:
            self._activation_subscription.unsubscribe()
        self._activation_subscription = None
        self._active = False
        self._activation_emitted = False

    @property
    def active(self) -> bool:
        """Return whether the ArchitectDaemon is actively processing pulses."""

        return self._active

    def _ensure_activation_subscription(self) -> None:
        if not self._subscriptions_enabled:
            return
        if self._activation_subscription and self._activation_subscription.active:
            return
        self._activation_subscription = pulse_bus.subscribe(self._handle_activation_pulse)

    def _ensure_event_subscription(self) -> None:
        if not self._subscriptions_enabled:
            return
        if self._subscription and self._subscription.active:
            return
        self._subscription = pulse_bus.subscribe(self.handle_pulse)

    def _handle_activation_pulse(self, event: Mapping[str, object]) -> None:
        event_type = event.get("event_type")
        if event_type != "first_boot_complete":
            return
        self._boot_completed = True
        self._activate(reason="first_boot_complete")

    def _activate(self, *, reason: str) -> None:
        if not self._boot_completed and not self.completion_path.exists():
            return
        self._boot_completed = True
        was_active = self._active
        self._active = True
        self.sync_config(force=True, emit=False)
        if self._subscriptions_enabled:
            self._ensure_event_subscription()
        if not self._activation_emitted or not was_active:
            self._emit_activation_event(reason)
            self._activation_emitted = True

    # ------------------------------------------------------------------
    # Session helpers
    def _load_session(self) -> dict[str, object]:
        if not self.session_file.exists():
            return {"runs": 0, "successes": 0, "failures": 0}
        try:
            data = json.loads(self.session_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"runs": 0, "successes": 0, "failures": 0}
        if not isinstance(data, MutableMapping):
            return {"runs": 0, "successes": 0, "failures": 0}
        payload = dict(data)
        payload.setdefault("runs", 0)
        payload.setdefault("successes", 0)
        payload.setdefault("failures", 0)
        return payload

    def _save_session(self) -> None:
        self.session_file.write_text(
            json.dumps(self._session, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _record_success(self) -> None:
        self._session["runs"] = int(self._session.get("runs", 0)) + 1
        self._session["successes"] = int(self._session.get("successes", 0)) + 1
        self._save_session()

    def _record_failure(self) -> None:
        self._session["runs"] = int(self._session.get("runs", 0)) + 1
        self._session["failures"] = int(self._session.get("failures", 0)) + 1
        self._save_session()

    # ------------------------------------------------------------------
    # Configuration management
    def sync_config(self, *, force: bool = False, emit: bool = True) -> None:
        if not force and not self._active:
            return
        if self._config_sync_in_progress:
            return
        self._config_sync_in_progress = True
        try:
            mtime: float | None = None
            if self.config_path.exists():
                try:
                    mtime = self.config_path.stat().st_mtime
                except OSError:
                    mtime = None
            data: Mapping[str, object] | None = None
            if self.config_path.exists():
                try:
                    loaded = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
                except Exception:
                    loaded = {}
                if isinstance(loaded, Mapping):
                    data = loaded
                else:
                    data = {}
            else:
                data = {}
            snapshot = dict(self._normalize_config(data))
            should_apply = force or snapshot != self._config_snapshot
            if not should_apply:
                self._config_mtime = mtime
                return
            previous = dict(self._config_snapshot)
            self._config_snapshot = snapshot
            self._config_mtime = mtime
            self._apply_config(snapshot)
            if emit and previous != snapshot:
                self._emit_config_update(previous, snapshot)
        finally:
            self._config_sync_in_progress = False

    def _normalize_config(self, data: Mapping[str, object] | None) -> dict[str, object]:
        payload = data or {}
        mode_value = payload.get("codex_mode", self._codex_mode or "observe")
        mode = str(mode_value).strip().lower()
        if mode not in {"observe", "repair", "full", "expand"}:
            mode = "observe"
        interval = self._coerce_float(payload.get("codex_interval"), self._default_interval)
        max_iterations = self._coerce_int(
            payload.get("codex_max_iterations"), self._default_max_iterations
        )
        peer_name = str(payload.get("federation_peer_name") or "").strip()
        peers_raw = payload.get("federation_peers") or payload.get("federation_addresses")
        peers = self._normalize_peers(peers_raw)
        autonomy = self._coerce_bool(payload.get("architect_autonomy", False))
        return {
            "codex_mode": mode,
            "codex_interval": interval,
            "codex_max_iterations": max_iterations,
            "federation_peer_name": peer_name,
            "federation_peers": tuple(peers),
            "architect_autonomy": autonomy,
        }

    def _normalize_peers(self, raw: object) -> list[str]:
        if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
            return []
        peers: list[str] = []
        seen: set[str] = set()
        for item in raw:
            candidate = str(item).strip()
            if not candidate:
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            peers.append(candidate)
        return peers

    @staticmethod
    def _coerce_float(value: object, default: float) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return float(default)
        return float(default)

    @staticmethod
    def _coerce_int(value: object, default: int) -> int:
        if isinstance(value, (int, float)):
            try:
                return int(value)
            except (ValueError, TypeError):
                return int(default)
        if isinstance(value, str):
            try:
                return int(float(value.strip()))
            except ValueError:
                return int(default)
        return int(default)

    @staticmethod
    def _coerce_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    def _apply_config(self, snapshot: Mapping[str, object]) -> None:
        self._codex_mode = str(snapshot.get("codex_mode", "observe"))
        self.interval = float(snapshot.get("codex_interval", self._default_interval))
        self.max_iterations = int(
            snapshot.get("codex_max_iterations", self._default_max_iterations)
        )
        self._federation_peer_name = str(
            snapshot.get("federation_peer_name", "")
        ).strip()
        peers = snapshot.get("federation_peers", ())
        if isinstance(peers, (list, tuple)):
            self._federation_peers = tuple(str(item) for item in peers)
        else:
            self._federation_peers = ()
        self._autonomy_enabled = bool(snapshot.get("architect_autonomy", False))

    def _current_config_summary(self) -> dict[str, object]:
        return {
            "codex_mode": self._codex_mode,
            "codex_interval": self.interval,
            "codex_max_iterations": self.max_iterations,
            "federation_peer_name": self._federation_peer_name,
            "federation_peers": list(self._federation_peers),
            "architect_autonomy": self._autonomy_enabled,
        }

    def _emit_activation_event(self, reason: str) -> None:
        summary = self._current_config_summary()
        ledger_payload = {
            "event": "architect_enabled",
            "summary": dict(summary),
            "reason": reason,
        }
        self._emit_ledger_event(ledger_payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_enabled",
                "priority": "info",
                "payload": {"summary": dict(summary), "reason": reason},
            }
        )

    def _emit_config_update(
        self, previous: Mapping[str, object], current: Mapping[str, object]
    ) -> None:
        summary = self._current_config_summary()

        def _format(value: object) -> object:
            if isinstance(value, tuple):
                return list(value)
            if isinstance(value, list):
                return list(value)
            return value

        changes: dict[str, dict[str, object]] = {}
        for key, value in summary.items():
            prev_val = _format(previous.get(key))
            curr_val = _format(current.get(key))
            if prev_val != curr_val:
                changes[key] = {"previous": prev_val, "current": curr_val}

        ledger_payload = {
            "event": "architect_config_update",
            "summary": dict(summary),
            "changes": changes,
        }
        self._emit_ledger_event(ledger_payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_config_update",
                "priority": "info",
                "payload": {"summary": dict(summary), "changes": changes},
            }
        )

    def _now(self) -> datetime:
        return self._clock()

    def _has_active_request(self) -> bool:
        return any(
            req.status in {"submitted", "awaiting_veil"} for req in self._requests.values()
        )

    # ------------------------------------------------------------------
    # Public helpers
    def request_expand(
        self,
        description: str,
        context: Iterable[Mapping[str, object]] | None = None,
    ) -> ArchitectRequest:
        if not self._active:
            raise RuntimeError("ArchitectDaemon is inactive until first boot completes.")
        self.sync_config()
        details = {"description": description}
        return self._create_request("expand", description, context, details)

    def request_repair(
        self,
        reason: str,
        context: Iterable[Mapping[str, object]] | None = None,
    ) -> ArchitectRequest:
        if not self._active:
            raise RuntimeError("ArchitectDaemon is inactive until first boot completes.")
        self.sync_config()
        details = {"trigger": reason}
        return self._create_request("repair", reason, context, details)

    def request_reflect(
        self,
        topic: str,
        context: Iterable[Mapping[str, object]] | None = None,
    ) -> ArchitectRequest:
        if not self._active:
            raise RuntimeError("ArchitectDaemon is inactive until first boot completes.")
        self.sync_config()
        details = {"topic": topic}
        return self._create_request("reflect", topic, context, details)

    def get_request(self, architect_id: str) -> ArchitectRequest | None:
        return self._requests.get(architect_id)

    def tick(self, now: datetime | None = None) -> ArchitectRequest | None:
        if not self._active:
            return None
        self.sync_config()
        timestamp = (now or self._now()).timestamp()
        if self.interval <= 0:
            return None
        if self._has_active_request():
            return None
        if timestamp - self._last_reflect < self.interval:
            return None
        request = self.request_reflect("interval_reflection")
        self._last_reflect = timestamp
        self._session["last_reflect"] = timestamp
        self._save_session()
        return request

    # ------------------------------------------------------------------
    # Event ingestion
    def handle_pulse(self, event: Mapping[str, object]) -> None:
        if not self._active:
            return
        self.sync_config()
        normalized = self._normalize_pulse_event(event)
        if normalized is None:
            return
        self._context_buffer.append(normalized)
        source = normalized.get("source")
        event_type = normalized.get("event_type")
        if source == "MonitoringDaemon" and event_type == "monitor_alert":
            self.request_repair("monitor_alert")
        elif source == "DriverManager" and event_type == "driver_failure":
            self.request_repair("driver_failure")

    def handle_ledger_entry(self, entry: Mapping[str, object]) -> None:
        if not self._active:
            return
        self.sync_config()
        normalized = self._normalize_ledger_entry(entry)
        if normalized is None:
            return
        self._ledger_buffer.append(normalized)
        event = normalized.get("event")
        if event == "self_expand":
            request = self._match_request(normalized.get("request_id"))
            if request:
                self._complete_request(request, normalized)
        elif event == "self_expand_rejected":
            request = self._match_request(normalized.get("request_id"))
            if request:
                reason = str(normalized.get("reason", ""))
                self._retry_request(request, reason, normalized)
        elif event == "veil_pending":
            request = self._match_request(normalized.get("patch_id"))
            if request:
                self._surface_veil_request(request, normalized)
        elif event == "self_repair":
            request = self._match_repair_request()
            if request:
                self._complete_request(request, normalized)
        elif event == "self_repair_failed":
            request = self._match_repair_request()
            if request:
                reason = str(normalized.get("reason", ""))
                self._retry_request(request, reason, normalized)

    # ------------------------------------------------------------------
    # Request orchestration
    def _create_request(
        self,
        mode: str,
        reason: str,
        context: Iterable[Mapping[str, object]] | None,
        details: Mapping[str, object],
    ) -> ArchitectRequest:
        architect_id = self._generate_architect_id()
        normalized_context = self._gather_context(context)
        request = ArchitectRequest(
            architect_id=architect_id,
            mode=mode,
            reason=reason,
            context=normalized_context,
            created_at=self._now(),
            details=dict(details),
            max_iterations=max(1, self.max_iterations),
        )
        self._requests[architect_id] = request
        self._write_prompt(request)
        self._publish_pulse(
            {
                "timestamp": request.created_at.isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "codex_request",
                "priority": "info",
                "payload": {
                    "architect_id": architect_id,
                    "mode": mode,
                    "reason": reason,
                    "iterations": request.iterations,
                },
            }
        )
        self._emit_ledger_event(
            {
                "event": "architect_request",
                "architect_id": architect_id,
                "mode": mode,
                "reason": reason,
                "prompt": request.prompt_path.as_posix().lstrip("/")
                if request.prompt_path
                else "",
                "iterations": request.iterations,
                "max_iterations": request.max_iterations,
            }
        )
        self._record_prompt_event(request, "suggested")
        if self._autonomy_enabled:
            self._record_prompt_event(request, "submitted")
        else:
            self._record_prompt_event(request, "pending", priority="warning")
        return request

    def _write_prompt(self, request: ArchitectRequest) -> None:
        stem = self._prompt_stem(request)
        path = self.request_dir / f"{stem}.txt"
        counter = 0
        while path.exists():
            counter += 1
            path = self.request_dir / f"{stem}_{counter}.txt"
        prompt = self._build_prompt(request)
        path.write_text(prompt, encoding="utf-8")
        metadata = request.metadata()
        metadata["prompt_path"] = path.as_posix().lstrip("/")
        metadata["context"] = request.context
        metadata["ledger_snapshot"] = list(self._ledger_buffer)
        path.with_suffix(".json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
        )
        prefix = self._prefix_from_stem(path.stem)
        request.codex_prefix = prefix
        request.prompt_path = path
        self._prefix_index[prefix] = request

    def _build_prompt(self, request: ArchitectRequest) -> str:
        ethics = codex_daemon.load_ethics()
        lines = [
            "You are the ArchitectDaemon for SentientOS.",
            f"Mode: {request.mode}",
            f"Reason: {request.reason}",
            "",
            SAFETY_ENVELOPE,
            "",
            "Ethics Context:",
            ethics or "No additional ethics context provided.",
            "",
        ]
        if request.details:
            lines.append("Request Details:")
            for key, value in sorted(request.details.items()):
                lines.append(f"- {key}: {value}")
            lines.append("")
        if request.context:
            lines.append("Context Events:")
            for entry in request.context:
                lines.append(f"- {json.dumps(entry, sort_keys=True)}")
            lines.append("")
        if self._ledger_buffer:
            lines.append("Recent Codex Ledger Snapshot:")
            for entry in list(self._ledger_buffer)[-10:]:
                lines.append(f"- {json.dumps(entry, sort_keys=True)}")
            lines.append("")
        if request.mode == "repair":
            lines.append("Objective: Address regressions, failing diagnostics, or anomalies.")
            lines.append("Ensure tests pass and health metrics recover.")
        elif request.mode == "expand":
            lines.append(
                "Objective: Expand SentientOS with the requested capability while"
            )
            lines.append("respecting sanctuary law and adding coverage where possible.")
        elif request.mode == "reflect":
            lines.append(
                "Objective: Perform a meta-audit, summarize risks, and propose follow-ups."
            )
        else:
            lines.append("Objective: Respond to the described situation safely and thoroughly.")
        lines.append("")
        lines.append(
            "Always generate actionable plans and patches suitable for Codex application."
        )
        return "\n".join(lines)

    def _complete_request(
        self, request: ArchitectRequest, entry: Mapping[str, object]
    ) -> None:
        request.status = "completed"
        merged = self._finalize_branch(request)
        status = "merged" if merged else "blocked"
        self._emit_ledger_event(
            {
                "event": "architect_success",
                "architect_id": request.architect_id,
                "mode": request.mode,
                "request_id": entry.get("request_id", ""),
                "files_changed": list(entry.get("files_changed", [])),
                "iterations": request.iterations,
                "merge_status": status,
            }
        )
        if merged:
            self._record_success()
        else:
            self._record_failure()
        self._prefix_index.pop(request.codex_prefix, None)

    def _retry_request(
        self,
        request: ArchitectRequest,
        reason: str,
        entry: Mapping[str, object],
    ) -> None:
        request.last_error = reason or str(entry)
        request.iterations += 1
        if request.iterations >= request.max_iterations:
            request.status = "failed"
            self._emit_ledger_event(
                {
                    "event": "architect_failure",
                    "architect_id": request.architect_id,
                    "mode": request.mode,
                    "reason": reason,
                    "iterations": request.iterations,
                }
            )
            self._record_failure()
            self._prefix_index.pop(request.codex_prefix, None)
            return
        self._emit_ledger_event(
            {
                "event": "architect_retry",
                "architect_id": request.architect_id,
                "mode": request.mode,
                "reason": reason,
                "next_iteration": request.iterations,
            }
        )
        self._prefix_index.pop(request.codex_prefix, None)
        self._write_prompt(request)

    def _surface_veil_request(
        self, request: ArchitectRequest, entry: Mapping[str, object]
    ) -> None:
        request.status = "awaiting_veil"
        payload = {
            "architect_id": request.architect_id,
            "mode": request.mode,
            "request_id": entry.get("patch_id", ""),
            "reason": request.reason,
            "files_changed": list(entry.get("files_changed", [])),
            "iterations": request.iterations,
        }
        self._emit_ledger_event(
            {
                "event": "architect_veil_pending",
                "architect_id": request.architect_id,
                "mode": request.mode,
                "request_id": payload["request_id"],
            }
        )
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "veil_request",
                "priority": "warning",
                "payload": payload,
            }
        )
        self._record_prompt_event(request, "pending", priority="warning")

    def _record_prompt_event(
        self, request: ArchitectRequest, state: str, *, priority: str = "info"
    ) -> None:
        prompt_path = (
            request.prompt_path.as_posix().lstrip("/") if request.prompt_path else ""
        )
        payload = {
            "architect_id": request.architect_id,
            "mode": request.mode,
            "reason": request.reason,
            "prompt": prompt_path,
            "codex_prefix": request.codex_prefix,
            "iterations": request.iterations,
            "autonomy": self._autonomy_enabled,
        }
        if state == "pending":
            payload["requires_approval"] = True
        ledger_payload = dict(payload)
        ledger_payload["event"] = f"architect_prompt_{state}"
        self._emit_ledger_event(ledger_payload)
        pulse_payload = dict(payload)
        pulse_payload["status"] = state
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": f"architect_prompt_{state}",
                "priority": priority,
                "payload": pulse_payload,
            }
        )

    # ------------------------------------------------------------------
    # Git and CI management
    def _finalize_branch(self, request: ArchitectRequest) -> bool:
        branch = self._create_branch_name(request)
        request.branch_name = branch
        if not self._prepare_branch(branch):
            return False
        if not self._run_ci_pipeline():
            return False
        if not self._run_immutability_verifier():
            return False
        merged = self._merge_branch(branch, request)
        return merged

    def _prepare_branch(self, branch: str) -> bool:
        ok_main = self._run_git(["checkout", "main"])
        if ok_main.returncode != 0:
            self._emit_ledger_event(
                {
                    "event": "architect_branch_failed",
                    "branch": branch,
                    "reason": "checkout_main_failed",
                    "returncode": ok_main.returncode,
                }
            )
            return False
        result = self._run_git(["checkout", "-B", branch])
        if result.returncode != 0:
            self._emit_ledger_event(
                {
                    "event": "architect_branch_failed",
                    "branch": branch,
                    "reason": "create_branch_failed",
                    "returncode": result.returncode,
                }
            )
            return False
        return True

    def _run_ci_pipeline(self) -> bool:
        for command in self._ci_commands:
            result = self._run_command(command)
            if result.returncode != 0:
                self._emit_ledger_event(
                    {
                        "event": "architect_ci_failed",
                        "command": list(command),
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                )
                return False
        return True

    def _run_immutability_verifier(self) -> bool:
        command = list(self._immutability_command)
        result = self._run_command(command)
        if result.returncode != 0:
            self._emit_ledger_event(
                {
                    "event": "architect_immutability_failed",
                    "command": command,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            return False
        return True

    def _merge_branch(self, branch: str, request: ArchitectRequest) -> bool:
        self._run_git(["checkout", "main"])
        result = self._run_git(["merge", "--no-ff", branch])
        if result.returncode == 0:
            payload = {
                "architect_id": request.architect_id,
                "branch": branch,
                "mode": request.mode,
            }
            self._emit_ledger_event({"event": "architect_merge", **payload})
            self._publish_pulse(
                {
                    "timestamp": self._now().isoformat(),
                    "source_daemon": "ArchitectDaemon",
                    "event_type": "architect_merge",
                    "priority": "info",
                    "payload": payload,
                }
            )
            return True
        self._emit_ledger_event(
            {
                "event": "architect_merge_failed",
                "branch": branch,
                "returncode": result.returncode,
            }
        )
        return False

    def _run_git(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(list(command), capture_output=True, text=True)

    def _run_command(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(list(command), capture_output=True, text=True)

    # ------------------------------------------------------------------
    # Matching helpers
    def _match_request(self, request_id: object) -> ArchitectRequest | None:
        if not isinstance(request_id, str) or not request_id:
            return None
        for prefix, request in list(self._prefix_index.items()):
            if request_id.startswith(prefix):
                return request
        return None

    def _match_repair_request(self) -> ArchitectRequest | None:
        for request in self._requests.values():
            if request.mode == "repair" and request.status in {"submitted", "completed"}:
                return request
        return None

    # ------------------------------------------------------------------
    # Prompt helpers
    def _gather_context(
        self, context: Iterable[Mapping[str, object]] | None
    ) -> list[dict[str, object]]:
        entries = [dict(item) for item in self._context_buffer]
        if context:
            for entry in context:
                if isinstance(entry, Mapping):
                    entries.append(self._normalize_context(entry))
        return entries[-25:]

    def _normalize_context(self, entry: Mapping[str, object]) -> dict[str, object]:
        normalized: dict[str, object] = {}
        if "source" in entry:
            normalized["source"] = str(entry.get("source"))
        elif "source_daemon" in entry:
            normalized["source"] = str(entry.get("source_daemon"))
        if "event_type" in entry:
            normalized["event_type"] = str(entry.get("event_type"))
        if "priority" in entry:
            normalized["priority"] = str(entry.get("priority"))
        if "timestamp" in entry:
            normalized["timestamp"] = str(entry.get("timestamp"))
        payload = entry.get("payload")
        if isinstance(payload, Mapping):
            normalized["payload"] = _normalize_mapping(payload)
        elif payload is not None:
            normalized["payload"] = payload
        for key in ("reason", "detail", "summary"):
            if key in entry:
                normalized[key] = entry[key]
        return normalized

    def _prompt_stem(self, request: ArchitectRequest) -> str:
        stem = request.architect_id
        if request.iterations:
            stem = f"{stem}_iter{request.iterations:02d}"
        return stem

    def _prefix_from_stem(self, stem: str) -> str:
        token = _sanitize_token(stem)
        return f"expand_{token}_"

    def _generate_architect_id(self) -> str:
        return f"architect_{self._now().strftime('%Y%m%d_%H%M%S')}"

    # ------------------------------------------------------------------
    # Ledger & pulse helpers
    def _emit_ledger_event(self, event: Mapping[str, object]) -> None:
        payload = dict(event)
        payload.setdefault("ts", self._now().strftime("%Y-%m-%d %H:%M:%S"))
        payload.setdefault("source", "ArchitectDaemon")
        try:
            append_json(self.ledger_path, payload)
        except Exception:
            pass
        if self._ledger_sink:
            try:
                self._ledger_sink(dict(payload))
            except Exception:
                pass

    def _publish_pulse(self, event: Mapping[str, object]) -> None:
        try:
            self._pulse_publisher(dict(event))
        except Exception:
            pass

    def _normalize_pulse_event(
        self, event: Mapping[str, object]
    ) -> dict[str, object] | None:
        source = event.get("source_daemon")
        event_type = event.get("event_type")
        if not isinstance(source, str) or not isinstance(event_type, str):
            return None
        normalized = {
            "timestamp": str(event.get("timestamp", self._now().isoformat())),
            "source": source,
            "event_type": event_type,
        }
        priority = event.get("priority")
        if isinstance(priority, str):
            normalized["priority"] = priority
        payload = event.get("payload")
        if isinstance(payload, Mapping):
            normalized["payload"] = _normalize_mapping(payload)
        return normalized

    def _normalize_ledger_entry(
        self, entry: Mapping[str, object]
    ) -> dict[str, object] | None:
        event = entry.get("event")
        if not isinstance(event, str) or not event:
            return None
        normalized: dict[str, object] = {"event": event}
        for key in (
            "request_id",
            "patch_id",
            "reason",
            "files_changed",
            "codex_mode",
            "iterations",
            "failure_reason",
        ):
            if key in entry:
                normalized[key] = entry[key]
        return normalized

    def _create_branch_name(self, request: ArchitectRequest) -> str:
        timestamp = self._now().strftime("%Y%m%d_%H%M%S")
        token = _sanitize_token(request.architect_id)
        return f"architect/{token}_{timestamp}"
