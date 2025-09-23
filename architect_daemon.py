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

import random

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
ARCHITECT_JITTER = float(os.getenv("ARCHITECT_JITTER", str(30 * 60)))
ARCHITECT_COOLDOWN_PERIOD = float(
    os.getenv("ARCHITECT_COOLDOWN_PERIOD", str(24 * 60 * 60))
)
ARCHITECT_MAX_FAILURES = int(os.getenv("ARCHITECT_MAX_FAILURES", "3"))
ARCHITECT_REFLECTION_FREQUENCY = int(
    os.getenv("ARCHITECT_REFLECTION_FREQUENCY", "10")
)
ARCHITECT_ANOMALY_THRESHOLD = int(os.getenv("ARCHITECT_ANOMALY_THRESHOLD", "3"))
ARCHITECT_REFLECTION_DIR = Path(
    os.getenv("ARCHITECT_REFLECTION_DIR", "/glow/codex_reflections")
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
    cycle_number: int = 0
    cycle_type: str = "expansion"

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
        jitter: float | None = None,
        reflection_frequency: int | None = None,
        cooldown_period: float | None = None,
        max_failures: int | None = None,
        reflection_dir: Path | str | None = None,
        rng: random.Random | None = None,
        anomaly_threshold: int | None = None,
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
        self._base_interval = max(60.0, self._default_interval)
        self.interval = float(self._base_interval)
        self._default_max_iterations = int(
            max_iterations if max_iterations is not None else ARCHITECT_MAX_ITERATIONS
        )
        self.max_iterations = int(self._default_max_iterations)
        self._default_jitter = float(jitter if jitter is not None else ARCHITECT_JITTER)
        self.jitter = max(0.0, self._default_jitter)
        self._reflection_frequency = max(
            1,
            int(
                reflection_frequency
                if reflection_frequency is not None
                else ARCHITECT_REFLECTION_FREQUENCY
            ),
        )
        self._cooldown_period = max(
            0.0,
            float(
                cooldown_period
                if cooldown_period is not None
                else ARCHITECT_COOLDOWN_PERIOD
            ),
        )
        self._max_failures = max(
            1,
            int(max_failures if max_failures is not None else ARCHITECT_MAX_FAILURES),
        )
        self._anomaly_threshold = max(
            1,
            int(
                anomaly_threshold
                if anomaly_threshold is not None
                else ARCHITECT_ANOMALY_THRESHOLD
            ),
        )
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
        self._rng = rng or random.Random()

        self.request_dir.mkdir(parents=True, exist_ok=True)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._reflection_dir = (
            Path(reflection_dir) if reflection_dir else ARCHITECT_REFLECTION_DIR
        )
        self._reflection_dir.mkdir(parents=True, exist_ok=True)

        self._requests: dict[str, ArchitectRequest] = {}
        self._prefix_index: dict[str, ArchitectRequest] = {}
        self._context_buffer: Deque[dict[str, object]] = deque(maxlen=25)
        self._ledger_buffer: Deque[dict[str, object]] = deque(maxlen=25)
        self._subscription: pulse_bus.PulseSubscription | None = None
        self._activation_subscription: pulse_bus.PulseSubscription | None = None
        self._subscriptions_enabled = False
        self._cycle_history: Deque[dict[str, object]] = deque(maxlen=50)
        self._cycle_counter = 0
        self._next_cycle_due: float | None = None
        self._last_cycle_started: float | None = None
        self._failure_streak = 0
        self._cooldown_until = 0.0
        self._anomaly_streak = 0
        self._throttle_multiplier = 1.0
        self._throttled = False
        self._last_reflection_path: str | None = None
        self._last_reflection_summary: str | None = None

        self._session = self._load_session()
        self._hydrate_session_state()

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
        self._ensure_cycle_schedule(self._now().timestamp())
        if not self._activation_emitted or not was_active:
            self._emit_activation_event(reason)
            self._activation_emitted = True

    # ------------------------------------------------------------------
    # Session helpers
    def _load_session(self) -> dict[str, object]:
        if not self.session_file.exists():
            return {
                "runs": 0,
                "successes": 0,
                "failures": 0,
                "cycle_count": 0,
                "failure_streak": 0,
                "cooldown_until": 0.0,
                "next_cycle_due": 0.0,
                "last_cycle_started": 0.0,
                "cycle_history": [],
                "throttled": False,
                "throttle_multiplier": 1.0,
                "last_reflection_path": "",
                "last_reflection_summary": "",
                "anomaly_streak": 0,
            }
        try:
            data = json.loads(self.session_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {
                "runs": 0,
                "successes": 0,
                "failures": 0,
                "cycle_count": 0,
                "failure_streak": 0,
                "cooldown_until": 0.0,
                "next_cycle_due": 0.0,
                "last_cycle_started": 0.0,
                "cycle_history": [],
                "throttled": False,
                "throttle_multiplier": 1.0,
                "last_reflection_path": "",
                "last_reflection_summary": "",
                "anomaly_streak": 0,
            }
        if not isinstance(data, MutableMapping):
            return {
                "runs": 0,
                "successes": 0,
                "failures": 0,
                "cycle_count": 0,
                "failure_streak": 0,
                "cooldown_until": 0.0,
                "next_cycle_due": 0.0,
                "last_cycle_started": 0.0,
                "cycle_history": [],
                "throttled": False,
                "throttle_multiplier": 1.0,
                "last_reflection_path": "",
                "last_reflection_summary": "",
                "anomaly_streak": 0,
            }
        payload = dict(data)
        payload.setdefault("runs", 0)
        payload.setdefault("successes", 0)
        payload.setdefault("failures", 0)
        payload.setdefault("cycle_count", 0)
        payload.setdefault("failure_streak", 0)
        payload.setdefault("cooldown_until", 0.0)
        payload.setdefault("next_cycle_due", 0.0)
        payload.setdefault("last_cycle_started", 0.0)
        payload.setdefault("cycle_history", [])
        payload.setdefault("throttled", False)
        payload.setdefault("throttle_multiplier", 1.0)
        payload.setdefault("last_reflection_path", "")
        payload.setdefault("last_reflection_summary", "")
        payload.setdefault("anomaly_streak", 0)
        return payload

    def _hydrate_session_state(self) -> None:
        self._cycle_counter = int(self._session.get("cycle_count", 0))
        try:
            self._failure_streak = int(self._session.get("failure_streak", 0))
        except (TypeError, ValueError):
            self._failure_streak = 0
        cooldown_value = self._session.get("cooldown_until", 0.0)
        self._cooldown_until = self._coerce_float(cooldown_value, 0.0)
        next_cycle_value = self._session.get("next_cycle_due")
        next_cycle = self._coerce_float(next_cycle_value, 0.0)
        self._next_cycle_due = next_cycle if next_cycle > 0 else None
        last_cycle_value = self._session.get("last_cycle_started")
        last_cycle = self._coerce_float(last_cycle_value, 0.0)
        self._last_cycle_started = last_cycle if last_cycle > 0 else None
        history = self._session.get("cycle_history")
        if isinstance(history, list):
            for entry in history:
                if isinstance(entry, Mapping):
                    self._cycle_history.append(dict(entry))
        self._throttled = bool(self._session.get("throttled", False))
        try:
            self._throttle_multiplier = float(
                self._session.get("throttle_multiplier", 1.0)
            )
        except (TypeError, ValueError):
            self._throttle_multiplier = 1.0
        if self._throttle_multiplier <= 0:
            self._throttle_multiplier = 1.0
        path_value = self._session.get("last_reflection_path", "")
        if isinstance(path_value, str) and path_value.strip():
            self._last_reflection_path = path_value
        else:
            self._last_reflection_path = None
        summary_value = self._session.get("last_reflection_summary", "")
        if isinstance(summary_value, str) and summary_value.strip():
            self._last_reflection_summary = summary_value
        else:
            self._last_reflection_summary = None
        try:
            self._anomaly_streak = int(self._session.get("anomaly_streak", 0))
        except (TypeError, ValueError):
            self._anomaly_streak = 0
        self._update_interval()

    def _save_session(self) -> None:
        self._session["cycle_count"] = int(self._cycle_counter)
        self._session["failure_streak"] = int(self._failure_streak)
        self._session["cooldown_until"] = float(self._cooldown_until or 0.0)
        self._session["next_cycle_due"] = float(self._next_cycle_due or 0.0)
        self._session["last_cycle_started"] = float(self._last_cycle_started or 0.0)
        self._session["cycle_history"] = [dict(entry) for entry in self._cycle_history]
        self._session["throttled"] = bool(self._throttled)
        self._session["throttle_multiplier"] = float(self._throttle_multiplier)
        self._session["last_reflection_path"] = self._last_reflection_path or ""
        self._session["last_reflection_summary"] = self._last_reflection_summary or ""
        self._session["anomaly_streak"] = int(self._anomaly_streak)
        self._session["autonomy_enabled"] = bool(self._autonomy_enabled)
        self.session_file.write_text(
            json.dumps(self._session, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _is_in_cooldown(self, timestamp: float | None = None) -> bool:
        if self._cooldown_until <= 0:
            return False
        target = timestamp if timestamp is not None else self._now().timestamp()
        return target < self._cooldown_until

    def _ensure_cycle_schedule(self, timestamp: float) -> None:
        if self._next_cycle_due is None or self._next_cycle_due <= 0:
            self._schedule_next_cycle(timestamp)

    def _schedule_next_cycle(self, base_timestamp: float | None = None) -> None:
        now_ts = base_timestamp if base_timestamp is not None else self._now().timestamp()
        start_ts = now_ts
        if self._is_in_cooldown(now_ts):
            start_ts = max(now_ts, self._cooldown_until)
        jitter_offset = 0.0
        if self.jitter > 0:
            jitter_offset = self._rng.uniform(-self.jitter, self.jitter)
        interval = max(60.0, self.interval + jitter_offset)
        due = start_ts + interval
        if self._is_in_cooldown(now_ts):
            due = max(due, self._cooldown_until)
        self._next_cycle_due = due
        self._save_session()

    def _begin_cycle(
        self, *, trigger: str, timestamp: datetime | None = None
    ) -> ArchitectRequest | None:
        if self._has_active_request():
            return None
        now_dt = timestamp or self._now()
        now_ts = now_dt.timestamp()
        cycle_number = self._cycle_counter + 1
        is_reflection = cycle_number % self._reflection_frequency == 0
        if is_reflection:
            request = self._draft_reflection_cycle(cycle_number)
        else:
            request = self._draft_cycle_request(cycle_number)
        if request is None:
            return None
        request.cycle_number = cycle_number
        request.cycle_type = "reflection" if is_reflection else "expansion"
        self._cycle_counter = cycle_number
        self._last_cycle_started = now_ts
        self._schedule_next_cycle(now_ts)
        self._record_cycle_start(request, trigger)
        self._save_session()
        return request

    def _record_cycle_start(self, request: ArchitectRequest, trigger: str) -> None:
        entry: dict[str, object] = {
            "cycle": request.cycle_number,
            "architect_id": request.architect_id,
            "type": request.cycle_type,
            "trigger": trigger,
            "started_at": request.created_at.isoformat(),
            "throttled": self._throttled,
            "mode": request.mode,
            "status": "reflection_pending"
            if request.cycle_type == "reflection"
            else "requested",
        }
        if request.prompt_path is not None:
            entry["prompt"] = request.prompt_path.as_posix().lstrip("/")
        self._cycle_history.append(entry)
        self._emit_cycle_start_event(request, trigger)

    def _emit_cycle_start_event(self, request: ArchitectRequest, trigger: str) -> None:
        next_cycle_iso = (
            datetime.fromtimestamp(self._next_cycle_due, tz=timezone.utc).isoformat()
            if self._next_cycle_due
            else ""
        )
        ledger_payload = {
            "event": "architect_cycle_start",
            "cycle": request.cycle_number,
            "cycle_type": request.cycle_type,
            "architect_id": request.architect_id,
            "trigger": trigger,
            "throttled": self._throttled,
            "next_cycle_due": next_cycle_iso,
        }
        self._emit_ledger_event(ledger_payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_cycle_start",
                "priority": "info",
                "payload": {
                    "cycle": request.cycle_number,
                    "cycle_type": request.cycle_type,
                    "trigger": trigger,
                    "throttled": self._throttled,
                    "next_cycle_due": next_cycle_iso,
                },
            }
        )

    def _update_cycle_entry(self, architect_id: str, **updates: object) -> None:
        for entry in reversed(self._cycle_history):
            if entry.get("architect_id") == architect_id:
                entry.update({key: value for key, value in updates.items() if value is not None})
                break

    def _recent_cycle_history(self, limit: int = 10) -> list[dict[str, object]]:
        expansions = [
            dict(item)
            for item in self._cycle_history
            if item.get("type") != "reflection"
        ]
        return expansions[-limit:]

    def _draft_cycle_request(self, cycle_number: int) -> ArchitectRequest:
        description = f"Scheduled Codex cycle {cycle_number:04d}"
        details = {
            "description": description,
            "cycle_number": cycle_number,
            "trigger": "scheduled",
            "throttled": self._throttled,
        }
        request = self._create_request("expand", description, None, details)
        return request

    def _draft_reflection_cycle(self, cycle_number: int) -> ArchitectRequest:
        topic = f"cycle_{cycle_number:04d}_reflection"
        window_start = max(1, cycle_number - 9)
        history = self._recent_cycle_history(limit=10)
        details = {
            "topic": topic,
            "cycle_number": cycle_number,
            "window_start": window_start,
            "window_end": cycle_number,
            "cycle_history": history,
        }
        request = self._create_request("reflect", topic, None, details)
        self._last_reflection_summary = None
        prompt_ref = (
            request.prompt_path.as_posix().lstrip("/")
            if request.prompt_path
            else ""
        )
        self._emit_ledger_event(
            {
                "event": "architect_reflection",
                "cycle": cycle_number,
                "prompt": prompt_ref,
            }
        )
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_reflection",
                "priority": "info",
                "payload": {"cycle": cycle_number, "prompt": prompt_ref},
            }
        )
        return request

    def _enter_cooldown(self, reason: str, *, timestamp: float | None = None) -> None:
        now_ts = timestamp if timestamp is not None else self._now().timestamp()
        self._cooldown_until = now_ts + max(0.0, self._cooldown_period)
        cooldown_iso = datetime.fromtimestamp(
            self._cooldown_until, tz=timezone.utc
        ).isoformat()
        payload = {
            "event": "architect_cooldown",
            "reason": reason,
            "cooldown_until": cooldown_iso,
            "failure_streak": self._failure_streak,
        }
        self._emit_ledger_event(payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_cooldown",
                "priority": "warning",
                "payload": {
                    "reason": reason,
                    "cooldown_until": cooldown_iso,
                    "failure_streak": self._failure_streak,
                },
            }
        )
        self._schedule_next_cycle(self._cooldown_until)

    def _exit_cooldown(self, *, triggered_by: str, timestamp: float | None = None) -> None:
        if self._cooldown_until <= 0:
            self._failure_streak = 0
            return
        now_ts = timestamp if timestamp is not None else self._now().timestamp()
        self._cooldown_until = 0.0
        self._failure_streak = 0
        payload = {
            "event": "architect_cooldown_complete",
            "trigger": triggered_by,
        }
        self._emit_ledger_event(payload)
        self._publish_pulse(
            {
                "timestamp": datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_cooldown_complete",
                "priority": "info",
                "payload": {"trigger": triggered_by},
            }
        )
        self._schedule_next_cycle(now_ts)

    def _update_cooldown_state(self, timestamp: float) -> None:
        if self._cooldown_until > 0 and timestamp >= self._cooldown_until:
            self._exit_cooldown(triggered_by="elapsed", timestamp=timestamp)

    def _engage_throttle(self, payload: Mapping[str, object] | None) -> None:
        self._throttled = True
        self._throttle_multiplier = max(self._throttle_multiplier, 2.0)
        self._anomaly_streak = max(self._anomaly_streak, self._anomaly_threshold)
        self._update_interval()
        details = {
            "event": "architect_throttled",
            "multiplier": self._throttle_multiplier,
            "anomaly_streak": self._anomaly_streak,
        }
        if payload:
            details["payload"] = dict(payload)
        self._emit_ledger_event(details)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_throttled",
                "priority": "warning",
                "payload": {
                    "multiplier": self._throttle_multiplier,
                    "anomaly_streak": self._anomaly_streak,
                },
            }
        )
        self._schedule_next_cycle(self._now().timestamp())

    def _release_throttle(self, *, reason: str) -> None:
        if not self._throttled:
            self._anomaly_streak = 0
            return
        self._throttled = False
        self._throttle_multiplier = 1.0
        self._anomaly_streak = 0
        self._update_interval()
        self._emit_ledger_event(
            {
                "event": "architect_throttle_cleared",
                "reason": reason,
            }
        )
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_throttle_cleared",
                "priority": "info",
                "payload": {"reason": reason},
            }
        )
        self._schedule_next_cycle(self._now().timestamp())

    def reset_cooldown(self, *, actor: str | None = None) -> None:
        actor_name = actor or "unknown"
        self._emit_ledger_event(
            {"event": "architect_cooldown_reset", "actor": actor_name}
        )
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_cooldown_reset",
                "priority": "info",
                "payload": {"actor": actor_name},
            }
        )
        self._exit_cooldown(triggered_by="manual_reset")
        self._save_session()

    def _handle_manual_cycle_request(
        self, source: str | None, event: Mapping[str, object]
    ) -> None:
        if not self._active:
            return
        now = self._now()
        if self._is_in_cooldown(now.timestamp()):
            self._emit_ledger_event(
                {
                    "event": "architect_run_now_blocked",
                    "reason": "cooldown_active",
                    "actor": source or "unknown",
                }
            )
            self._publish_pulse(
                {
                    "timestamp": now.isoformat(),
                    "source_daemon": "ArchitectDaemon",
                    "event_type": "architect_run_now_blocked",
                    "priority": "warning",
                    "payload": {"reason": "cooldown_active"},
                }
            )
            return
        if self._has_active_request():
            self._emit_ledger_event(
                {
                    "event": "architect_run_now_skipped",
                    "reason": "request_active",
                    "actor": source or "unknown",
                }
            )
            return
        request = self._begin_cycle(trigger="manual", timestamp=now)
        if request is None:
            return
        self._emit_ledger_event(
            {
                "event": "architect_run_now_triggered",
                "cycle": request.cycle_number,
                "actor": source or "unknown",
            }
        )
        self._publish_pulse(
            {
                "timestamp": now.isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_run_now_triggered",
                "priority": "info",
                "payload": {"cycle": request.cycle_number},
            }
        )

    def _handle_monitor_alert(self, event: Mapping[str, object]) -> None:
        self._anomaly_streak = min(self._anomaly_streak + 1, self._anomaly_threshold * 2)
        payload = event.get("payload") if isinstance(event, Mapping) else None
        if self._anomaly_streak >= self._anomaly_threshold and not self._throttled:
            normalized_payload = payload if isinstance(payload, Mapping) else None
            self._engage_throttle(normalized_payload)

    def _handle_monitor_summary(self, event: Mapping[str, object]) -> None:
        payload = event.get("payload") if isinstance(event, Mapping) else None
        anomalies: Sequence[object] | None = None
        if isinstance(payload, Mapping):
            anomalies_value = payload.get("anomalies")
            if isinstance(anomalies_value, Sequence):
                anomalies = anomalies_value
        if not anomalies:
            self._anomaly_streak = 0
            self._release_throttle(reason="monitor_summary")
        else:
            self._anomaly_streak = min(len(anomalies), self._anomaly_threshold)

    def _record_success(self) -> None:
        self._session["runs"] = int(self._session.get("runs", 0)) + 1
        self._session["successes"] = int(self._session.get("successes", 0)) + 1
        self._failure_streak = 0
        self._save_session()

    def _record_failure(self) -> None:
        self._session["runs"] = int(self._session.get("runs", 0)) + 1
        self._session["failures"] = int(self._session.get("failures", 0)) + 1
        self._failure_streak += 1
        if self._failure_streak >= self._max_failures:
            self._enter_cooldown("failure_streak")
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
        raw_interval = payload.get("architect_interval")
        if raw_interval is None:
            raw_interval = payload.get("codex_interval", self._default_interval)
        architect_interval = self._coerce_float(raw_interval, self._default_interval)
        codex_interval = self._coerce_float(
            payload.get("codex_interval"), architect_interval
        )
        architect_jitter = self._coerce_float(
            payload.get("architect_jitter"), self._default_jitter
        )
        max_iterations = self._coerce_int(
            payload.get("codex_max_iterations"), self._default_max_iterations
        )
        peer_name = str(payload.get("federation_peer_name") or "").strip()
        peers_raw = payload.get("federation_peers") or payload.get("federation_addresses")
        peers = self._normalize_peers(peers_raw)
        autonomy = self._coerce_bool(payload.get("architect_autonomy", False))
        return {
            "codex_mode": mode,
            "codex_interval": codex_interval,
            "architect_interval": architect_interval,
            "architect_jitter": architect_jitter,
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

    def _update_interval(self) -> None:
        base = max(60.0, float(getattr(self, "_base_interval", self.interval)))
        multiplier = float(self._throttle_multiplier or 1.0)
        if multiplier <= 0:
            multiplier = 1.0
        self.interval = base * multiplier

    def _apply_config(self, snapshot: Mapping[str, object]) -> None:
        self._codex_mode = str(snapshot.get("codex_mode", "observe"))
        base_interval = float(
            snapshot.get("architect_interval", snapshot.get("codex_interval", self._default_interval))
        )
        self._base_interval = max(60.0, base_interval)
        self.jitter = max(
            0.0,
            float(snapshot.get("architect_jitter", self._default_jitter)),
        )
        self._update_interval()
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
            "codex_interval": self._base_interval,
            "architect_interval": self._base_interval,
            "architect_effective_interval": self.interval,
            "architect_jitter": self.jitter,
            "codex_max_iterations": self.max_iterations,
            "federation_peer_name": self._federation_peer_name,
            "federation_peers": list(self._federation_peers),
            "architect_autonomy": self._autonomy_enabled,
            "architect_throttled": self._throttled,
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
        current_dt = now or self._now()
        timestamp = current_dt.timestamp()
        self._update_cooldown_state(timestamp)
        if self.interval <= 0:
            return None
        if self._has_active_request():
            return None
        if self._is_in_cooldown(timestamp):
            return None
        self._ensure_cycle_schedule(timestamp)
        if self._next_cycle_due is None:
            return None
        if timestamp + 1e-6 < self._next_cycle_due:
            return None
        return self._begin_cycle(trigger="scheduled", timestamp=current_dt)

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
        if source == "MonitoringDaemon":
            if event_type == "monitor_alert":
                self._handle_monitor_alert(normalized)
                self.request_repair("monitor_alert")
            elif event_type == "monitor_summary":
                self._handle_monitor_summary(normalized)
            return
        if event_type == "architect_run_now":
            self._handle_manual_cycle_request(str(source) if isinstance(source, str) else None, normalized)
            return
        if event_type == "architect_reset_cooldown":
            self.reset_cooldown(actor=str(source) if isinstance(source, str) else None)
            return
        if source == "DriverManager" and event_type == "driver_failure":
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
        target_dir = self._reflection_dir if request.mode == "reflect" else self.request_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{stem}.txt"
        counter = 0
        while path.exists():
            counter += 1
            path = target_dir / f"{stem}_{counter}.txt"
        prompt = self._build_prompt(request)
        path.write_text(prompt, encoding="utf-8")
        metadata = request.metadata()
        prompt_path = path.as_posix().lstrip("/")
        metadata["prompt_path"] = prompt_path
        metadata["context"] = request.context
        metadata["ledger_snapshot"] = list(self._ledger_buffer)
        if request.cycle_number:
            metadata["cycle_number"] = request.cycle_number
            metadata["cycle_type"] = request.cycle_type
        if request.mode == "reflect":
            metadata["cycle_history"] = request.details.get("cycle_history", [])
        path.with_suffix(".json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
        )
        prefix = self._prefix_from_stem(path.stem)
        request.codex_prefix = prefix
        request.prompt_path = path
        self._prefix_index[prefix] = request
        if request.mode == "reflect":
            self._last_reflection_path = prompt_path

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
        detail_items = dict(request.details)
        history = detail_items.pop("cycle_history", None)
        if detail_items:
            lines.append("Request Details:")
            for key, value in sorted(detail_items.items()):
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
            lines.append("Reflection Task:")
            lines.append(
                "Review the last 10 cycles of Codex expansions, summarize outcomes, suggest next priorities, and identify regressions. Respond in JSON."
            )
            lines.append(
                "Return a JSON object with keys: summary, next_priorities, regressions. Do not propose or apply code patches."
            )
            if isinstance(history, list) and history:
                lines.append("")
                lines.append("Recent Cycle Outcomes:")
                for entry in history:
                    if not isinstance(entry, Mapping):
                        continue
                    cycle = entry.get("cycle")
                    status = entry.get("status", "unknown")
                    mode = entry.get("mode", "")
                    summary_parts = [f"Cycle {cycle}", f"status={status}"]
                    if mode:
                        summary_parts.append(f"mode={mode}")
                    trigger = entry.get("trigger")
                    if trigger:
                        summary_parts.append(f"trigger={trigger}")
                    prompt_ref = entry.get("prompt")
                    if prompt_ref:
                        summary_parts.append(f"prompt={prompt_ref}")
                    lines.append("- " + ", ".join(str(part) for part in summary_parts if part))
                lines.append("")
        else:
            lines.append("Objective: Respond to the described situation safely and thoroughly.")
        lines.append("")
        if request.mode == "reflect":
            lines.append("Focus on analysis only; do not propose code patches or file changes.")
        else:
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
        completed_at = self._now().isoformat()
        self._update_cycle_entry(
            request.architect_id,
            status="completed",
            result=status,
            completed_at=completed_at,
        )
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
            self._update_cycle_entry(
                request.architect_id,
                status="failed",
                error=reason,
                failed_at=self._now().isoformat(),
            )
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
        self._update_cycle_entry(
            request.architect_id,
            status="retrying",
            error=reason,
            retry_iteration=request.iterations,
        )
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
        self._update_cycle_entry(
            request.architect_id,
            status="awaiting_veil",
            patch_id=payload["request_id"],
        )
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


def load_architect_status(
    session_path: Path | str | None = None,
) -> dict[str, object]:
    """Load the architect session ledger and return a normalized status snapshot."""

    path = Path(session_path) if session_path else ARCHITECT_SESSION_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, MutableMapping):
        return {}
    status = dict(data)

    def _to_float(value: object) -> float:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0

    now_ts = _utcnow().timestamp()
    cooldown_until = _to_float(status.get("cooldown_until"))
    next_cycle_due = _to_float(status.get("next_cycle_due"))
    status["cooldown_active"] = cooldown_until > now_ts
    status["next_cycle_iso"] = (
        datetime.fromtimestamp(next_cycle_due, tz=timezone.utc).isoformat()
        if next_cycle_due > 0
        else ""
    )
    status["cooldown_until_iso"] = (
        datetime.fromtimestamp(cooldown_until, tz=timezone.utc).isoformat()
        if cooldown_until > 0
        else ""
    )
    return status
