"""ArchitectDaemon — autonomous Codex meta-orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import difflib
import itertools
import json
import os
import re
import subprocess
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Iterable, Mapping, MutableMapping, Sequence

import random
from uuid import uuid4

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
ARCHITECT_REFLECTION_INTERVAL = int(
    os.getenv(
        "ARCHITECT_REFLECTION_INTERVAL",
        os.getenv("ARCHITECT_REFLECTION_FREQUENCY", "10"),
    )
)
ARCHITECT_ANOMALY_THRESHOLD = int(os.getenv("ARCHITECT_ANOMALY_THRESHOLD", "3"))
ARCHITECT_REFLECTION_DIR = Path(
    os.getenv("ARCHITECT_REFLECTION_DIR", "/glow/codex_reflections")
)
ARCHITECT_FEDERATE_REFLECTIONS = (
    os.getenv("ARCHITECT_FEDERATE_REFLECTIONS", "0").strip().lower()
    not in {"0", "false", "no", "off"}
)
ARCHITECT_FEDERATE_PRIORITIES = (
    os.getenv("ARCHITECT_FEDERATE_PRIORITIES", "0").strip().lower()
    not in {"0", "false", "no", "off"}
)
ARCHITECT_PRIORITY_BACKLOG_PATH = Path(
    os.getenv(
        "ARCHITECT_PRIORITY_BACKLOG",
        os.path.join(str(ARCHITECT_REFLECTION_DIR), "priorities.json"),
    )
)
ARCHITECT_CYCLE_DIR = Path(
    os.getenv("ARCHITECT_CYCLE_DIR", "/glow/codex_cycles")
)
ARCHITECT_TRAJECTORY_DIR = Path(
    os.getenv("ARCHITECT_TRAJECTORY_DIR", "/glow/codex_trajectories")
)
ARCHITECT_TRAJECTORY_INTERVAL = int(
    os.getenv("ARCHITECT_TRAJECTORY_INTERVAL", "10")
)
ARCHITECT_SUCCESS_RATE_THRESHOLD = float(
    os.getenv("ARCHITECT_SUCCESS_RATE_THRESHOLD", "0.7")
)
ARCHITECT_FAILURE_STREAK_THRESHOLD = int(
    os.getenv("ARCHITECT_FAILURE_STREAK_THRESHOLD", "3")
)
ARCHITECT_CONFLICT_RATE_THRESHOLD = float(
    os.getenv("ARCHITECT_CONFLICT_RATE_THRESHOLD", "0.3")
)

_PRIORITY_ACTIVE_STATUSES = {"pending", "in_progress", "done", "discarded"}
_PRIORITY_HISTORY_STATUSES = {"done", "discarded"}

_DEFAULT_CI_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("python", "-m", "scripts.run_tests", "-q"),
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


_CONFLICT_SIMILARITY_THRESHOLD = 0.82
_CONFLICT_STATUSES = {"pending", "accepted", "rejected", "separate"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_token(text: str) -> str:
    token = text.strip() or "request"
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in token)


_PRIORITY_CANONICAL_PATTERN = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", text.strip().lower())
    token = token.strip("_")
    return token or "event"


def _canonicalize_priority_text(text: str) -> str:
    normalized = _PRIORITY_CANONICAL_PATTERN.sub("", text.strip().lower())
    return normalized or text.strip().lower()


def _normalize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    data: dict[str, object] = {}
    for key, val in value.items():
        if isinstance(val, Mapping):
            data[str(key)] = _normalize_mapping(val)
        else:
            data[str(key)] = val
    return data


def _text_similarity(left: str, right: str) -> float:
    text_a = left.strip().lower()
    text_b = right.strip().lower()
    if not text_a or not text_b:
        return 0.0
    if text_a == text_b:
        return 1.0
    return float(difflib.SequenceMatcher(None, text_a, text_b).ratio())


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
        reflection_interval: int | None = None,
        reflection_frequency: int | None = None,
        cooldown_period: float | None = None,
        max_failures: int | None = None,
        reflection_dir: Path | str | None = None,
        priority_path: Path | str | None = None,
        cycle_dir: Path | str | None = None,
        trajectory_interval: int | None = None,
        trajectory_dir: Path | str | None = None,
        rng: random.Random | None = None,
        anomaly_threshold: int | None = None,
        success_rate_threshold: float | None = None,
        failure_streak_threshold: int | None = None,
        conflict_rate_threshold: float | None = None,
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
        reflection_interval = (
            reflection_interval
            if reflection_interval is not None
            else reflection_frequency
        )
        if reflection_interval is None:
            reflection_interval = ARCHITECT_REFLECTION_INTERVAL
        self._reflection_interval = max(1, int(reflection_interval))
        self._default_reflection_interval = int(self._reflection_interval)
        self._cooldown_period = max(
            0.0,
            float(
                cooldown_period
                if cooldown_period is not None
                else ARCHITECT_COOLDOWN_PERIOD
            ),
        )
        self._default_cooldown_period = float(self._cooldown_period)
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
        self._success_rate_threshold = max(
            0.0,
            float(
                success_rate_threshold
                if success_rate_threshold is not None
                else ARCHITECT_SUCCESS_RATE_THRESHOLD
            ),
        )
        self._failure_streak_threshold = max(
            1,
            int(
                failure_streak_threshold
                if failure_streak_threshold is not None
                else ARCHITECT_FAILURE_STREAK_THRESHOLD
            ),
        )
        self._conflict_rate_threshold = max(
            0.0,
            float(
                conflict_rate_threshold
                if conflict_rate_threshold is not None
                else ARCHITECT_CONFLICT_RATE_THRESHOLD
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

        self._priority_path = (
            Path(priority_path)
            if priority_path is not None
            else ARCHITECT_PRIORITY_BACKLOG_PATH
        )
        if not self._priority_path.is_absolute():
            self._priority_path = self._reflection_dir / self._priority_path
        self._priority_path.parent.mkdir(parents=True, exist_ok=True)
        self._peer_backlog_dir = self._reflection_dir / "peer_backlogs"
        self._peer_backlog_dir.mkdir(parents=True, exist_ok=True)
        (
            self._priority_active,
            self._priority_history,
            self._priority_updated,
            priority_dirty,
            federated_entries,
            conflict_entries,
        ) = self._load_priority_backlog()
        self._priority_index = {
            entry["id"]: entry for entry in self._priority_active if "id" in entry
        }
        self._federated_priorities: dict[str, dict[str, object]] = {}
        self._federated_index: dict[str, dict[str, object]] = {}
        self._peer_backlog_entries: dict[str, dict[str, dict[str, object]]] = {}
        self._federated_conflicts_reported: set[str] = set()
        self._conflicts: dict[str, dict[str, object]] = {}
        self._conflict_lookup: dict[tuple[str, ...], str] = {}
        self._conflict_index: dict[str, set[str]] = {}
        self._hydrate_federated_state(federated_entries)
        self._hydrate_conflicts(conflict_entries)
        self._local_pending_snapshot = self._pending_snapshot()
        if priority_dirty:
            self._save_priority_backlog(share=False)

        self._conflict_resolution_dir = self._reflection_dir / "resolutions"
        self._conflict_resolution_dir.mkdir(parents=True, exist_ok=True)

        self._cycle_dir = Path(cycle_dir) if cycle_dir else ARCHITECT_CYCLE_DIR
        self._cycle_dir.mkdir(parents=True, exist_ok=True)
        self._trajectory_dir = (
            Path(trajectory_dir) if trajectory_dir else ARCHITECT_TRAJECTORY_DIR
        )
        self._trajectory_dir.mkdir(parents=True, exist_ok=True)
        interval_value = (
            trajectory_interval
            if trajectory_interval is not None
            else ARCHITECT_TRAJECTORY_INTERVAL
        )
        self._trajectory_interval = max(1, int(interval_value))

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
        self._last_trajectory_path: str | None = None
        self._last_trajectory_id: str | None = None
        self._last_trajectory_notes: str | None = None
        self._federate_reflections = bool(ARCHITECT_FEDERATE_REFLECTIONS)
        self._federate_priorities = bool(ARCHITECT_FEDERATE_PRIORITIES)

        self._steering_overrides: dict[str, object] = {
            "reflection_interval": None,
            "cooldown_period": None,
            "conflict_priority": False,
        }
        self._low_confidence_priorities: set[str] = set()
        self._priority_confidence: dict[str, str] = {}
        self._trajectory_adjustment_reason: str = ""
        self._trajectory_adjustment_settings: dict[str, object] = {}
        self._conflict_priority_escalated = False

        self._cycle_state: dict[str, dict[str, object]] = {}
        self._pending_cycle_anomalies: list[str] = []
        self._pending_cycle_conflicts: set[str] = set()
        self._pending_cycle_cooldown = False
        self._active_cycle_id: str | None = None

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
                "last_trajectory_path": "",
                "last_trajectory_id": "",
                "last_trajectory_notes": "",
                "trajectory_interval": ARCHITECT_TRAJECTORY_INTERVAL,
                "trajectory_adjustment_reason": "",
                "trajectory_adjustment_settings": {},
                "trajectory_overrides": {},
                "low_confidence_priorities": [],
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
                "last_trajectory_path": "",
                "last_trajectory_id": "",
                "last_trajectory_notes": "",
                "trajectory_interval": ARCHITECT_TRAJECTORY_INTERVAL,
                "trajectory_adjustment_reason": "",
                "trajectory_adjustment_settings": {},
                "trajectory_overrides": {},
                "low_confidence_priorities": [],
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
                "last_trajectory_path": "",
                "last_trajectory_id": "",
                "last_trajectory_notes": "",
                "trajectory_interval": ARCHITECT_TRAJECTORY_INTERVAL,
                "trajectory_adjustment_reason": "",
                "trajectory_adjustment_settings": {},
                "trajectory_overrides": {},
                "low_confidence_priorities": [],
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
        payload.setdefault("last_trajectory_path", "")
        payload.setdefault("last_trajectory_id", "")
        payload.setdefault("last_trajectory_notes", "")
        payload.setdefault("trajectory_interval", ARCHITECT_TRAJECTORY_INTERVAL)
        payload.setdefault("trajectory_adjustment_reason", "")
        payload.setdefault("trajectory_adjustment_settings", {})
        payload.setdefault("trajectory_overrides", {})
        payload.setdefault("low_confidence_priorities", [])
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
        trajectory_path = self._session.get("last_trajectory_path", "")
        if isinstance(trajectory_path, str) and trajectory_path.strip():
            self._last_trajectory_path = trajectory_path
        else:
            self._last_trajectory_path = None
        trajectory_id = self._session.get("last_trajectory_id", "")
        if isinstance(trajectory_id, str) and trajectory_id.strip():
            self._last_trajectory_id = trajectory_id
        else:
            self._last_trajectory_id = None
        trajectory_notes = self._session.get("last_trajectory_notes", "")
        if isinstance(trajectory_notes, str) and trajectory_notes.strip():
            self._last_trajectory_notes = trajectory_notes
        else:
            self._last_trajectory_notes = None
        try:
            interval_value = int(self._session.get("trajectory_interval", self._trajectory_interval))
            if interval_value > 0:
                self._trajectory_interval = interval_value
        except (TypeError, ValueError):
            pass
        reason_value = self._session.get("trajectory_adjustment_reason", "")
        if isinstance(reason_value, str):
            self._trajectory_adjustment_reason = reason_value.strip()
        else:
            self._trajectory_adjustment_reason = ""
        settings_value = self._session.get("trajectory_adjustment_settings", {})
        if isinstance(settings_value, Mapping):
            self._trajectory_adjustment_settings = dict(settings_value)
        else:
            self._trajectory_adjustment_settings = {}
        overrides_value = self._session.get("trajectory_overrides", {})
        normalized_overrides: dict[str, object] = {
            "reflection_interval": None,
            "cooldown_period": None,
            "conflict_priority": False,
        }
        if isinstance(overrides_value, Mapping):
            reflection_override = overrides_value.get("reflection_interval")
            if isinstance(reflection_override, int) and reflection_override > 0:
                normalized_overrides["reflection_interval"] = int(reflection_override)
            cooldown_override = overrides_value.get("cooldown_period")
            if isinstance(cooldown_override, (int, float)) and float(cooldown_override) > 0:
                normalized_overrides["cooldown_period"] = float(cooldown_override)
            if overrides_value.get("conflict_priority"):
                normalized_overrides["conflict_priority"] = True
        self._steering_overrides = normalized_overrides
        low_confidence_value = self._session.get("low_confidence_priorities", [])
        if isinstance(low_confidence_value, Sequence) and not isinstance(low_confidence_value, (str, bytes)):
            self._low_confidence_priorities = {
                _canonicalize_priority_text(str(item))
                for item in low_confidence_value
                if str(item).strip()
            }
        else:
            self._low_confidence_priorities = set()
        self._apply_steering_overrides()
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
        self._session["last_trajectory_path"] = self._last_trajectory_path or ""
        self._session["last_trajectory_id"] = self._last_trajectory_id or ""
        self._session["last_trajectory_notes"] = self._last_trajectory_notes or ""
        self._session["trajectory_interval"] = int(self._trajectory_interval)
        self._session["trajectory_adjustment_reason"] = self._trajectory_adjustment_reason
        self._session["trajectory_adjustment_settings"] = dict(
            self._trajectory_adjustment_settings
        )
        self._session["trajectory_overrides"] = dict(self._steering_overrides)
        self._session["low_confidence_priorities"] = sorted(self._low_confidence_priorities)
        self.session_file.write_text(
            json.dumps(self._session, indent=2, sort_keys=True), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Priority backlog management
    def _load_priority_backlog(
        self,
    ) -> tuple[
        list[dict[str, object]],
        list[dict[str, object]],
        str,
        bool,
        list[dict[str, object]],
        list[dict[str, object]],
    ]:
        timestamp = self._now().isoformat()
        if not self._priority_path.exists():
            return [], [], timestamp, True, [], []
        try:
            raw = json.loads(self._priority_path.read_text(encoding="utf-8"))
        except Exception:
            return [], [], timestamp, True, [], []
        if not isinstance(raw, Mapping):
            return [], [], timestamp, True, [], []

        updated = str(raw.get("updated", timestamp))
        dirty = False

        active_list: list[dict[str, object]] = []
        raw_active = raw.get("active")
        if isinstance(raw_active, Sequence):
            for item in raw_active:
                if not isinstance(item, Mapping):
                    continue
                priority_id = str(item.get("id", "")).strip()
                text = str(item.get("text", "")).strip()
                status = str(item.get("status", "pending")).strip().lower()
                if not priority_id or not text:
                    continue
                if status not in _PRIORITY_ACTIVE_STATUSES:
                    status = "pending"
                    dirty = True
                if status == "in_progress":
                    status = "pending"
                    dirty = True
                entry: dict[str, object] = {"id": priority_id, "text": text, "status": status}
                confidence_value = str(item.get("confidence", "")).strip()
                if confidence_value:
                    entry["confidence"] = confidence_value
                active_list.append(entry)

        history_list: list[dict[str, str]] = []
        raw_history = raw.get("history")
        if isinstance(raw_history, Sequence):
            seen: set[str] = set()
            for item in raw_history:
                if not isinstance(item, Mapping):
                    continue
                priority_id = str(item.get("id", "")).strip()
                text = str(item.get("text", "")).strip()
                status = str(item.get("status", "done")).strip().lower()
                completed_at = str(item.get("completed_at", "")).strip()
                if (
                    not priority_id
                    or not text
                    or status not in _PRIORITY_HISTORY_STATUSES
                ):
                    continue
                if priority_id in seen:
                    continue
                entry: dict[str, str] = {
                    "id": priority_id,
                    "text": text,
                    "status": status,
                }
                if completed_at:
                    entry["completed_at"] = completed_at
                history_list.append(entry)
                seen.add(priority_id)

        federated_entries: list[dict[str, object]] = []
        raw_federated = raw.get("federated")
        if isinstance(raw_federated, Sequence):
            for item in raw_federated:
                if not isinstance(item, Mapping):
                    continue
                entry_id = str(item.get("id", "")).strip()
                text = str(item.get("text", "")).strip()
                if not entry_id or not text:
                    continue
                canonical = str(
                    item.get("canonical", _canonicalize_priority_text(text))
                ).strip()
                origin_peers_raw = item.get("origin_peers")
                origin_peers: list[str] = []
                if isinstance(origin_peers_raw, Sequence):
                    for peer in origin_peers_raw:
                        peer_name = str(peer).strip()
                        if peer_name:
                            origin_peers.append(peer_name)
                variants: list[dict[str, object]] = []
                raw_variants = item.get("variants")
                if isinstance(raw_variants, Sequence):
                    for variant in raw_variants:
                        if not isinstance(variant, Mapping):
                            continue
                        peer_name = str(variant.get("peer", "")).strip()
                        variant_text = str(variant.get("text", "")).strip()
                        if not peer_name or not variant_text:
                            continue
                        variant_entry: dict[str, object] = {
                            "peer": peer_name,
                            "text": variant_text,
                        }
                        received_at = variant.get("received_at")
                        if isinstance(received_at, str) and received_at.strip():
                            variant_entry["received_at"] = received_at.strip()
                        verified = variant.get("signature_verified")
                        if isinstance(verified, bool):
                            variant_entry["signature_verified"] = verified
                        elif isinstance(verified, (int, float)):
                            variant_entry["signature_verified"] = bool(verified)
                        variants.append(variant_entry)
                entry: dict[str, object] = {
                    "id": entry_id,
                    "text": text,
                    "canonical": canonical or _canonicalize_priority_text(text),
                    "origin_peers": sorted({peer for peer in origin_peers}),
                    "conflict": bool(item.get("conflict", False)),
                    "status": str(item.get("status", "pending") or "pending"),
                    "variants": variants,
                }
                if item.get("merged"):
                    entry["merged"] = True
                    merged_at = str(item.get("merged_at", "")).strip()
                    if merged_at:
                        entry["merged_at"] = merged_at
                    merged_priority = str(item.get("merged_priority_id", "")).strip()
                    if merged_priority:
                        entry["merged_priority_id"] = merged_priority
                federated_entries.append(entry)

        conflict_entries: list[dict[str, object]] = []
        raw_conflicts = raw.get("conflicts")
        if isinstance(raw_conflicts, Sequence):
            for item in raw_conflicts:
                if not isinstance(item, Mapping):
                    continue
                conflict_entries.append(dict(item))

        return (
            active_list,
            history_list,
            updated,
            dirty,
            federated_entries,
            conflict_entries,
        )

    def _save_priority_backlog(self, *, share: bool = True) -> None:
        self._priority_updated = self._now().isoformat()
        payload = {
            "updated": self._priority_updated,
            "active": [dict(item) for item in self._priority_active],
            "history": [dict(item) for item in self._priority_history],
        }
        federated_payload = self._serialize_federated_entries()
        payload["federated"] = federated_payload
        payload["conflicts"] = self._serialize_conflicts()
        try:
            self._priority_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
            )
        except Exception:
            pass

        current_snapshot = self._pending_snapshot()
        diff = self._compute_pending_diff(self._local_pending_snapshot, current_snapshot)
        self._local_pending_snapshot = current_snapshot
        if share and self._federate_priorities:
            self._share_backlog(diff, current_snapshot)

    def _serialize_federated_entries(self) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        for canonical, entry in sorted(self._federated_priorities.items()):
            text = str(entry.get("text", "")).strip()
            serialized: dict[str, object] = {
                "id": str(entry.get("id", "")).strip(),
                "text": text,
                "canonical": entry.get("canonical", canonical),
                "origin_peers": sorted({
                    str(peer).strip() for peer in entry.get("origin_peers", []) if str(peer).strip()
                }),
                "status": str(entry.get("status", "pending") or "pending"),
            }
            if not serialized["id"]:
                serialized["id"] = str(uuid4())
            if entry.get("merged"):
                serialized["merged"] = True
                merged_at = entry.get("merged_at")
                if isinstance(merged_at, str) and merged_at.strip():
                    serialized["merged_at"] = merged_at.strip()
                merged_priority = entry.get("merged_priority_id")
                if isinstance(merged_priority, str) and merged_priority.strip():
                    serialized["merged_priority_id"] = merged_priority.strip()
            variants_payload: list[dict[str, object]] = []
            for variant in entry.get("variants", []):
                if not isinstance(variant, Mapping):
                    continue
                peer = str(variant.get("peer", "")).strip()
                variant_text = str(variant.get("text", "")).strip()
                if not peer or not variant_text:
                    continue
                variant_entry: dict[str, object] = {"peer": peer, "text": variant_text}
                received_at = variant.get("received_at")
                if isinstance(received_at, str) and received_at.strip():
                    variant_entry["received_at"] = received_at.strip()
                if "signature_verified" in variant:
                    variant_entry["signature_verified"] = bool(
                        variant.get("signature_verified")
                    )
                variants_payload.append(variant_entry)
            variants_payload.sort(key=lambda item: item.get("peer", ""))
            serialized["variants"] = variants_payload
            conflict_ids = sorted(self._conflict_index.get(serialized["id"], set()))
            if conflict_ids:
                serialized["conflicts"] = conflict_ids
                serialized["conflict"] = any(
                    self._conflicts.get(conflict_id, {}).get("status") == "pending"
                    for conflict_id in conflict_ids
                )
            else:
                serialized["conflict"] = False
            entries.append(serialized)
        entries.sort(key=lambda item: str(item.get("text", "")).lower())
        return entries

    def _serialize_conflicts(self) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for conflict_id, conflict in self._conflicts.items():
            federated_ids: list[str] = []
            for value in conflict.get("federated_ids", []):
                entry_id = str(value or "").strip()
                if entry_id:
                    federated_ids.append(entry_id)
            if not federated_ids:
                continue
            variants_payload: list[dict[str, object]] = []
            for variant in conflict.get("variants", []):
                if not isinstance(variant, Mapping):
                    continue
                peer = str(variant.get("peer", "")).strip()
                text = str(variant.get("text", "")).strip()
                entry_id = str(variant.get("entry_id", "")).strip()
                if not peer or not text:
                    continue
                payload: dict[str, object] = {"peer": peer, "text": text}
                if entry_id:
                    payload["entry_id"] = entry_id
                received_at = variant.get("received_at")
                if isinstance(received_at, str) and received_at.strip():
                    payload["received_at"] = received_at.strip()
                variants_payload.append(payload)
            variants_payload.sort(key=lambda item: (item.get("peer", ""), item.get("entry_id", "")))
            codex_payload: dict[str, object] | None = None
            codex_state = conflict.get("codex")
            if isinstance(codex_state, Mapping):
                codex_payload = _normalize_mapping(codex_state)
            record: dict[str, object] = {
                "conflict_id": str(conflict_id),
                "federated_ids": federated_ids,
                "variants": variants_payload,
                "detected_at": str(conflict.get("detected_at", "")),
                "status": str(conflict.get("status", "pending")),
            }
            if codex_payload:
                record["codex"] = codex_payload
            records.append(record)
        records.sort(key=lambda item: item.get("detected_at", ""))
        return records

    def _pending_snapshot(self) -> dict[str, dict[str, object]]:
        snapshot: dict[str, dict[str, object]] = {}
        for entry in self._priority_active:
            priority_id = str(entry.get("id", "")).strip()
            if not priority_id:
                continue
            status = str(entry.get("status", "pending")).strip().lower()
            if status != "pending":
                continue
            snapshot[priority_id] = {
                "id": priority_id,
                "text": str(entry.get("text", "")).strip(),
                "status": status,
            }
        return snapshot

    def _compute_pending_diff(
        self,
        previous: Mapping[str, Mapping[str, object]] | None,
        current: Mapping[str, Mapping[str, object]] | None,
    ) -> dict[str, list[dict[str, object]]]:
        prev = previous or {}
        curr = current or {}
        diff: dict[str, list[dict[str, object]]] = {
            "added": [],
            "removed": [],
            "updated": [],
        }
        for priority_id, entry in curr.items():
            if priority_id not in prev:
                diff["added"].append(dict(entry))
                continue
            prev_entry = prev[priority_id]
            if (
                str(prev_entry.get("text", "")).strip()
                != str(entry.get("text", "")).strip()
            ) or (
                str(prev_entry.get("status", "")).strip()
                != str(entry.get("status", "")).strip()
            ):
                diff["updated"].append(dict(entry))
        for priority_id, entry in prev.items():
            if priority_id not in curr:
                diff["removed"].append(dict(entry))
        return diff

    def _share_backlog(
        self,
        diff: Mapping[str, Sequence[Mapping[str, object]]],
        snapshot: Mapping[str, Mapping[str, object]],
    ) -> None:
        if not any(diff.get(key) for key in ("added", "removed", "updated")):
            return
        source_peer = self._federation_peer_name or "local"
        payload_diff = {
            key: [dict(item) for item in diff.get(key, [])]
            for key in ("added", "removed", "updated")
        }
        pending_payload = [dict(item) for item in snapshot.values()]
        event_timestamp = self._now().isoformat()
        ledger_payload = {
            "event": "architect_backlog_shared",
            "source_peer": source_peer,
            "diff": payload_diff,
            "pending_count": len(pending_payload),
            "updated": self._priority_updated,
        }
        self._emit_ledger_event(ledger_payload)
        pulse_payload = {
            "timestamp": event_timestamp,
            "source_daemon": "ArchitectDaemon",
            "event_type": "architect_backlog_shared",
            "priority": "info",
            "payload": {
                "diff": payload_diff,
                "pending": pending_payload,
                "updated": self._priority_updated,
            },
            "source_peer": source_peer,
        }
        self._publish_pulse(pulse_payload)

    def _register_reflection_priorities(
        self, priorities: Sequence[str]
    ) -> list[dict[str, str]]:
        created: list[dict[str, str]] = []
        for item in priorities:
            text = str(item).strip()
            if not text:
                continue
            priority_id = str(uuid4())
            entry = {"id": priority_id, "text": text, "status": "pending"}
            self._priority_active.append(entry)
            self._priority_index[priority_id] = entry
            created.append(entry)
        if created:
            self._save_priority_backlog()
        return created

    # ------------------------------------------------------------------
    # Federated backlog helpers
    def _hydrate_federated_state(
        self, entries: Sequence[Mapping[str, object]]
    ) -> None:
        self._federated_priorities.clear()
        self._federated_index.clear()
        self._peer_backlog_entries.clear()
        self._federated_conflicts_reported = set()
        for item in entries:
            if not isinstance(item, Mapping):
                continue
            text = str(item.get("text", "")).strip()
            canonical = str(
                item.get("canonical", _canonicalize_priority_text(text))
            ).strip()
            if not canonical:
                canonical = _canonicalize_priority_text(text)
            entry_id = str(item.get("id", "")).strip() or str(uuid4())
            origin_peers_raw = item.get("origin_peers", [])
            origin_peers = [
                str(peer).strip()
                for peer in origin_peers_raw
                if isinstance(peer, (str, bytes)) and str(peer).strip()
            ]
            entry: dict[str, object] = {
                "id": entry_id,
                "text": text,
                "canonical": canonical,
                "origin_peers": sorted({peer for peer in origin_peers}),
                "conflict": bool(item.get("conflict", False)),
                "status": str(item.get("status", "pending") or "pending"),
                "variants": [],
                "_peer_map": {},
            }
            if item.get("merged"):
                entry["merged"] = True
                merged_at = str(item.get("merged_at", "")).strip()
                if merged_at:
                    entry["merged_at"] = merged_at
                merged_priority_id = str(item.get("merged_priority_id", "")).strip()
                if merged_priority_id:
                    entry["merged_priority_id"] = merged_priority_id
            variants_raw = item.get("variants")
            if isinstance(variants_raw, Sequence):
                for variant in variants_raw:
                    if not isinstance(variant, Mapping):
                        continue
                    peer = str(variant.get("peer", "")).strip()
                    variant_text = str(variant.get("text", "")).strip()
                    if not peer or not variant_text:
                        continue
                    variant_entry: dict[str, object] = {
                        "peer": peer,
                        "text": variant_text,
                    }
                    received_at = variant.get("received_at")
                    if isinstance(received_at, str) and received_at.strip():
                        variant_entry["received_at"] = received_at.strip()
                    if "signature_verified" in variant:
                        variant_entry["signature_verified"] = bool(
                            variant.get("signature_verified")
                        )
                    entry["variants"].append(variant_entry)
                    entry["_peer_map"][peer] = variant_text
                    peer_entries = self._peer_backlog_entries.setdefault(peer, {})
                    canonical_variant = _canonicalize_priority_text(variant_text)
                    peer_entries[canonical_variant] = {
                        "peer": peer,
                        "text": variant_text,
                        "canonical": canonical_variant,
                        "received_at": variant_entry.get("received_at", ""),
                        "signature_verified": bool(
                            variant_entry.get("signature_verified", False)
                        ),
                    }
            entry["variants"].sort(key=lambda data: data.get("peer", ""))
            self._federated_priorities[canonical] = entry
            self._federated_index[entry_id] = entry
            if entry.get("conflict"):
                entry["conflict"] = True

    def _hydrate_conflicts(self, entries: Sequence[Mapping[str, object]]) -> None:
        self._conflicts.clear()
        self._conflict_lookup.clear()
        self._conflict_index.clear()
        pending_conflicts: set[str] = set()
        for item in entries:
            if not isinstance(item, Mapping):
                continue
            conflict_id = str(item.get("conflict_id", "")).strip()
            if not conflict_id:
                conflict_id = str(uuid4())
            federated_ids: list[str] = []
            raw_ids = item.get("federated_ids")
            if isinstance(raw_ids, Sequence):
                for value in raw_ids:
                    entry_id = str(value or "").strip()
                    if entry_id:
                        federated_ids.append(entry_id)
            if not federated_ids:
                legacy_id = str(item.get("federated_id", "")).strip()
                if legacy_id:
                    federated_ids.append(legacy_id)
            if not federated_ids:
                continue
            key = tuple(sorted(federated_ids))
            status = str(item.get("status", "pending")).strip().lower()
            if status not in _CONFLICT_STATUSES:
                status = "pending"
            detected_at = str(item.get("detected_at", "")).strip()
            if not detected_at:
                detected_at = self._now().isoformat()
            variants: list[dict[str, object]] = []
            raw_variants = item.get("variants")
            if isinstance(raw_variants, Sequence):
                for variant in raw_variants:
                    if not isinstance(variant, Mapping):
                        continue
                    peer = str(variant.get("peer", "")).strip()
                    text = str(variant.get("text", "")).strip()
                    if not peer or not text:
                        continue
                    entry_id = str(variant.get("entry_id", "")).strip()
                    if not entry_id:
                        entry_id = federated_ids[0]
                    received_at = str(variant.get("received_at", "")).strip()
                    variant_payload: dict[str, object] = {
                        "peer": peer,
                        "text": text,
                        "entry_id": entry_id,
                    }
                    if received_at:
                        variant_payload["received_at"] = received_at
                    variants.append(variant_payload)
            if not variants:
                # Legacy format: synthesize from federated entries
                for entry_id in federated_ids:
                    entry = self._federated_index.get(entry_id)
                    if not entry:
                        continue
                    for variant in entry.get("variants", []):
                        if not isinstance(variant, Mapping):
                            continue
                        peer = str(variant.get("peer", "")).strip()
                        text = str(variant.get("text", "")).strip()
                        if peer and text:
                            payload: dict[str, object] = {
                                "peer": peer,
                                "text": text,
                                "entry_id": entry_id,
                            }
                            received_at = str(variant.get("received_at", "")).strip()
                            if received_at:
                                payload["received_at"] = received_at
                            variants.append(payload)
            variants.sort(key=lambda data: (data.get("peer", ""), data.get("entry_id", "")))
            codex_state: dict[str, object] = {}
            raw_codex = item.get("codex")
            if isinstance(raw_codex, Mapping):
                codex_state = dict(raw_codex)
            record = {
                "conflict_id": conflict_id,
                "federated_ids": list(dict.fromkeys(federated_ids)),
                "variants": variants,
                "detected_at": detected_at,
                "status": status,
                "codex": codex_state,
            }
            self._conflicts[conflict_id] = record
            self._conflict_lookup[key] = conflict_id
            for entry_id in federated_ids:
                self._conflict_index.setdefault(entry_id, set()).add(conflict_id)
                entry = self._federated_index.get(entry_id)
                if entry and status == "pending":
                    entry["conflict"] = True
            if status == "pending":
                pending_conflicts.add(conflict_id)
        self._federated_conflicts_reported = pending_conflicts

    def _create_federated_entry(self, canonical: str, text: str) -> dict[str, object]:
        return {
            "id": str(uuid4()),
            "text": text,
            "canonical": canonical,
            "origin_peers": [],
            "variants": [],
            "conflict": False,
            "status": "pending",
            "_peer_map": {},
        }

    def _clone_federated_entry(self, entry: Mapping[str, object]) -> dict[str, object]:
        text = str(entry.get("text", "")).strip()
        canonical = str(
            entry.get("canonical", _canonicalize_priority_text(text))
        ).strip()
        cloned = {
            "id": str(entry.get("id", "")).strip() or str(uuid4()),
            "text": text,
            "canonical": canonical or _canonicalize_priority_text(text),
            "origin_peers": [],
            "variants": [],
            "conflict": False,
            "status": str(entry.get("status", "pending") or "pending"),
            "_peer_map": {},
        }
        if entry.get("merged"):
            cloned["merged"] = True
            merged_at = entry.get("merged_at")
            if isinstance(merged_at, str) and merged_at.strip():
                cloned["merged_at"] = merged_at.strip()
            merged_priority_id = entry.get("merged_priority_id")
            if isinstance(merged_priority_id, str) and merged_priority_id.strip():
                cloned["merged_priority_id"] = merged_priority_id.strip()
        return cloned

    def _apply_peer_variant(
        self, entry: dict[str, object], peer: str, variant: Mapping[str, object]
    ) -> None:
        text = str(variant.get("text", "")).strip()
        if not text:
            return
        canonical = str(
            variant.get("canonical", _canonicalize_priority_text(text))
        ).strip()
        received_at = str(variant.get("received_at", "")).strip()
        verified = bool(variant.get("signature_verified", False))
        peer_map = entry.setdefault("_peer_map", {})
        peer_map[peer] = text
        origin_peers = entry.setdefault("origin_peers", [])
        if peer not in origin_peers:
            origin_peers.append(peer)
        variants = entry.setdefault("variants", [])
        existing_variant: dict[str, object] | None = None
        for payload in variants:
            if isinstance(payload, Mapping) and payload.get("peer") == peer:
                existing_variant = payload  # type: ignore[assignment]
                break
        if existing_variant is None:
            new_variant: dict[str, object] = {"peer": peer, "text": text}
            if received_at:
                new_variant["received_at"] = received_at
            if "signature_verified" in variant:
                new_variant["signature_verified"] = verified
            variants.append(new_variant)
        else:
            existing_variant["text"] = text
            if received_at:
                existing_variant["received_at"] = received_at
            if "signature_verified" in variant:
                existing_variant["signature_verified"] = verified
        if not entry.get("text"):
            entry["text"] = text
        else:
            if (
                str(entry.get("text", "")).strip() != text
                and _canonicalize_priority_text(str(entry.get("text", "")))
                == canonical
            ):
                entry["conflict"] = True
        entry["status"] = str(entry.get("status", "pending") or "pending")

    def _update_peer_backlog_entries(
        self,
        peer: str,
        entries: Sequence[Mapping[str, object]] | Sequence[object],
        timestamp: str,
        verified: bool,
    ) -> None:
        normalized: dict[str, dict[str, object]] = {}
        for item in entries:
            if isinstance(item, Mapping):
                text = str(item.get("text", "")).strip()
            else:
                text = str(item).strip()
            if not text:
                continue
            canonical = _canonicalize_priority_text(text)
            normalized[canonical] = {
                "peer": peer,
                "text": text,
                "canonical": canonical,
                "received_at": timestamp,
                "signature_verified": bool(verified),
            }
        self._peer_backlog_entries[peer] = normalized

    def _update_conflicts_from_priorities(
        self, priorities: Mapping[str, dict[str, object]]
    ) -> set[str]:
        previous_pending = set(self._federated_conflicts_reported)
        new_conflicts: dict[str, dict[str, object]] = {}
        new_lookup: dict[tuple[str, ...], str] = {}
        entry_conflict_index: dict[str, set[str]] = {}
        pending_conflicts: set[str] = set()
        emitted_conflicts: set[str] = set()

        variant_records: list[dict[str, str]] = []
        for entry in priorities.values():
            entry_id = str(entry.get("id", "")).strip()
            if not entry_id:
                continue
            variants = entry.get("variants", [])
            if isinstance(variants, Sequence):
                for variant in variants:
                    if not isinstance(variant, Mapping):
                        continue
                    peer = str(variant.get("peer", "")).strip()
                    text = str(variant.get("text", "")).strip()
                    if not peer or not text:
                        continue
                    record = {
                        "peer": peer,
                        "text": text,
                        "entry_id": entry_id,
                        "received_at": str(variant.get("received_at", "")).strip(),
                    }
                    variant_records.append(record)

        conflict_groups: dict[tuple[str, ...], dict[str, object]] = {}
        for left, right in itertools.combinations(variant_records, 2):
            if left["peer"] == right["peer"]:
                continue
            entry_ids = tuple(sorted({left["entry_id"], right["entry_id"]}))
            same_entry = len(entry_ids) == 1
            existing_conflict_id = self._conflict_lookup.get(entry_ids)
            existing_conflict = (
                self._conflicts.get(existing_conflict_id)
                if existing_conflict_id
                else None
            )
            if existing_conflict and existing_conflict.get("status") in {"accepted", "separate"}:
                continue
            if left["text"].strip().lower() == right["text"].strip().lower():
                continue
            similarity = _text_similarity(left["text"], right["text"])
            canonical_match = (
                _canonicalize_priority_text(left["text"])
                == _canonicalize_priority_text(right["text"])
            )
            if same_entry:
                if not canonical_match and similarity < _CONFLICT_SIMILARITY_THRESHOLD:
                    continue
            else:
                if similarity < _CONFLICT_SIMILARITY_THRESHOLD:
                    continue
            group = conflict_groups.setdefault(entry_ids, {"variants": {}, "pairs": []})
            for record in (left, right):
                variant_key = (record["peer"], record["entry_id"])
                if variant_key not in group["variants"]:
                    group["variants"][variant_key] = dict(record)
            group.setdefault("pairs", []).append(
                {
                    "peer_a": left["peer"],
                    "text_a": left["text"],
                    "peer_b": right["peer"],
                    "text_b": right["text"],
                    "similarity": similarity,
                }
            )

        now_iso = self._now().isoformat()
        for key, details in conflict_groups.items():
            conflict_id = self._conflict_lookup.get(key)
            existing_conflict = (
                self._conflicts.get(conflict_id) if conflict_id else None
            )
            if conflict_id is None:
                conflict_id = str(uuid4())
            record: dict[str, object] = {
                "conflict_id": conflict_id,
                "federated_ids": list(key),
                "variants": [],
                "detected_at": now_iso,
                "status": "pending",
                "codex": {},
            }
            if existing_conflict:
                detected = str(existing_conflict.get("detected_at", "")).strip()
                if detected:
                    record["detected_at"] = detected
                status = str(existing_conflict.get("status", "pending"))
                if status in {"pending", "rejected", "accepted", "separate"}:
                    record["status"] = status
                codex_state = existing_conflict.get("codex")
                if isinstance(codex_state, Mapping):
                    record["codex"] = dict(codex_state)
            variants_list: list[dict[str, object]] = []
            for variant in details.get("variants", {}).values():
                payload: dict[str, object] = {
                    "peer": variant.get("peer", ""),
                    "text": variant.get("text", ""),
                    "entry_id": variant.get("entry_id", ""),
                }
                received_at = str(variant.get("received_at", "")).strip()
                if received_at:
                    payload["received_at"] = received_at
                variants_list.append(payload)
            variants_list.sort(key=lambda item: (item.get("peer", ""), item.get("entry_id", "")))
            record["variants"] = variants_list
            new_lookup[key] = conflict_id
            new_conflicts[conflict_id] = record
            is_active = record["status"] in {"pending", "rejected"}
            for entry_id in key:
                entry_conflict_index.setdefault(entry_id, set()).add(conflict_id)
            if is_active:
                pending_conflicts.add(conflict_id)
                if conflict_id not in previous_pending:
                    emitted_conflicts.add(conflict_id)

        for conflict_id, record in self._conflicts.items():
            if conflict_id in new_conflicts:
                continue
            status = str(record.get("status", "pending"))
            if status in {"accepted", "separate"}:
                new_conflicts[conflict_id] = dict(record)
                key = tuple(
                    sorted(
                        {
                            str(value or "").strip()
                            for value in record.get("federated_ids", [])
                            if str(value or "").strip()
                        }
                    )
                )
                if key:
                    new_lookup[key] = conflict_id

        for entry in priorities.values():
            entry_id = str(entry.get("id", "")).strip()
            if not entry_id:
                continue
            conflict_ids = entry_conflict_index.get(entry_id, set())
            entry["conflict"] = any(
                new_conflicts.get(conflict_id, {}).get("status") in {"pending", "rejected"}
                for conflict_id in conflict_ids
            )

        self._conflicts = new_conflicts
        self._conflict_lookup = new_lookup
        self._conflict_index = entry_conflict_index
        self._federated_conflicts_reported = pending_conflicts
        return emitted_conflicts

    def _reconcile_federated_priorities(self) -> None:
        new_priorities: dict[str, dict[str, object]] = {}
        for peer, entries in self._peer_backlog_entries.items():
            for canonical, variant in entries.items():
                text = str(variant.get("text", "")).strip()
                if not text:
                    continue
                entry = new_priorities.get(canonical)
                if entry is None:
                    existing = self._federated_priorities.get(canonical)
                    entry = (
                        self._clone_federated_entry(existing)
                        if existing is not None
                        else self._create_federated_entry(canonical, text)
                    )
                    new_priorities[canonical] = entry
                self._apply_peer_variant(entry, peer, variant)
        for entry in new_priorities.values():
            entry["origin_peers"] = sorted(set(entry.get("origin_peers", [])))
            variants = entry.get("variants", [])
            if isinstance(variants, list):
                variants.sort(key=lambda data: data.get("peer", ""))

        emitted_conflicts = self._update_conflicts_from_priorities(new_priorities)
        for conflict_id in emitted_conflicts:
            conflict_record = self._conflicts.get(conflict_id)
            if conflict_record:
                self._emit_backlog_conflict(conflict_record)
        self._federated_priorities = new_priorities
        self._federated_index = {
            entry["id"]: entry for entry in new_priorities.values() if entry.get("id")
        }

    def _handle_backlog_action(self, event: Mapping[str, object]) -> None:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            return
        conflict_id = str(payload.get("conflict_id", "")).strip()
        if not conflict_id:
            return
        action = str(payload.get("action", "")).strip().lower()
        if action == "accept":
            self.accept_conflict_merge(conflict_id)
        elif action == "reject":
            reason = str(payload.get("reason", "")).strip()
            self.reject_conflict_merge(conflict_id, reason=reason or None)
        elif action in {"separate", "keep_separate"}:
            self.keep_conflict_separate(conflict_id)

    def _emit_backlog_conflict(self, conflict: Mapping[str, object]) -> None:
        conflict_id = str(conflict.get("conflict_id", "")).strip()
        federated_ids = [
            str(value or "").strip() for value in conflict.get("federated_ids", [])
            if str(value or "").strip()
        ]
        variants_payload: list[dict[str, object]] = []
        peers: list[str] = []
        for variant in conflict.get("variants", []):
            if not isinstance(variant, Mapping):
                continue
            peer = str(variant.get("peer", "")).strip()
            text = str(variant.get("text", "")).strip()
            if not peer or not text:
                continue
            entry_id = str(variant.get("entry_id", "")).strip()
            payload: dict[str, object] = {"peer": peer, "text": text}
            if entry_id:
                payload["entry_id"] = entry_id
            received_at = str(variant.get("received_at", "")).strip()
            if received_at:
                payload["received_at"] = received_at
            variants_payload.append(payload)
            peers.append(peer)
        peers = sorted({peer for peer in peers if peer})
        ledger_payload = {
            "event": "architect_backlog_conflict",
            "conflict_id": conflict_id,
            "federated_ids": federated_ids,
            "detected_at": conflict.get("detected_at"),
            "peers": peers,
            "variants": variants_payload,
        }
        self._emit_ledger_event(ledger_payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_backlog_conflict",
                "priority": "warning",
                "payload": {
                    "conflict_id": conflict_id,
                    "federated_ids": federated_ids,
                    "peers": peers,
                    "detected_at": conflict.get("detected_at"),
                    "variants": variants_payload,
                },
            }
        )
        self._record_cycle_conflict(conflict_id)
        if conflict_id:
            self._process_conflict_resolution(conflict_id)

    def _process_conflict_resolution(self, conflict_id: str) -> None:
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            return
        status = str(conflict.get("status", "pending"))
        if status not in {"pending", "rejected"}:
            return
        variants = conflict.get("variants", [])
        if not isinstance(variants, Sequence) or len(variants) < 2:
            return
        codex_state = conflict.get("codex")
        if not isinstance(codex_state, dict):
            codex_state = {}
        conflict["codex"] = codex_state
        suggestion_state = codex_state.get("suggestion")
        if isinstance(suggestion_state, Mapping):
            suggestion_status = str(suggestion_state.get("status", "pending"))
            if suggestion_status in {"pending", "accepted"}:
                return
        if codex_state.get("status") in {"failed", "rejected"} and codex_state.get(
            "attempted_at"
        ):
            return
        prompt = self._build_conflict_prompt(conflict)
        codex_state["attempted_at"] = self._now().isoformat()
        codex_state["status"] = "pending"
        output, error = self._execute_codex_prompt(prompt)
        if error:
            codex_state["status"] = "failed"
            codex_state["error"] = {
                "message": error,
                "output": (output or "")[:1000],
            }
            self._emit_conflict_resolution_failed(conflict_id, error, output)
            self._save_priority_backlog(share=False)
            return
        suggestion_payload, parse_error = self._parse_conflict_response(output)
        if parse_error or suggestion_payload is None:
            codex_state["status"] = "failed"
            codex_state["error"] = {
                "message": parse_error or "invalid_response",
                "output": (output or "")[:1000],
            }
            self._emit_conflict_resolution_failed(conflict_id, parse_error or "invalid_response", output)
            self._save_priority_backlog(share=False)
            return
        suggestion_record = self._store_conflict_suggestion(
            conflict_id, conflict, suggestion_payload, prompt, output
        )
        codex_state["status"] = "succeeded"
        codex_state["suggestion"] = suggestion_record
        conflict["codex"] = codex_state
        conflict["status"] = "pending"
        self._emit_conflict_resolution_success(conflict_id, suggestion_record)
        self._save_priority_backlog(share=False)

    def _build_conflict_prompt(self, conflict: Mapping[str, object]) -> str:
        ethics = codex_daemon.load_ethics()
        lines = [
            "You are assisting with SentientOS federated backlog reconciliation.",
            SAFETY_ENVELOPE,
            "The following peers proposed overlapping but non-identical priorities:",
        ]
        variants = conflict.get("variants", [])
        if isinstance(variants, Sequence):
            sorted_variants = sorted(
                (
                    variant
                    for variant in variants
                    if isinstance(variant, Mapping)
                    and str(variant.get("peer", "")).strip()
                    and str(variant.get("text", "")).strip()
                ),
                key=lambda item: str(item.get("peer", "")),
            )
            for variant in sorted_variants:
                peer = str(variant.get("peer", "")).strip()
                text = str(variant.get("text", "")).strip()
                text_literal = json.dumps(text)
                lines.append(f"- Peer {peer}: {text_literal}")
        lines.append(
            "Suggest a unified priority that preserves intent, removes duplication, and respects covenant safety."
        )
        lines.append('Respond in JSON: { "merged_priority": "string", "notes": "string" }')
        if ethics:
            lines.append("")
            lines.append("Ethics Context:")
            lines.append(ethics)
        return "\n".join(lines)

    def _execute_codex_prompt(self, prompt: str) -> tuple[str, str | None]:
        try:
            proc = subprocess.run(
                ["codex", "exec", prompt],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return "", f"codex_execution_failed: {exc}"
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        if proc.returncode != 0:
            message = f"codex_exit_{proc.returncode}"
            if stderr.strip():
                message = f"{message}: {stderr.strip()}"
            return stdout, message
        return stdout, None

    def _parse_conflict_response(
        self, output: str
    ) -> tuple[dict[str, str] | None, str | None]:
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return None, "invalid_json"
        if not isinstance(parsed, Mapping):
            return None, "invalid_schema"
        keys = set(parsed.keys())
        if keys != {"merged_priority", "notes"}:
            return None, "invalid_schema"
        merged_priority = parsed.get("merged_priority")
        notes_value = parsed.get("notes")
        if not isinstance(merged_priority, str) or not merged_priority.strip():
            return None, "invalid_merged_priority"
        if not isinstance(notes_value, str):
            return None, "invalid_notes"
        suggestion = {
            "merged_priority": merged_priority.strip(),
            "notes": notes_value.strip(),
        }
        return suggestion, None

    def _store_conflict_suggestion(
        self,
        conflict_id: str,
        conflict: Mapping[str, object],
        suggestion: Mapping[str, str],
        prompt: str,
        output: str,
    ) -> dict[str, object]:
        merged_priority = str(suggestion.get("merged_priority", "")).strip()
        notes = str(suggestion.get("notes", "")).strip()
        priority_id = str(uuid4())
        origin_peers = sorted(
            {
                str(variant.get("peer", "")).strip()
                for variant in conflict.get("variants", [])
                if isinstance(variant, Mapping)
                and str(variant.get("peer", "")).strip()
            }
        )
        merged_from = [
            str(value or "").strip() for value in conflict.get("federated_ids", [])
            if str(value or "").strip()
        ]
        generated_at = self._now().isoformat()
        suggestion_record: dict[str, object] = {
            "priority_id": priority_id,
            "merged_priority": merged_priority,
            "notes": notes,
            "origin_peers": origin_peers,
            "merged_from": merged_from,
            "status": "pending",
            "generated_at": generated_at,
        }
        timestamp = self._now().strftime("%Y%m%d_%H%M%S")
        path = self._conflict_resolution_dir / f"merged_{timestamp}.json"
        counter = 0
        while path.exists():
            counter += 1
            path = self._conflict_resolution_dir / f"merged_{timestamp}_{counter}.json"
        payload = {
            "conflict_id": conflict_id,
            "generated_at": generated_at,
            "suggestion": dict(suggestion_record),
            "prompt": prompt,
            "raw_output": output,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        suggestion_record["path"] = path.as_posix()
        return suggestion_record

    def _emit_conflict_resolution_success(
        self, conflict_id: str, suggestion: Mapping[str, object]
    ) -> None:
        peers = list(suggestion.get("origin_peers", [])) if isinstance(
            suggestion.get("origin_peers"), Sequence
        ) else []
        ledger_payload = {
            "event": "architect_backlog_resolved",
            "conflict_id": conflict_id,
            "priority_id": suggestion.get("priority_id"),
            "merged_priority": suggestion.get("merged_priority"),
            "origin_peers": peers,
            "merged_from": list(suggestion.get("merged_from", [])),
            "path": suggestion.get("path"),
        }
        self._emit_ledger_event(ledger_payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_backlog_resolved",
                "priority": "info",
                "payload": {
                    "conflict_id": conflict_id,
                    "priority_id": suggestion.get("priority_id"),
                    "merged_priority": suggestion.get("merged_priority"),
                    "origin_peers": peers,
                    "merged_from": list(suggestion.get("merged_from", [])),
                    "path": suggestion.get("path"),
                },
            }
        )
        self._record_cycle_conflict(conflict_id)

    def _emit_conflict_resolution_failed(
        self, conflict_id: str, reason: str, output: str | None
    ) -> None:
        ledger_payload = {
            "event": "architect_backlog_resolution_failed",
            "conflict_id": conflict_id,
            "reason": reason,
        }
        if output:
            ledger_payload["output"] = output[:1000]
        self._emit_ledger_event(ledger_payload)
        pulse_payload: dict[str, object] = {
            "conflict_id": conflict_id,
            "reason": reason,
        }
        if output:
            pulse_payload["output"] = output[:500]
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_backlog_resolution_failed",
                "priority": "warning",
                "payload": pulse_payload,
            }
        )
        self._record_cycle_conflict(conflict_id)

    def accept_conflict_merge(self, conflict_id: str) -> bool:
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            return False
        codex_state = conflict.get("codex")
        if not isinstance(codex_state, dict):
            return False
        suggestion = codex_state.get("suggestion")
        if not isinstance(suggestion, Mapping):
            return False
        merged_priority = str(suggestion.get("merged_priority", "")).strip()
        if not merged_priority:
            return False
        status = str(conflict.get("status", "pending"))
        if status not in {"pending", "rejected"}:
            return False
        priority_id = str(suggestion.get("priority_id", "")).strip()
        if not priority_id:
            priority_id = str(uuid4())
            suggestion = dict(suggestion)
            suggestion["priority_id"] = priority_id
            codex_state["suggestion"] = suggestion
        if priority_id in self._priority_index:
            return False
        origin_peers = list(suggestion.get("origin_peers", [])) if isinstance(
            suggestion.get("origin_peers"), Sequence
        ) else []
        merged_from = [
            str(value or "").strip() for value in conflict.get("federated_ids", [])
            if str(value or "").strip()
        ]
        entry = {
            "id": priority_id,
            "text": merged_priority,
            "status": "pending",
        }
        if origin_peers:
            entry["origin_peers"] = origin_peers
        if merged_from:
            entry["merged_from"] = merged_from
        self._priority_active.append(entry)
        self._priority_index[priority_id] = entry
        now = self._now().isoformat()
        suggestion_record = dict(suggestion)
        suggestion_record["status"] = "accepted"
        suggestion_record["accepted_at"] = now
        codex_state["suggestion"] = suggestion_record
        codex_state["status"] = "accepted"
        conflict["status"] = "accepted"
        conflict["resolved_at"] = now
        for entry_id in merged_from:
            ids = self._conflict_index.get(entry_id)
            if ids:
                ids.discard(conflict_id)
                if not ids:
                    self._conflict_index.pop(entry_id, None)
            fed_entry = self._federated_index.get(entry_id)
            if fed_entry:
                fed_entry["merged"] = True
                fed_entry["merged_at"] = now
                fed_entry["merged_priority_id"] = priority_id
                has_active = any(
                    self._conflicts.get(cid, {}).get("status") in {"pending", "rejected"}
                    for cid in self._conflict_index.get(entry_id, set())
                )
                fed_entry["conflict"] = has_active
        self._federated_conflicts_reported.discard(conflict_id)
        self._save_priority_backlog()
        self._emit_ledger_event(
            {
                "event": "architect_backlog_merge_accepted",
                "conflict_id": conflict_id,
                "priority_id": priority_id,
                "merged_priority": merged_priority,
                "origin_peers": origin_peers,
                "merged_from": merged_from,
            }
        )
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_backlog_merge_accepted",
                "priority": "info",
                "payload": {
                    "conflict_id": conflict_id,
                    "priority_id": priority_id,
                    "merged_priority": merged_priority,
                    "origin_peers": origin_peers,
                    "merged_from": merged_from,
                },
            }
        )
        self._record_cycle_conflict(conflict_id)
        return True

    def reject_conflict_merge(self, conflict_id: str, reason: str | None = None) -> bool:
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            return False
        codex_state = conflict.get("codex")
        if not isinstance(codex_state, dict):
            return False
        suggestion = codex_state.get("suggestion")
        if not isinstance(suggestion, Mapping):
            return False
        suggestion_record = dict(suggestion)
        now = self._now().isoformat()
        suggestion_record["status"] = "rejected"
        suggestion_record["rejected_at"] = now
        codex_state["suggestion"] = suggestion_record
        codex_state["status"] = "rejected"
        conflict["codex"] = codex_state
        conflict["status"] = "rejected"
        self._save_priority_backlog(share=False)
        payload = {
            "event": "architect_backlog_merge_rejected",
            "conflict_id": conflict_id,
            "notes": suggestion_record.get("notes"),
        }
        if reason:
            payload["reason"] = reason
        self._emit_ledger_event(payload)
        pulse_payload = {
            "timestamp": now,
            "source_daemon": "ArchitectDaemon",
            "event_type": "architect_backlog_merge_rejected",
            "priority": "warning",
            "payload": {
                "conflict_id": conflict_id,
                "notes": suggestion_record.get("notes"),
            },
        }
        if reason:
            pulse_payload["payload"]["reason"] = reason
        self._publish_pulse(pulse_payload)
        self._record_cycle_conflict(conflict_id)
        return True

    def keep_conflict_separate(self, conflict_id: str) -> bool:
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            return False
        now = self._now().isoformat()
        codex_state = conflict.get("codex")
        if isinstance(codex_state, dict):
            codex_state["status"] = "separate"
            suggestion = codex_state.get("suggestion")
            if isinstance(suggestion, Mapping):
                suggestion_record = dict(suggestion)
                suggestion_record["status"] = "dismissed"
                suggestion_record["dismissed_at"] = now
                codex_state["suggestion"] = suggestion_record
            conflict["codex"] = codex_state
        conflict["status"] = "separate"
        conflict["resolved_at"] = now
        for entry_id in conflict.get("federated_ids", []):
            entry_id_str = str(entry_id or "").strip()
            if not entry_id_str:
                continue
            ids = self._conflict_index.get(entry_id_str)
            if ids:
                ids.discard(conflict_id)
                if not ids:
                    self._conflict_index.pop(entry_id_str, None)
            entry = self._federated_index.get(entry_id_str)
            if entry:
                has_active = any(
                    self._conflicts.get(cid, {}).get("status") in {"pending", "rejected"}
                    for cid in self._conflict_index.get(entry_id_str, set())
                )
                entry["conflict"] = has_active
        self._federated_conflicts_reported.discard(conflict_id)
        self._save_priority_backlog(share=False)
        self._emit_ledger_event(
            {
                "event": "architect_backlog_merge_separated",
                "conflict_id": conflict_id,
                "federated_ids": list(conflict.get("federated_ids", [])),
            }
        )
        self._publish_pulse(
            {
                "timestamp": now,
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_backlog_merge_separated",
                "priority": "info",
                "payload": {
                    "conflict_id": conflict_id,
                    "federated_ids": list(conflict.get("federated_ids", [])),
                },
            }
        )
        self._record_cycle_conflict(conflict_id)
        return True

    def _store_peer_backlog(
        self,
        peer: str,
        entries: Sequence[Mapping[str, object]] | Sequence[object],
        diff: Mapping[str, object] | None,
        *,
        verified: bool,
        event_timestamp: str,
    ) -> Path:
        filename = _sanitize_token(peer or "peer") or "peer"
        path = self._peer_backlog_dir / f"{filename}.json"
        update_entry: dict[str, object] = {
            "source_peer": peer,
            "received_at": self._now().isoformat(),
            "event_timestamp": event_timestamp,
            "signature_verified": bool(verified),
            "pending": [
                {"text": str(item.get("text", "")) if isinstance(item, Mapping) else str(item)}
                for item in entries
            ],
        }
        if diff:
            update_entry["diff"] = _normalize_mapping(diff)
        payload: dict[str, object] = {"peer": peer, "updates": []}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(existing, Mapping):
                    for key, value in existing.items():
                        if key == "updates" and isinstance(value, list):
                            payload["updates"] = list(value)
                        elif key != "updates":
                            payload[key] = value
            except Exception:
                payload = {"peer": peer, "updates": []}
        updates_list = payload.setdefault("updates", [])
        if isinstance(updates_list, list):
            updates_list.append(update_entry)
        else:
            payload["updates"] = [update_entry]
        payload["latest_pending"] = update_entry["pending"]
        payload["last_received_at"] = update_entry["received_at"]
        payload["signature_verified"] = bool(verified)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _emit_backlog_received(
        self,
        peer: str,
        entries: Sequence[Mapping[str, object]] | Sequence[object],
        diff: Mapping[str, object] | None,
        verified: bool,
        stored_path: Path,
    ) -> None:
        ledger_payload = {
            "event": "architect_backlog_received",
            "peer": peer,
            "count": len(entries),
            "signature_verified": bool(verified),
            "path": stored_path.as_posix().lstrip("/"),
        }
        if diff:
            ledger_payload["diff"] = _normalize_mapping(diff)
        self._emit_ledger_event(ledger_payload)
        pulse_payload = {
            "timestamp": self._now().isoformat(),
            "source_daemon": "ArchitectDaemon",
            "event_type": "architect_backlog_received",
            "priority": "info" if verified else "warning",
            "payload": {
                "peer": peer,
                "count": len(entries),
                "signature_verified": bool(verified),
                "path": stored_path.as_posix(),
                "diff": _normalize_mapping(diff) if diff else {},
            },
        }
        self._publish_pulse(pulse_payload)

    def _emit_backlog_invalid(self, peer: str) -> None:
        payload = {
            "event": "architect_backlog_invalid",
            "peer": peer,
            "reason": "invalid_signature",
        }
        self._emit_ledger_event(payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_backlog_invalid",
                "priority": "warning",
                "payload": {"peer": peer, "reason": "invalid_signature"},
            }
        )

    def _extract_remote_priorities(
        self, payload: Mapping[str, object]
    ) -> list[dict[str, object]]:
        candidates: list[dict[str, object]] = []
        pending = payload.get("pending") or payload.get("active")
        if isinstance(pending, Sequence):
            for item in pending:
                if isinstance(item, Mapping):
                    text = str(item.get("text", "")).strip()
                    status = str(item.get("status", "pending")).strip().lower()
                else:
                    text = str(item).strip()
                    status = "pending"
                if not text:
                    continue
                if status not in {"pending", "in_progress", ""}:
                    continue
                candidates.append({"text": text})
        return candidates

    def merge_federated_priority(
        self, federated_id: str
    ) -> dict[str, str] | None:
        entry = self._federated_index.get(federated_id)
        if not entry:
            return None
        text = str(entry.get("text", "")).strip()
        if not text:
            return None
        priority_id = str(uuid4())
        local_entry = {"id": priority_id, "text": text, "status": "pending"}
        self._priority_active.append(local_entry)
        self._priority_index[priority_id] = local_entry
        entry["merged"] = True
        entry["merged_at"] = self._now().isoformat()
        entry["merged_priority_id"] = priority_id
        self._save_priority_backlog()
        ledger_payload = {
            "event": "architect_backlog_merged",
            "federated_id": federated_id,
            "priority_id": priority_id,
            "text": text,
            "origin_peers": list(entry.get("origin_peers", [])),
        }
        self._emit_ledger_event(ledger_payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_backlog_merged",
                "priority": "info",
                "payload": {
                    "federated_id": federated_id,
                    "priority_id": priority_id,
                    "text": text,
                    "origin_peers": list(entry.get("origin_peers", [])),
                },
            }
        )
        return local_entry

    def _emit_priority_event(
        self,
        event_type: str,
        entry: Mapping[str, object],
        *,
        cycle: int | None,
        priority_level: str,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        ledger_payload = {
            "event": event_type,
            "priority_id": entry.get("id"),
            "text": entry.get("text"),
        }
        pulse_payload = {
            "priority_id": entry.get("id"),
            "text": entry.get("text"),
        }
        if cycle is not None:
            ledger_payload["cycle"] = cycle
            pulse_payload["cycle"] = cycle
        if extra:
            for key, value in extra.items():
                ledger_payload[key] = value
                pulse_payload[key] = value
        self._emit_ledger_event(ledger_payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": event_type,
                "priority": priority_level,
                "payload": pulse_payload,
            }
        )

    def _select_backlog_priority(self, cycle_number: int) -> dict[str, str] | None:
        for entry in self._priority_active:
            status = str(entry.get("status", "pending")).strip().lower()
            if status == "pending":
                entry["status"] = "in_progress"
                self._priority_index[entry["id"]] = entry
                self._save_priority_backlog()
                self._emit_priority_event(
                    "architect_priority_selected",
                    entry,
                    cycle=cycle_number,
                    priority_level="info",
                    extra={"status": entry["status"]},
                )
                return entry
        return None

    def _finalize_priority(
        self,
        priority_id: str | None,
        *,
        status: str,
        cycle: int,
        reason: str | None = None,
    ) -> None:
        if not priority_id:
            return
        entry = self._priority_index.get(priority_id)
        if not entry:
            return
        status = str(status).strip().lower()
        if status not in _PRIORITY_ACTIVE_STATUSES:
            return
        entry["status"] = status
        if status in _PRIORITY_HISTORY_STATUSES:
            already_recorded = any(
                hist.get("id") == priority_id for hist in self._priority_history
            )
            if not already_recorded:
                record: dict[str, str] = {
                    "id": entry["id"],
                    "text": entry["text"],
                    "status": status,
                    "completed_at": self._now().isoformat(),
                }
                self._priority_history.append(record)
        self._save_priority_backlog()
        extra: dict[str, object] = {"status": status}
        if reason:
            extra["reason"] = reason
        event_type = "architect_priority_done"
        priority_level = "info"
        if status != "done":
            event_type = "architect_priority_discarded"
            priority_level = "warning"
        self._record_cycle_backlog_outcome(priority_id, status=status, reason=reason)
        self._emit_priority_event(
            event_type,
            entry,
            cycle=cycle,
            priority_level=priority_level,
            extra=extra,
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
        is_reflection = cycle_number % self._reflection_interval == 0
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
        self._initialize_cycle_summary(request, trigger)
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

    def _initialize_cycle_summary(self, request: ArchitectRequest, trigger: str) -> None:
        summary: dict[str, object] = {
            "cycle_id": str(uuid4()),
            "started_at": request.created_at.isoformat(),
            "ended_at": "",
            "reflections": [],
            "backlog_attempts": [],
            "federation_conflicts": [],
            "cooldown": False,
            "anomalies": [],
            "notes": "",
        }
        state: dict[str, object] = {
            "summary": summary,
            "notes": [
                f"cycle={request.cycle_number}",
                f"mode={request.mode}",
                f"trigger={trigger}",
            ],
            "backlog_index": {},
            "conflict_ids": set(),
            "cycle_number": request.cycle_number,
        }
        if self._pending_cycle_anomalies:
            unique = sorted(dict.fromkeys(self._pending_cycle_anomalies))
            summary["anomalies"] = list(unique)
            notes = state.get("notes")
            if isinstance(notes, list):
                notes.append(f"anomalies={','.join(unique)}")
            self._pending_cycle_anomalies = []
        if self._pending_cycle_conflicts:
            state["conflict_ids"] = set(self._pending_cycle_conflicts)
            self._pending_cycle_conflicts = set()
        if self._pending_cycle_cooldown:
            summary["cooldown"] = True
            notes = state.get("notes")
            if isinstance(notes, list):
                notes.append("cooldown=pending")
            self._pending_cycle_cooldown = False
        self._cycle_state[request.architect_id] = state
        self._active_cycle_id = request.architect_id
        self._record_cycle_backlog_attempt(request, state)

    def _record_cycle_backlog_attempt(
        self, request: ArchitectRequest, state: Mapping[str, object]
    ) -> None:
        details = request.details
        priority_id = str(details.get("priority_id", "")).strip()
        if not priority_id:
            return
        text = str(details.get("priority_text", "")).strip()
        summary = state.get("summary")
        if not isinstance(summary, dict):
            return
        backlog_entry = {"id": priority_id, "text": text, "status": "pending"}
        attempts = summary.setdefault("backlog_attempts", [])
        if isinstance(attempts, list):
            attempts.append(backlog_entry)
        backlog_index = state.get("backlog_index")
        if isinstance(backlog_index, dict):
            backlog_index[priority_id] = backlog_entry
        notes = state.get("notes")
        if isinstance(notes, list):
            notes.append(f"backlog={priority_id}")

    def _find_cycle_backlog_entry(
        self, priority_id: str
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        for state in self._cycle_state.values():
            backlog_index = state.get("backlog_index")
            if isinstance(backlog_index, dict) and priority_id in backlog_index:
                return backlog_index[priority_id], state
        return None, None

    def _record_cycle_backlog_outcome(
        self, priority_id: str, *, status: str, reason: str | None
    ) -> None:
        entry, state = self._find_cycle_backlog_entry(priority_id)
        if not entry or not state:
            return
        normalized = str(status or "").strip().lower()
        if normalized == "discarded" and (reason or "").strip() in {"merge_failed", "max_iterations"}:
            normalized = "failed"
        if normalized not in {"done", "failed", "discarded"}:
            normalized = "failed" if normalized != "done" else "done"
        entry["status"] = normalized
        notes = state.get("notes")
        if isinstance(notes, list):
            note = f"backlog[{priority_id}]={normalized}"
            if reason:
                note = f"{note}({reason})"
            notes.append(note)

    def _record_cycle_conflict(self, conflict_id: str) -> None:
        token = str(conflict_id or "").strip()
        if not token:
            return
        if self._active_cycle_id and self._active_cycle_id in self._cycle_state:
            state = self._cycle_state[self._active_cycle_id]
            conflicts = state.get("conflict_ids")
            if isinstance(conflicts, set):
                conflicts.add(token)
        else:
            self._pending_cycle_conflicts.add(token)

    def _record_cycle_anomaly(self, label: str) -> None:
        token = _slugify(label)
        if not token:
            return
        if self._active_cycle_id and self._active_cycle_id in self._cycle_state:
            state = self._cycle_state[self._active_cycle_id]
            summary = state.get("summary")
            if isinstance(summary, dict):
                anomalies = summary.setdefault("anomalies", [])
                if isinstance(anomalies, list) and token not in anomalies:
                    anomalies.append(token)
                    notes = state.get("notes")
                    if isinstance(notes, list):
                        notes.append(f"anomaly={token}")
        else:
            if token not in self._pending_cycle_anomalies:
                self._pending_cycle_anomalies.append(token)

    def _mark_cycle_cooldown(self) -> None:
        if self._active_cycle_id and self._active_cycle_id in self._cycle_state:
            state = self._cycle_state[self._active_cycle_id]
            summary = state.get("summary")
            if isinstance(summary, dict):
                summary["cooldown"] = True
            notes = state.get("notes")
            if isinstance(notes, list):
                notes.append("cooldown=true")
        else:
            self._pending_cycle_cooldown = True

    def _finalize_cycle_summary(
        self,
        request: ArchitectRequest,
        *,
        result: str,
        reason: str | None = None,
        reflection_path: Path | None = None,
    ) -> None:
        state = self._cycle_state.get(request.architect_id)
        if not state:
            return
        summary = state.get("summary")
        if not isinstance(summary, dict):
            self._cycle_state.pop(request.architect_id, None)
            if self._active_cycle_id == request.architect_id:
                self._active_cycle_id = None
            return
        if summary.get("ended_at"):
            return
        if reflection_path is not None:
            reflections = summary.setdefault("reflections", [])
            if isinstance(reflections, list):
                rel = reflection_path.as_posix().lstrip("/")
                reflections.append(rel)
        summary["ended_at"] = self._now().isoformat()
        notes = state.get("notes")
        if isinstance(notes, list):
            result_note = f"result={result}"
            if reason:
                result_note = f"{result_note}:{reason}"
            notes.append(result_note)
            summary["notes"] = "; ".join(notes)
        else:
            summary["notes"] = f"result={result}" if not reason else f"result={result}:{reason}"

        summary["cooldown"] = bool(summary.get("cooldown", False))

        def _normalize_str_list(values: object) -> list[str]:
            result: list[str] = []
            if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
                for item in values:
                    text = str(item).strip()
                    if text:
                        result.append(text)
            return result

        summary["reflections"] = _normalize_str_list(summary.get("reflections"))
        summary["anomalies"] = sorted(dict.fromkeys(_normalize_str_list(summary.get("anomalies"))))

        backlog_attempts: list[dict[str, object]] = []
        seen_backlog: set[str] = set()
        for attempt in summary.get("backlog_attempts", []):
            if not isinstance(attempt, Mapping):
                continue
            entry_id = str(attempt.get("id", "")).strip()
            if not entry_id or entry_id in seen_backlog:
                continue
            status_value = str(attempt.get("status", "")).strip().lower()
            if status_value == "discarded" and str(attempt.get("reason", "")).strip() in {"merge_failed", "max_iterations"}:
                status_value = "failed"
            if status_value not in {"done", "failed", "discarded"}:
                status_value = "failed" if status_value != "done" else "done"
            backlog_attempts.append(
                {
                    "id": entry_id,
                    "text": str(attempt.get("text", "")).strip(),
                    "status": status_value,
                }
            )
            seen_backlog.add(entry_id)
        summary["backlog_attempts"] = backlog_attempts

        conflict_ids = state.get("conflict_ids")
        if isinstance(conflict_ids, set):
            backlog_index = state.get("backlog_index")
            if isinstance(backlog_index, dict):
                for priority_id in backlog_index.keys():
                    for conflict_id in self._conflict_index.get(priority_id, set()):
                        conflict_ids.add(conflict_id)
        else:
            conflict_ids = set()
        federation_conflicts: list[dict[str, object]] = []
        for conflict_id in sorted(conflict_ids):
            record = self._conflicts.get(conflict_id)
            if not isinstance(record, Mapping):
                continue
            peers = []
            variants = record.get("variants", [])
            if isinstance(variants, Sequence):
                for variant in variants:
                    if not isinstance(variant, Mapping):
                        continue
                    peer = str(variant.get("peer", "")).strip()
                    if peer:
                        peers.append(peer)
            peers = sorted(dict.fromkeys(peers))
            codex_state = record.get("codex") if isinstance(record.get("codex"), Mapping) else {}
            resolution_path = ""
            if isinstance(codex_state, Mapping):
                suggestion = codex_state.get("suggestion")
                if isinstance(suggestion, Mapping):
                    resolution_path = str(suggestion.get("path", "")).strip()
            status_value = str(record.get("status", "pending")).strip().lower()
            status_label = "resolved" if status_value in {"accepted", "separate"} else "unresolved"
            federation_conflicts.append(
                {
                    "id": conflict_id,
                    "peers": peers,
                    "status": status_label,
                    "resolution_path": resolution_path,
                }
            )
        summary["federation_conflicts"] = federation_conflicts

        valid, error = self._validate_cycle_summary(summary)
        stats = {
            "successes": sum(1 for item in backlog_attempts if item.get("status") == "done"),
            "failures": sum(
                1
                for item in backlog_attempts
                if item.get("status") in {"failed", "discarded"}
            ),
            "conflicts_resolved": sum(
                1 for entry in federation_conflicts if entry.get("status") == "resolved"
            ),
        }
        summary_path: Path | None = None
        failure_reason: str | None = None
        if not valid:
            failure_reason = error or "invalid_summary"
            self._handle_cycle_summary_failure(request, summary, failure_reason)
        else:
            try:
                summary_path = self._persist_cycle_summary(summary)
            except Exception as exc:  # pragma: no cover - defensive
                failure_reason = f"write_failed:{exc}"
                self._handle_cycle_summary_failure(request, summary, failure_reason)

        if summary_path is not None:
            rel_path = summary_path.as_posix().lstrip("/")
            ledger_payload = {
                "event": "architect_cycle_summary",
                "cycle": request.cycle_number,
                "cycle_id": summary["cycle_id"],
                "started_at": summary["started_at"],
                "ended_at": summary["ended_at"],
                "reflections": list(summary.get("reflections", [])),
                "backlog_attempts": backlog_attempts,
                "federation_conflicts": federation_conflicts,
                "cooldown": summary.get("cooldown", False),
                "anomalies": summary.get("anomalies", []),
                "notes": summary.get("notes", ""),
                "summary_path": rel_path,
                **stats,
            }
            self._emit_ledger_event(ledger_payload)
            pulse_payload = {
                "cycle": request.cycle_number,
                "cycle_id": summary["cycle_id"],
                "successes": stats["successes"],
                "failures": stats["failures"],
                "conflicts_resolved": stats["conflicts_resolved"],
                "summary_path": summary_path.as_posix(),
                "ended_at": summary["ended_at"],
            }
            self._publish_pulse(
                {
                    "timestamp": summary["ended_at"],
                    "source_daemon": "ArchitectDaemon",
                    "event_type": "architect_cycle_summary",
                    "priority": "info",
                    "payload": pulse_payload,
                }
            )
            self._update_cycle_entry(
                request.architect_id,
                summary_path=rel_path,
                summary_stats=dict(stats),
            )
            self._maybe_generate_trajectory(request)
        elif failure_reason:
            self._update_cycle_entry(
                request.architect_id,
                summary_error=failure_reason,
            )

        self._cycle_state.pop(request.architect_id, None)
        if self._active_cycle_id == request.architect_id:
            self._active_cycle_id = None
        self._save_session()

    def _validate_cycle_summary(
        self, summary: Mapping[str, object]
    ) -> tuple[bool, str | None]:
        required_keys = ["cycle_id", "started_at", "ended_at", "notes"]
        for key in required_keys:
            value = summary.get(key)
            if not isinstance(value, str):
                return False, f"invalid_{key}"
            if key != "notes" and not value.strip():
                return False, f"missing_{key}"
        if not isinstance(summary.get("cooldown"), bool):
            return False, "invalid_cooldown"
        reflections = summary.get("reflections")
        if not isinstance(reflections, list) or any(not isinstance(item, str) for item in reflections):
            return False, "invalid_reflections"
        anomalies = summary.get("anomalies")
        if not isinstance(anomalies, list) or any(not isinstance(item, str) for item in anomalies):
            return False, "invalid_anomalies"
        backlog = summary.get("backlog_attempts")
        if not isinstance(backlog, list):
            return False, "invalid_backlog"
        for attempt in backlog:
            if not isinstance(attempt, Mapping):
                return False, "invalid_backlog_entry"
            entry_id = attempt.get("id")
            status = attempt.get("status")
            if not isinstance(entry_id, str) or not entry_id.strip():
                return False, "invalid_backlog_id"
            if not isinstance(status, str) or status not in {"done", "failed", "discarded"}:
                return False, "invalid_backlog_status"
            if not isinstance(attempt.get("text"), str):
                return False, "invalid_backlog_text"
        conflicts = summary.get("federation_conflicts")
        if not isinstance(conflicts, list):
            return False, "invalid_conflicts"
        for conflict in conflicts:
            if not isinstance(conflict, Mapping):
                return False, "invalid_conflict_entry"
            conflict_id = conflict.get("id")
            status = conflict.get("status")
            peers = conflict.get("peers")
            if not isinstance(conflict_id, str) or not conflict_id.strip():
                return False, "invalid_conflict_id"
            if status not in {"resolved", "unresolved"}:
                return False, "invalid_conflict_status"
            if not isinstance(peers, list) or any(not isinstance(item, str) for item in peers):
                return False, "invalid_conflict_peers"
            if not isinstance(conflict.get("resolution_path"), str):
                return False, "invalid_conflict_path"
        return True, None

    def _persist_cycle_summary(self, summary: Mapping[str, object]) -> Path:
        ended_at = str(summary.get("ended_at", ""))
        timestamp = self._timestamp_for_cycle_filename(ended_at)
        path = self._cycle_dir / f"cycle_{timestamp}.json"
        counter = 0
        while path.exists():
            counter += 1
            path = self._cycle_dir / f"cycle_{timestamp}_{counter}.json"
        path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _timestamp_for_cycle_filename(self, ended_at: str) -> str:
        try:
            normalized = ended_at.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
        except Exception:
            dt = self._now()
        return dt.strftime("%Y%m%d_%H%M%S")

    def _handle_cycle_summary_failure(
        self, request: ArchitectRequest, summary: Mapping[str, object], reason: str
    ) -> None:
        payload = {
            "event": "architect_cycle_summary_failed",
            "cycle": request.cycle_number,
            "cycle_id": summary.get("cycle_id", ""),
            "reason": reason,
        }
        self._emit_ledger_event(payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_cycle_summary_failed",
                "priority": "warning",
                "payload": {
                    "cycle": request.cycle_number,
                    "cycle_id": summary.get("cycle_id", ""),
                    "reason": reason,
                },
            }
        )

    def _maybe_generate_trajectory(self, request: ArchitectRequest) -> None:
        interval = max(1, int(self._trajectory_interval or 1))
        cycle_number = int(request.cycle_number or 0)
        if cycle_number <= 0:
            return
        if cycle_number % interval != 0:
            return
        self._emit_trajectory_start(cycle_number, interval)
        try:
            report = self._build_trajectory_report(interval=interval)
        except ValueError as exc:
            reason = str(exc) or "trajectory_build_failed"
            self._handle_trajectory_failure(cycle_number, reason)
            return
        valid, error = self._validate_trajectory_report(report)
        if not valid:
            self._handle_trajectory_failure(
                cycle_number, error or "invalid_trajectory_report"
            )
            return
        try:
            report_path = self._persist_trajectory_report(report)
        except Exception as exc:  # pragma: no cover - defensive guard
            self._handle_trajectory_failure(cycle_number, f"write_failed:{exc}")
            return
        self._handle_trajectory_success(report, report_path)

    def _emit_trajectory_start(self, cycle_number: int, interval: int) -> None:
        timestamp = self._now().isoformat()
        ledger_payload = {
            "event": "architect_trajectory_start",
            "cycle": cycle_number,
            "interval": interval,
        }
        self._emit_ledger_event(ledger_payload)
        self._publish_pulse(
            {
                "timestamp": timestamp,
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_trajectory_start",
                "priority": "info",
                "payload": {"cycle": cycle_number, "interval": interval},
            }
        )

    def _emit_trajectory_warning(
        self, message: str, *, detail: Mapping[str, object] | None = None
    ) -> None:
        payload: dict[str, object] = {"event": "architect_trajectory_warning", "message": message}
        if detail:
            for key, value in detail.items():
                payload[key] = value
        self._emit_ledger_event(payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_trajectory_warning",
                "priority": "warning",
                "payload": dict(payload),
            }
        )

    def _collect_recent_cycles(self, limit: int) -> list[dict[str, object]]:
        try:
            files = sorted(
                self._cycle_dir.glob("cycle_*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            files = []
        if limit > 0:
            files = files[:limit]
        if limit > 0 and len(files) < limit:
            self._emit_trajectory_warning(
                "cycle_history_shortfall",
                detail={"expected": limit, "available": len(files)},
            )
        records: list[dict[str, object]] = []
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self._emit_trajectory_warning(
                    "cycle_summary_unreadable",
                    detail={"summary_path": path.as_posix()},
                )
                continue
            if not isinstance(data, Mapping):
                self._emit_trajectory_warning(
                    "cycle_summary_invalid",
                    detail={"summary_path": path.as_posix()},
                )
                continue
            record = dict(data)
            record["__path__"] = path
            records.append(record)
        if not records:
            return []
        records.sort(
            key=lambda item: self._parse_iso_timestamp(str(item.get("ended_at", "")))
        )
        return records

    def _parse_iso_timestamp(self, value: str) -> datetime:
        text = value.strip()
        if not text:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            normalized = text.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    def _build_trajectory_report(self, *, interval: int) -> dict[str, object]:
        cycles = self._collect_recent_cycles(interval)
        if not cycles:
            raise ValueError("no_cycle_summaries")
        cycle_paths: list[str] = []
        started_values: list[str] = []
        ended_values: list[str] = []
        total_successes = 0
        total_failures = 0
        failure_counts: dict[str, int] = {}
        failure_labels: dict[str, str] = {}
        conflict_counts: dict[str, int] = {}
        backlog_status: dict[str, str] = {}
        planned_priorities: dict[str, str] = {}
        conflict_cycles = 0
        total_conflicts = 0
        for record in cycles:
            path_obj = record.get("__path__")
            if isinstance(path_obj, Path):
                cycle_paths.append(path_obj.as_posix())
            started = str(record.get("started_at", "")).strip()
            ended = str(record.get("ended_at", "")).strip()
            if started:
                started_values.append(started)
            if ended:
                ended_values.append(ended)
            backlog = record.get("backlog_attempts", [])
            if isinstance(backlog, list):
                for attempt in backlog:
                    if not isinstance(attempt, Mapping):
                        continue
                    status = str(attempt.get("status", "")).strip().lower()
                    text = str(attempt.get("text", "")).strip()
                    if not text:
                        text = str(attempt.get("id", "")).strip()
                    canonical = _canonicalize_priority_text(text) if text else ""
                    if not canonical:
                        canonical = str(attempt.get("id", "")).strip()
                    if not canonical:
                        continue
                    label = text or canonical
                    if status == "done":
                        total_successes += 1
                        backlog_status[canonical] = "done"
                    elif status in {"failed", "discarded"}:
                        total_failures += 1
                        if backlog_status.get(canonical) != "done":
                            backlog_status[canonical] = "discarded"
                        failure_counts[canonical] = failure_counts.get(canonical, 0) + 1
                        failure_labels.setdefault(canonical, label)
            conflicts = record.get("federation_conflicts", [])
            if isinstance(conflicts, list):
                unresolved_in_cycle = 0
                for conflict in conflicts:
                    if not isinstance(conflict, Mapping):
                        continue
                    status_value = str(conflict.get("status", "")).strip().lower()
                    if status_value == "resolved":
                        continue
                    label = str(conflict.get("id", "")).strip()
                    if not label:
                        continue
                    unresolved_in_cycle += 1
                    conflict_counts[label] = conflict_counts.get(label, 0) + 1
                if unresolved_in_cycle:
                    conflict_cycles += 1
                    total_conflicts += unresolved_in_cycle
            reflections = record.get("reflections", [])
            if isinstance(reflections, list):
                for ref in reflections:
                    if not isinstance(ref, str):
                        continue
                    ref_path = Path(ref)
                    if not ref_path.is_absolute():
                        ref_path = Path("/") / ref.lstrip("/")
                    if not ref_path.exists():
                        self._emit_trajectory_warning(
                            "reflection_missing",
                            detail={"reflection_path": ref},
                        )
                        continue
                    try:
                        reflection_data = json.loads(ref_path.read_text(encoding="utf-8"))
                    except Exception:
                        self._emit_trajectory_warning(
                            "reflection_invalid",
                            detail={"reflection_path": ref_path.as_posix()},
                        )
                        continue
                    priorities = reflection_data.get("next_priorities")
                    if isinstance(priorities, list):
                        for item in priorities:
                            if not isinstance(item, str):
                                continue
                            text_value = item.strip()
                            if not text_value:
                                continue
                            canonical = _canonicalize_priority_text(text_value)
                            if not canonical:
                                canonical = text_value.lower()
                            planned_priorities.setdefault(canonical, text_value)
        total_attempts = total_successes + total_failures
        success_rate = (
            float(round(total_successes / total_attempts, 4)) if total_attempts else 0.0
        )
        failure_rate = (
            float(round(total_failures / total_attempts, 4)) if total_attempts else 0.0
        )
        conflict_rate = (
            float(round(conflict_cycles / len(cycles), 4)) if cycles else 0.0
        )
        recurring_labels: list[str] = []
        for canonical, count in failure_counts.items():
            if count > 1:
                recurring_labels.append(failure_labels.get(canonical, canonical))
        for label, count in conflict_counts.items():
            if count > 1:
                recurring_labels.append(label)
        recurring = sorted(dict.fromkeys(recurring_labels))
        planned_total = len(planned_priorities)
        completed = sum(
            1 for key in planned_priorities if backlog_status.get(key) == "done"
        )
        discarded = sum(
            1 for key in planned_priorities if backlog_status.get(key) == "discarded"
        )
        attempts_note = (
            f"{total_successes}/{total_attempts}"
            if total_attempts
            else "0/0"
        )
        followthrough_note = (
            f"{completed}/{planned_total} completed"
            if planned_total
            else "no planned priorities"
        )
        regression_note = ", ".join(recurring) if recurring else "none"
        notes = (
            f"Codex summary: {len(cycles)} cycles, success {success_rate * 100:.0f}%"
            f" ({attempts_note}), follow-through {followthrough_note}, "
            f"recurring regressions: {regression_note}."
        )
        started_at = started_values[0] if started_values else self._now().isoformat()
        ended_at = ended_values[-1] if ended_values else self._now().isoformat()
        report = {
            "trajectory_id": str(uuid4()),
            "started_at": started_at,
            "ended_at": ended_at,
            "cycles_included": cycle_paths,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "conflict_rate": conflict_rate,
            "recurring_regressions": recurring,
            "priority_followthrough": {
                "planned": int(planned_total),
                "completed": int(completed),
                "discarded": int(discarded),
            },
            "notes": notes,
            "total_conflicts": int(total_conflicts),
            "current_failure_streak": int(self._failure_streak),
            "priority_failures": [
                {
                    "canonical": canonical,
                    "label": failure_labels.get(canonical, canonical),
                    "count": int(count),
                }
                for canonical, count in sorted(failure_counts.items())
            ],
            "priority_status": dict(backlog_status),
        }
        return report

    def _validate_trajectory_report(
        self, report: Mapping[str, object]
    ) -> tuple[bool, str | None]:
        required = ("trajectory_id", "started_at", "ended_at", "notes")
        for key in required:
            value = report.get(key)
            if not isinstance(value, str):
                return False, f"invalid_{key}"
            if key != "notes" and not value.strip():
                return False, f"missing_{key}"
        cycles = report.get("cycles_included")
        if not isinstance(cycles, list) or not cycles:
            return False, "invalid_cycles"
        for item in cycles:
            if not isinstance(item, str) or not item.strip():
                return False, "invalid_cycle_path"
        success_rate = report.get("success_rate")
        failure_rate = report.get("failure_rate")
        if not isinstance(success_rate, (int, float)):
            return False, "invalid_success_rate"
        if not isinstance(failure_rate, (int, float)):
            return False, "invalid_failure_rate"
        if success_rate < 0 or failure_rate < 0:
            return False, "negative_rates"
        regressions = report.get("recurring_regressions")
        if not isinstance(regressions, list):
            return False, "invalid_regressions"
        if any(not isinstance(item, str) for item in regressions):
            return False, "invalid_regression_entry"
        followthrough = report.get("priority_followthrough")
        if not isinstance(followthrough, Mapping):
            return False, "invalid_followthrough"
        for key in ("planned", "completed", "discarded"):
            value = followthrough.get(key)
            if not isinstance(value, int) or value < 0:
                return False, f"invalid_followthrough_{key}"
        return True, None

    def _persist_trajectory_report(self, report: Mapping[str, object]) -> Path:
        ended_at = str(report.get("ended_at", ""))
        timestamp = self._timestamp_for_cycle_filename(ended_at)
        path = self._trajectory_dir / f"trajectory_{timestamp}.json"
        counter = 0
        while path.exists():
            counter += 1
            path = self._trajectory_dir / f"trajectory_{timestamp}_{counter}.json"
        path.write_text(json.dumps(dict(report), indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _handle_trajectory_success(
        self, report: Mapping[str, object], report_path: Path
    ) -> None:
        notes_value = str(report.get("notes", ""))
        rel_path = report_path.as_posix().lstrip("/")
        self._last_trajectory_path = rel_path
        self._last_trajectory_id = str(report.get("trajectory_id", "")) or None
        self._last_trajectory_notes = notes_value or None
        ledger_payload = {"event": "architect_trajectory_report", **dict(report)}
        ledger_payload["report_path"] = rel_path
        self._emit_ledger_event(ledger_payload)
        pulse_payload = {
            "timestamp": str(report.get("ended_at", self._now().isoformat())),
            "source_daemon": "ArchitectDaemon",
            "event_type": "architect_trajectory_report",
            "priority": "info",
            "payload": {
                "trajectory_id": report.get("trajectory_id"),
                "success_rate": report.get("success_rate"),
                "failure_rate": report.get("failure_rate"),
                "recurring_regressions": list(report.get("recurring_regressions", [])),
                "priority_followthrough": dict(
                    report.get("priority_followthrough", {})
                ),
                "cycles_included": list(report.get("cycles_included", [])),
                "report_path": report_path.as_posix(),
            },
        }
        self._publish_pulse(pulse_payload)
        self._apply_trajectory_adjustments(report)
        self._save_session()

    def _handle_trajectory_failure(self, cycle_number: int, reason: str) -> None:
        payload = {
            "event": "architect_trajectory_failed",
            "cycle": cycle_number,
            "reason": str(reason),
        }
        self._emit_ledger_event(payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_trajectory_failed",
                "priority": "warning",
                "payload": {"cycle": cycle_number, "reason": str(reason)},
            }
        )

    def _apply_trajectory_adjustments(self, report: Mapping[str, object]) -> None:
        if not isinstance(report, Mapping):
            return
        overrides = dict(self._steering_overrides)
        reason_parts: list[str] = []
        settings: dict[str, object] = {}
        changed = False

        success_rate = float(report.get("success_rate", 0.0) or 0.0)
        base_reflection = max(1, int(self._default_reflection_interval))
        if success_rate < self._success_rate_threshold:
            if base_reflection > 1:
                target_reflection = max(1, base_reflection // 2)
            else:
                target_reflection = 1
            if overrides.get("reflection_interval") != target_reflection:
                overrides["reflection_interval"] = target_reflection
                reason_parts.append(
                    (
                        f"Success rate {success_rate:.0%} below"
                        f" {self._success_rate_threshold:.0%}: reflection interval set to {target_reflection}"
                    )
                )
                settings["reflection_interval"] = target_reflection
                changed = True

        failure_streak_value = max(
            int(report.get("current_failure_streak", 0) or 0),
            int(self._failure_streak or 0),
        )
        if failure_streak_value > self._failure_streak_threshold:
            base_cooldown = max(self._default_cooldown_period, 0.0)
            target_cooldown = max(
                int(base_cooldown * 1.5),
                int(base_cooldown) + 6 * 60 * 60,
            )
            if overrides.get("cooldown_period") != target_cooldown:
                overrides["cooldown_period"] = target_cooldown
                hours = max(1, int(round(target_cooldown / 3600)))
                reason_parts.append(
                    (
                        f"Failure streak {failure_streak_value} exceeded"
                        f" {self._failure_streak_threshold}: cooldown extended to {hours}h"
                    )
                )
                settings["cooldown_period"] = target_cooldown
                changed = True

        conflict_rate = float(report.get("conflict_rate", 0.0) or 0.0)
        conflict_escalated = False
        if (
            conflict_rate > self._conflict_rate_threshold
            and not overrides.get("conflict_priority")
        ):
            overrides["conflict_priority"] = True
            reason_parts.append(
                (
                    f"Conflict rate {conflict_rate:.0%} above"
                    f" {self._conflict_rate_threshold:.0%}: conflict resolution escalated"
                )
            )
            settings["conflict_priority"] = True
            changed = True
            conflict_escalated = True

        status_map: dict[str, str] = {}
        raw_status = report.get("priority_status", {})
        if isinstance(raw_status, Mapping):
            for key, value in raw_status.items():
                canonical_key = _canonicalize_priority_text(str(key))
                if canonical_key:
                    status_map[canonical_key] = str(value)
        failure_entries = report.get("priority_failures", [])
        label_map: dict[str, str] = {}
        new_low_confidence = set(self._low_confidence_priorities)
        threshold_failures = max(2, self._failure_streak_threshold)
        if isinstance(failure_entries, Sequence):
            for item in failure_entries:
                if not isinstance(item, Mapping):
                    continue
                canonical = _canonicalize_priority_text(str(item.get("canonical", "")))
                if not canonical:
                    continue
                label_map[canonical] = str(item.get("label", canonical))
                try:
                    count = int(item.get("count", 0))
                except (TypeError, ValueError):
                    count = 0
                status_value = status_map.get(canonical, "")
                if count >= threshold_failures and status_value != "done":
                    new_low_confidence.add(canonical)

        priority_changed = new_low_confidence != self._low_confidence_priorities
        reorder_changed = self._update_priority_confidence(new_low_confidence)
        low_confidence_list = sorted(new_low_confidence)
        if priority_changed or reorder_changed:
            self._low_confidence_priorities = new_low_confidence
            labels = [label_map.get(item, item) for item in low_confidence_list]
            self._emit_priority_reordered_event(labels)
            self._save_priority_backlog()
            settings["low_confidence"] = low_confidence_list

        if not changed:
            if priority_changed or reorder_changed:
                self._trajectory_adjustment_settings["low_confidence"] = low_confidence_list
            return

        self._steering_overrides = overrides
        self._apply_steering_overrides()
        if conflict_escalated:
            self._escalate_conflict_resolution()
        reason_text = "; ".join(reason_parts)
        if reason_text:
            self._trajectory_adjustment_reason = reason_text
            self._trajectory_adjustment_settings = dict(settings)
            self._emit_trajectory_adjustment(reason_text, settings)

    def _emit_trajectory_adjustment(
        self, reason: str, settings: Mapping[str, object]
    ) -> None:
        payload = {
            "event": "architect_trajectory_adjusted",
            "reason": reason,
            "settings": dict(settings),
        }
        self._emit_ledger_event(payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_trajectory_adjusted",
                "priority": "info",
                "payload": {"reason": reason, "settings": dict(settings)},
            }
        )

    def _emit_priority_reordered_event(self, labels: Sequence[str]) -> None:
        normalized = [str(label) for label in labels if str(label).strip()]
        payload = {
            "event": "architect_priority_reordered",
            "low_confidence": normalized,
        }
        self._emit_ledger_event(payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_priority_reordered",
                "priority": "info",
                "payload": {"low_confidence": normalized},
            }
        )

    def _update_priority_confidence(self, low_confidence: set[str]) -> bool:
        low_confidence = {item for item in low_confidence if item}
        changed = False
        normal_entries: list[dict[str, object]] = []
        low_pending: list[dict[str, object]] = []
        new_confidence_map: dict[str, str] = {}
        for entry in list(self._priority_active):
            if not isinstance(entry, MutableMapping):
                continue
            text_value = str(entry.get("text", ""))
            canonical = _canonicalize_priority_text(text_value)
            status_value = str(entry.get("status", "pending")).strip().lower()
            is_low = canonical in low_confidence
            if is_low:
                if entry.get("confidence") != "low":
                    entry["confidence"] = "low"
                    changed = True
                if status_value == "pending":
                    low_pending.append(entry)
                else:
                    normal_entries.append(entry)
                entry_id = entry.get("id")
                if isinstance(entry_id, str):
                    new_confidence_map[entry_id] = "low"
            else:
                if entry.pop("confidence", None) is not None:
                    changed = True
                normal_entries.append(entry)
        new_order = normal_entries + low_pending
        if new_order != list(self._priority_active):
            self._priority_active[:] = new_order
            changed = True
        self._priority_index = {
            entry["id"]: entry
            for entry in self._priority_active
            if isinstance(entry, Mapping) and "id" in entry
        }
        self._priority_confidence = new_confidence_map
        return changed

    def _escalate_conflict_resolution(self) -> None:
        if not self._autonomy_enabled:
            return
        for conflict_id, record in list(self._conflicts.items()):
            if not isinstance(record, Mapping):
                continue
            status = str(record.get("status", "pending")).strip().lower()
            if status not in {"pending", "rejected"}:
                continue
            variants = record.get("variants", [])
            if not isinstance(variants, Sequence):
                continue
            variant_list = list(variants)
            if len(variant_list) < 2:
                continue
            try:
                self._process_conflict_resolution(conflict_id)
            except Exception:
                continue

    def reset_trajectory_adjustments(self, *, actor: str | None = None) -> None:
        actor_name = actor or "unknown"
        self._steering_overrides = {
            "reflection_interval": None,
            "cooldown_period": None,
            "conflict_priority": False,
        }
        self._low_confidence_priorities = set()
        self._priority_confidence = {}
        self._trajectory_adjustment_reason = ""
        self._trajectory_adjustment_settings = {}
        self._apply_steering_overrides()
        self._update_priority_confidence(set())
        if self._priority_active:
            self._save_priority_backlog()
        payload = {
            "event": "architect_adjustments_reset",
            "actor": actor_name,
        }
        self._emit_ledger_event(payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_adjustments_reset",
                "priority": "info",
                "payload": {"actor": actor_name},
            }
        )
        self._save_session()

    def _recent_cycle_history(self, limit: int = 10) -> list[dict[str, object]]:
        expansions = [
            dict(item)
            for item in self._cycle_history
            if item.get("type") != "reflection"
        ]
        return expansions[-limit:]

    def _draft_cycle_request(self, cycle_number: int) -> ArchitectRequest:
        priority_entry = self._select_backlog_priority(cycle_number)
        if priority_entry is not None:
            text = priority_entry.get("text", "").strip()
            description = f"Backlog priority: {text}" if text else "Backlog priority"
            details = {
                "description": description,
                "cycle_number": cycle_number,
                "trigger": "scheduled",
                "throttled": self._throttled,
                "priority_id": priority_entry.get("id", ""),
                "priority_text": text,
                "priority_status": priority_entry.get("status", "in_progress"),
                "priority_origin": "reflection_backlog",
            }
            return self._create_request("expand", description, None, details)

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
        window_end = cycle_number
        history = self._recent_cycle_history(limit=10)
        details = {
            "topic": topic,
            "cycle_number": cycle_number,
            "window_start": window_start,
            "window_end": window_end,
            "window_size": window_end - window_start + 1,
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
                "event": "architect_reflection_start",
                "cycle": cycle_number,
                "cycle_range": {"start": window_start, "end": window_end},
                "prompt": prompt_ref,
            }
        )
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_reflection_start",
                "priority": "info",
                "payload": {
                    "cycle": cycle_number,
                    "prompt": prompt_ref,
                    "cycle_range": {"start": window_start, "end": window_end},
                },
            }
        )
        return request

    def _enter_cooldown(self, reason: str, *, timestamp: float | None = None) -> None:
        now_ts = timestamp if timestamp is not None else self._now().timestamp()
        self._cooldown_until = now_ts + max(0.0, self._cooldown_period)
        cooldown_iso = datetime.fromtimestamp(
            self._cooldown_until, tz=timezone.utc
        ).isoformat()
        self._mark_cycle_cooldown()
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
        self._record_cycle_anomaly("throttled")
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
        label = ""
        if isinstance(payload, Mapping):
            raw_label = (
                payload.get("anomaly")
                or payload.get("detail")
                or payload.get("type")
                or ""
            )
            label = str(raw_label).strip()
        if not label:
            label = str(event.get("event_type", "monitor_alert"))
        self._record_cycle_anomaly(label)
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
        federate_reflections = self._coerce_bool(
            payload.get("federate_reflections", ARCHITECT_FEDERATE_REFLECTIONS)
        )
        federate_priorities = self._coerce_bool(
            payload.get("federate_priorities", ARCHITECT_FEDERATE_PRIORITIES)
        )
        trajectory_interval = max(
            1,
            self._coerce_int(
                payload.get(
                    "architect_trajectory_interval",
                    self._trajectory_interval,
                ),
                self._trajectory_interval,
            ),
        )
        return {
            "codex_mode": mode,
            "codex_interval": codex_interval,
            "architect_interval": architect_interval,
            "architect_jitter": architect_jitter,
            "codex_max_iterations": max_iterations,
            "federation_peer_name": peer_name,
            "federation_peers": tuple(peers),
            "architect_autonomy": autonomy,
            "federate_reflections": federate_reflections,
            "federate_priorities": federate_priorities,
            "architect_trajectory_interval": trajectory_interval,
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

    def _apply_steering_overrides(self) -> None:
        reflection_override = self._steering_overrides.get("reflection_interval")
        if isinstance(reflection_override, int) and reflection_override > 0:
            self._reflection_interval = max(1, int(reflection_override))
        else:
            self._reflection_interval = max(1, int(self._default_reflection_interval))
            self._steering_overrides["reflection_interval"] = None
        cooldown_override = self._steering_overrides.get("cooldown_period")
        if isinstance(cooldown_override, (int, float)) and float(cooldown_override) > 0:
            self._cooldown_period = float(cooldown_override)
        else:
            self._cooldown_period = float(self._default_cooldown_period)
            self._steering_overrides["cooldown_period"] = None
        conflict_override = bool(self._steering_overrides.get("conflict_priority"))
        self._steering_overrides["conflict_priority"] = conflict_override
        self._conflict_priority_escalated = conflict_override

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
        self._federate_reflections = bool(
            snapshot.get("federate_reflections", ARCHITECT_FEDERATE_REFLECTIONS)
        )
        self._federate_priorities = bool(
            snapshot.get("federate_priorities", ARCHITECT_FEDERATE_PRIORITIES)
        )
        try:
            trajectory_interval = int(
                snapshot.get(
                    "architect_trajectory_interval", self._trajectory_interval
                )
            )
        except (TypeError, ValueError):
            trajectory_interval = self._trajectory_interval
        if trajectory_interval <= 0:
            trajectory_interval = self._trajectory_interval
        self._trajectory_interval = max(1, trajectory_interval)
        self._apply_steering_overrides()

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
            "federate_reflections": self._federate_reflections,
            "federate_priorities": self._federate_priorities,
            "architect_trajectory_interval": self._trajectory_interval,
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
        if event_type == "architect_backlog_action":
            self._handle_backlog_action(normalized)
            return
        if event_type == "architect_backlog_shared":
            self._handle_federated_backlog(event, normalized)
            return
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
        if event_type == "architect_reset_adjustments":
            self.reset_trajectory_adjustments(
                actor=str(source) if isinstance(source, str) else None
            )
            return
        if source == "DriverManager" and event_type == "driver_failure":
            self.request_repair("driver_failure")

    def _handle_federated_backlog(
        self, event: Mapping[str, object], normalized: Mapping[str, object]
    ) -> None:
        if not self._federate_priorities:
            return
        peer = str(
            normalized.get("source_peer")
            or event.get("source_peer")
            or ""
        ).strip()
        if not peer or peer.lower() == "local":
            return
        if self._federation_peer_name and peer == self._federation_peer_name:
            return
        try:
            verified = bool(pulse_bus.verify(event))
        except Exception:
            verified = False
        if not verified:
            self._emit_backlog_invalid(peer)
            return
        payload = normalized.get("payload")
        if not isinstance(payload, Mapping):
            return
        entries = self._extract_remote_priorities(payload)
        diff = payload.get("diff") if isinstance(payload.get("diff"), Mapping) else None
        timestamp = str(normalized.get("timestamp", self._now().isoformat()))
        self._update_peer_backlog_entries(peer, entries, timestamp, verified)
        stored_path = self._store_peer_backlog(
            peer,
            entries,
            diff,
            verified=verified,
            event_timestamp=timestamp,
        )
        self._reconcile_federated_priorities()
        self._save_priority_backlog(share=False)
        self._emit_backlog_received(peer, entries, diff, verified, stored_path)

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
        elif event == "self_reflection":
            request = self._match_request(normalized.get("request_id"))
            if request:
                self._finalize_reflection(request, normalized)

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
            window_size = 10
            try:
                window_size = int(request.details.get("window_size", window_size))
            except Exception:
                window_size = 10
            lines.append("Reflection Prompt:")
            lines.append(f"Review the last {window_size} Codex cycles.")
            lines.append("Summarize outcomes (success, failure, veil, cooldown).")
            lines.append("Identify regressions or recurring issues.")
            lines.append("Suggest next-step priorities.")
            lines.append("Respond in JSON only using this schema:")
            lines.append("{")
            lines.append('  "summary": "string",')
            lines.append('  "successes": ["string"],')
            lines.append('  "failures": ["string"],')
            lines.append('  "regressions": ["string"],')
            lines.append('  "next_priorities": ["string"]')
            lines.append("}")
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
        priority_id = request.details.get("priority_id")
        cycle_number = int(request.cycle_number or 0)
        if isinstance(priority_id, str) and priority_id:
            status_value = "done" if merged else "discarded"
            reason_value = None if merged else "merge_failed"
            self._finalize_priority(
                priority_id,
                status=status_value,
                cycle=cycle_number,
                reason=reason_value,
            )
        summary_reason = None if merged else "merge_failed"
        self._finalize_cycle_summary(request, result=status, reason=summary_reason)
        self._prefix_index.pop(request.codex_prefix, None)

    def _finalize_reflection(
        self, request: ArchitectRequest, entry: Mapping[str, object]
    ) -> None:
        raw_output = entry.get("reflection", entry.get("output"))
        reflection, error = self._parse_reflection_output(raw_output)
        if reflection is None:
            reason = error or "invalid_reflection_output"
            self._record_reflection_failure(request, reason, raw_output)
            return

        path = self._persist_reflection(request, reflection)
        summary = str(reflection["summary"]).strip()
        next_priorities = list(reflection["next_priorities"])
        window_start = int(request.details.get("window_start", request.cycle_number))
        window_end = int(request.details.get("window_end", request.cycle_number))
        cycle_range = {"start": window_start, "end": window_end}
        rel_path = path.as_posix().lstrip("/")
        completed_at = self._now().isoformat()

        created_priorities = self._register_reflection_priorities(next_priorities)
        if created_priorities:
            priority_ids = [entry["id"] for entry in created_priorities]
            priority_texts = [entry["text"] for entry in created_priorities]
            self._emit_ledger_event(
                {
                    "event": "architect_priorities_parsed",
                    "reflection_path": rel_path,
                    "count": len(created_priorities),
                    "priority_ids": list(priority_ids),
                    "priorities": list(priority_texts),
                }
            )
            self._publish_pulse(
                {
                    "timestamp": completed_at,
                    "source_daemon": "ArchitectDaemon",
                    "event_type": "architect_priorities_parsed",
                    "priority": "info",
                    "payload": {
                        "reflection_path": path.as_posix(),
                        "count": len(created_priorities),
                        "priority_ids": list(priority_ids),
                        "priorities": list(priority_texts),
                    },
                }
            )

        request.status = "completed"
        request.last_error = None
        self._last_reflection_summary = summary
        self._last_reflection_path = rel_path
        self._update_cycle_entry(
            request.architect_id,
            status="completed",
            result="recorded",
            completed_at=completed_at,
            summary=summary,
            reflection_path=rel_path,
            next_priorities=list(next_priorities),
        )

        ledger_payload = {
            "event": "architect_reflection",
            "architect_id": request.architect_id,
            "cycle": request.cycle_number,
            "cycle_range": dict(cycle_range),
            "file": rel_path,
            "summary": summary,
            "next_priorities": list(next_priorities),
            "successes": list(reflection["successes"]),
            "failures": list(reflection["failures"]),
            "regressions": list(reflection["regressions"]),
            "federated": self._federate_reflections,
        }
        self._emit_ledger_event(ledger_payload)

        pulse_payload: dict[str, object] = {
            "cycle": request.cycle_number,
            "cycle_range": dict(cycle_range),
            "summary": summary,
            "next_priorities": list(next_priorities),
            "successes": list(reflection["successes"]),
            "failures": list(reflection["failures"]),
            "regressions": list(reflection["regressions"]),
            "file": path.as_posix(),
            "federated": self._federate_reflections,
        }
        if self._federate_reflections:
            pulse_payload["peers"] = list(self._federation_peers)
            if self._federation_peer_name:
                pulse_payload["peer_name"] = self._federation_peer_name

        self._publish_pulse(
            {
                "timestamp": completed_at,
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_reflection_complete",
                "priority": "info",
                "payload": pulse_payload,
            }
        )
        self._finalize_cycle_summary(
            request,
            result="reflection_recorded",
            reason=None,
            reflection_path=path,
        )
        self._prefix_index.pop(request.codex_prefix, None)

    def _record_reflection_failure(
        self, request: ArchitectRequest, reason: str, raw_output: object
    ) -> None:
        request.status = "failed"
        self._last_reflection_summary = None
        self._last_reflection_path = None
        self._update_cycle_entry(
            request.architect_id,
            status="failed",
            error=reason,
            failed_at=self._now().isoformat(),
        )
        payload = {
            "event": "architect_reflection_failed",
            "architect_id": request.architect_id,
            "cycle": request.cycle_number,
            "reason": reason,
        }
        if raw_output is not None:
            payload["raw_output_type"] = type(raw_output).__name__
        self._emit_ledger_event(payload)
        self._publish_pulse(
            {
                "timestamp": self._now().isoformat(),
                "source_daemon": "ArchitectDaemon",
                "event_type": "architect_reflection_failed",
                "priority": "warning",
                "payload": {"cycle": request.cycle_number, "reason": reason},
            }
        )
        self._finalize_cycle_summary(
            request,
            result="reflection_failed",
            reason=reason,
            reflection_path=None,
        )
        self._prefix_index.pop(request.codex_prefix, None)

    def _persist_reflection(
        self, request: ArchitectRequest, reflection: Mapping[str, object]
    ) -> Path:
        timestamp = self._now().strftime("%Y%m%d_%H%M%S")
        stem = f"reflection_{timestamp}"
        path = self._reflection_dir / f"{stem}.json"
        counter = 0
        while path.exists():
            counter += 1
            path = self._reflection_dir / f"{stem}_{counter}.json"
        payload = {
            "summary": reflection["summary"],
            "successes": list(reflection["successes"]),
            "failures": list(reflection["failures"]),
            "regressions": list(reflection["regressions"]),
            "next_priorities": list(reflection["next_priorities"]),
            "architect_id": request.architect_id,
            "cycle": request.cycle_number,
            "cycle_range": {
                "start": int(request.details.get("window_start", request.cycle_number)),
                "end": int(request.details.get("window_end", request.cycle_number)),
            },
            "generated_at": self._now().isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _parse_reflection_output(
        self, payload: object
    ) -> tuple[dict[str, object] | None, str | None]:
        if isinstance(payload, Mapping):
            data = dict(payload)
        elif isinstance(payload, str):
            text = payload.strip()
            if not text:
                return None, "empty_reflection_output"
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                return None, f"json_decode_error:{exc.msg}"
            if not isinstance(parsed, Mapping):
                return None, "reflection_not_object"
            data = dict(parsed)
        else:
            return None, "reflection_not_object"

        required = [
            "summary",
            "successes",
            "failures",
            "regressions",
            "next_priorities",
        ]
        for key in required:
            if key not in data:
                return None, f"missing_{key}"

        summary = data["summary"]
        if not isinstance(summary, str):
            summary = str(summary)

        def _normalize_list(name: str) -> list[str] | None:
            value = data.get(name)
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                return None
            result: list[str] = []
            for item in value:
                text = str(item).strip()
                if text:
                    result.append(text)
            return result

        successes = _normalize_list("successes")
        failures = _normalize_list("failures")
        regressions = _normalize_list("regressions")
        priorities = _normalize_list("next_priorities")
        if any(value is None for value in (successes, failures, regressions, priorities)):
            return None, "invalid_list_field"

        normalized: dict[str, object] = {
            "summary": summary.strip() or summary,
            "successes": successes or [],
            "failures": failures or [],
            "regressions": regressions or [],
            "next_priorities": priorities or [],
        }
        return normalized, None

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
            priority_id = request.details.get("priority_id")
            cycle_number = int(request.cycle_number or 0)
            if isinstance(priority_id, str) and priority_id:
                self._finalize_priority(
                    priority_id,
                    status="discarded",
                    cycle=cycle_number,
                    reason=reason or "max_iterations",
                )
            self._finalize_cycle_summary(
                request,
                result="failed",
                reason=reason or "max_iterations",
                reflection_path=None,
            )
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
        normalized: dict[str, object] = {
            "timestamp": str(event.get("timestamp", self._now().isoformat())),
            "source": source,
            "event_type": event_type,
        }
        priority = event.get("priority")
        if isinstance(priority, str):
            normalized["priority"] = priority
        source_peer = event.get("source_peer")
        if isinstance(source_peer, str) and source_peer:
            normalized["source_peer"] = source_peer
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
            "reflection",
            "output",
            "result",
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
    status.setdefault("last_trajectory_path", "")
    status.setdefault("last_trajectory_id", "")
    status.setdefault("last_trajectory_notes", "")
    try:
        interval_value = int(status.get("trajectory_interval", ARCHITECT_TRAJECTORY_INTERVAL))
    except (TypeError, ValueError):
        interval_value = ARCHITECT_TRAJECTORY_INTERVAL
    status["trajectory_interval"] = max(1, interval_value)
    reason_value = status.get("trajectory_adjustment_reason", "")
    status["trajectory_adjustment_reason"] = str(reason_value) if reason_value else ""
    settings_value = status.get("trajectory_adjustment_settings", {})
    if isinstance(settings_value, Mapping):
        status["trajectory_adjustment_settings"] = dict(settings_value)
    else:
        status["trajectory_adjustment_settings"] = {}
    overrides_value = status.get("trajectory_overrides", {})
    if isinstance(overrides_value, Mapping):
        status["trajectory_overrides"] = dict(overrides_value)
    else:
        status["trajectory_overrides"] = {}
    low_confidence_value = status.get("low_confidence_priorities", [])
    if isinstance(low_confidence_value, Sequence) and not isinstance(low_confidence_value, (str, bytes)):
        status["low_confidence_priorities"] = [
            _canonicalize_priority_text(str(item))
            for item in low_confidence_value
            if str(item).strip()
        ]
    else:
        status["low_confidence_priorities"] = []
    return status


def load_cycle_summaries(
    limit: int = 20,
    *,
    directory: Path | str | None = None,
) -> list[dict[str, object]]:
    """Load persisted cycle summaries sorted by most recent completion."""

    target_dir = Path(directory) if directory else ARCHITECT_CYCLE_DIR
    if not target_dir.exists():
        return []
    try:
        files = sorted(
            target_dir.glob("cycle_*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        files = []
    if limit > 0:
        files = files[:limit]
    records: list[dict[str, object]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, Mapping):
            continue
        record = dict(data)
        record["path"] = path.as_posix()
        records.append(record)
    records.sort(key=lambda item: str(item.get("ended_at", "")), reverse=True)
    return records


def load_trajectory_reports(
    limit: int = 10,
    *,
    directory: Path | str | None = None,
) -> list[dict[str, object]]:
    target_dir = Path(directory) if directory else ARCHITECT_TRAJECTORY_DIR
    if not target_dir.exists():
        return []
    try:
        files = sorted(
            target_dir.glob("trajectory_*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        files = []
    if limit > 0:
        files = files[:limit]
    records: list[dict[str, object]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, Mapping):
            continue
        record = dict(data)
        record["path"] = path.as_posix()
        records.append(record)
    records.sort(key=lambda item: str(item.get("ended_at", "")), reverse=True)
    return records


def load_priority_backlog_snapshot(
    *,
    path: Path | str | None = None,
) -> dict[str, object]:
    target = Path(path) if path else ARCHITECT_PRIORITY_BACKLOG_PATH
    if not target.exists():
        return {"active": [], "history": [], "low_confidence": [], "updated": ""}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {"active": [], "history": [], "low_confidence": [], "updated": ""}
    if not isinstance(raw, Mapping):
        return {"active": [], "history": [], "low_confidence": [], "updated": ""}
    active_entries: list[dict[str, object]] = []
    raw_active = raw.get("active")
    if isinstance(raw_active, Sequence):
        for item in raw_active:
            if not isinstance(item, Mapping):
                continue
            entry: dict[str, object] = {
                "id": str(item.get("id", "")),
                "text": str(item.get("text", "")),
                "status": str(item.get("status", "")),
            }
            confidence = str(item.get("confidence", "")).strip()
            if confidence:
                entry["confidence"] = confidence
            active_entries.append(entry)
    history_entries: list[dict[str, object]] = []
    raw_history = raw.get("history")
    if isinstance(raw_history, Sequence):
        for item in raw_history:
            if not isinstance(item, Mapping):
                continue
            entry = {
                "id": str(item.get("id", "")),
                "text": str(item.get("text", "")),
                "status": str(item.get("status", "")),
                "completed_at": str(item.get("completed_at", "")),
            }
            history_entries.append(entry)
    low_confidence = [
        str(entry.get("id") or entry.get("text"))
        for entry in active_entries
        if str(entry.get("confidence", "")) == "low"
    ]
    return {
        "active": active_entries,
        "history": history_entries,
        "low_confidence": [item for item in low_confidence if item],
        "updated": str(raw.get("updated", "")),
    }
