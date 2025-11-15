"""Windows-oriented runtime shell for SentientOS services."""

from __future__ import annotations

import copy
import json
import logging
import os
import subprocess
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Deque, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from sentientos.cathedral import (
    Amendment,
    AmendmentApplicator,
    CathedralDigest,
    DEFAULT_CATHEDRAL_CONFIG as BASE_CATHEDRAL_CONFIG,
    ReviewResult,
    RollbackEngine,
    RollbackResult,
    amendment_digest,
    evaluate_invariants,
    quarantine_amendment,
    review_amendment,
)
from sentientos.cathedral.federation_guard import GuardDecision, should_accept_amendment
from sentientos.persona import PersonaLoop, initial_state, make_persona_event_source
from sentientos.persona_events import collect_recent_events, publish_event
from sentientos.runtime import bootstrap
from sentientos.experiments.federation_guard import (
    ExperimentGuardDecision,
    set_event_sink as set_experiment_guard_sink,
    set_window_provider as set_experiment_window_provider,
)
from sentientos.federation.window import FederationWindow
from sentientos.federation.sync_view import PeerSyncView
from sentientos.voice.config import parse_tts_config
from sentientos.voice.tts import TtsEngine
from sentientos.world.bus import WorldEventBus
from sentientos.world.events import WorldEvent
from sentientos.world.sources import (
    DemoTriggerSource,
    IdlePulseSource,
    ScriptedTimelineSource,
    WorldSource,
)
from sentientos.memory import (
    DreamLoop,
    MemoryMounts,
    count_glow_shards,
    ensure_memory_mounts,
    most_recent_glow_entry,
    render_reflection_line,
    validate_memory_mounts,
)

__all__ = [
    "DEFAULT_RUNTIME_CONFIG",
    "DEFAULT_DASHBOARD_CONFIG",
    "DEFAULT_CATHEDRAL_CONFIG",
    "DEFAULT_DREAM_LOOP_CONFIG",
    "RuntimeShell",
    "ensure_runtime_dirs",
    "load_or_init_config",
]


_DEFAULT_CONFIG_TEMPLATE = bootstrap.build_default_config()
DEFAULT_RUNTIME_CONFIG: Dict[str, object] = dict(_DEFAULT_CONFIG_TEMPLATE["runtime"])
DEFAULT_PERSONA_CONFIG: Dict[str, object] = dict(_DEFAULT_CONFIG_TEMPLATE["persona"])
DEFAULT_DASHBOARD_CONFIG: Dict[str, object] = dict(_DEFAULT_CONFIG_TEMPLATE["dashboard"])
DEFAULT_VOICE_CONFIG: Dict[str, object] = copy.deepcopy(_DEFAULT_CONFIG_TEMPLATE.get("voice", {}))
DEFAULT_WORLD_CONFIG: Dict[str, object] = copy.deepcopy(_DEFAULT_CONFIG_TEMPLATE.get("world", {}))
DEFAULT_CATHEDRAL_CONFIG: Dict[str, object] = dict(BASE_CATHEDRAL_CONFIG)
DEFAULT_DREAM_LOOP_CONFIG: Dict[str, object] = dict(_DEFAULT_CONFIG_TEMPLATE["dream_loop"])

ensure_runtime_dirs = bootstrap.ensure_runtime_dirs


class RuntimeShell:
    """Manage SentientOS runtime services on Windows."""

    def __init__(self, config: Mapping[str, object]) -> None:
        self._config = dict(config)
        runtime_section = _ensure_runtime_config(self._config)
        runtime_root_value = runtime_section.get("root") or bootstrap.get_base_dir()
        self._runtime_root = Path(runtime_root_value)
        bootstrap.ensure_runtime_dirs(self._runtime_root)
        self._memory_mounts: MemoryMounts = ensure_memory_mounts(self._runtime_root)
        validate_memory_mounts(self._memory_mounts, self._runtime_root)

        logs_dir = runtime_section.get("logs_dir") or (self._runtime_root / "logs")
        self._log_path = Path(logs_dir) / "runtime.log"
        self._logger = logging.getLogger("sentientos.runtime.shell")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        if not any(_handler_targets(self._log_path, handler) for handler in self._logger.handlers):
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(self._log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self._logger.addHandler(handler)

        persona_section = _ensure_persona_config(self._config)
        voice_section = _ensure_voice_config(self._config)
        world_section = _ensure_world_config(self._config)
        cathedral_section = _ensure_cathedral_config(self._config)
        _ensure_federation_config(self._config)
        self._cathedral_config = dict(cathedral_section)

        self._process_commands: Dict[str, Tuple[Tuple[str, ...], Dict[str, Optional[object]]]] = {}
        self._processes: Dict[str, subprocess.Popen[bytes]] = {}
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._running = False
        self._watchdog_interval = float(runtime_section.get("watchdog_interval", 5.0))
        self._windows_mode = bool(runtime_section.get("windows_mode", True))
        self._persona_enabled = bool(persona_section.get("enabled", True))
        self._persona_tick_interval = float(
            persona_section.get("tick_interval_seconds", DEFAULT_PERSONA_CONFIG["tick_interval_seconds"])
        )
        self._persona_max_message_length = int(
            persona_section.get("max_message_length", DEFAULT_PERSONA_CONFIG["max_message_length"])
        )
        self._persona_loop: Optional[PersonaLoop] = None
        self._tts_engine: Optional[TtsEngine] = None
        self._speak_callback: Optional[Callable[[str], None]] = None
        self._world_enabled = bool(world_section.get("enabled", True))
        self._world_poll_interval = max(
            0.5, float(world_section.get("poll_interval_seconds", DEFAULT_WORLD_CONFIG.get("poll_interval_seconds", 2.0)))
        )
        self._world_bus: Optional[WorldEventBus] = WorldEventBus() if self._world_enabled else None
        self._world_sources: List[WorldSource] = []
        self._world_thread: Optional[threading.Thread] = None
        self._world_stop_event = threading.Event()
        self._guard_events: Deque[Dict[str, object]] = deque(maxlen=128)
        self._guard_lock = threading.Lock()
        self._guard_event_buffer: Deque[Dict[str, object]] = deque(maxlen=16)
        self._pending_federation_amendments: Dict[str, Amendment] = {}
        self._cathedral_guard_hold_total = 0
        self._experiment_guard_hold_total = 0
        self._persona_event_source = make_persona_event_source(
            self._world_bus if self._world_enabled else None,
            [collect_recent_events, self._persona_guard_event_source],
        )
        if self._world_enabled and self._world_bus is not None:
            self._world_sources = self._build_world_sources(world_section)
        self._configure_voice(voice_section)
        self._log("RuntimeShell initialised", extra=runtime_section)

        dream_loop_section = _ensure_dream_loop_config(self._config)
        self._dream_loop_enabled = bool(dream_loop_section.get("enabled", DEFAULT_DREAM_LOOP_CONFIG["enabled"]))
        interval_default = int(DEFAULT_DREAM_LOOP_CONFIG.get("interval_seconds", 60))
        self._dream_loop_interval = max(5, int(dream_loop_section.get("interval_seconds", interval_default)))
        self._dream_loop_max_recent = int(
            dream_loop_section.get("max_recent_shards", DEFAULT_DREAM_LOOP_CONFIG.get("max_recent_shards", 5))
        )
        self._dream_loop: Optional[DreamLoop] = None

        federation_config, federation_warnings = load_federation_config(
            self._config,
            runtime_root=self._runtime_root,
        )
        self._federation_config = federation_config
        self._federation_poller: Optional[FederationPoller] = None
        if federation_warnings:
            for warning in federation_warnings:
                self._log("Federation configuration warning", extra={"warning": warning})
        if self._federation_config.enabled:
            self._log(
                "Federation enabled",
                extra={
                    "node": self._federation_config.node_id.name,
                    "fingerprint": self._federation_config.node_id.fingerprint,
                    "peers": [peer.node_name for peer in self._federation_config.peers],
                },
            )

        review_log = str(cathedral_section.get("review_log") or DEFAULT_CATHEDRAL_CONFIG["review_log"])
        self._cathedral_log_path = Path(review_log)
        self._cathedral_log_path.parent.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("SENTIENTOS_CATHEDRAL_REVIEW_LOG", str(self._cathedral_log_path))
        quarantine_dir = str(cathedral_section.get("quarantine_dir") or DEFAULT_CATHEDRAL_CONFIG["quarantine_dir"])
        os.environ.setdefault("SENTIENTOS_QUARANTINE_DIR", quarantine_dir)
        self._cathedral_digest = CathedralDigest.from_log(self._cathedral_log_path)
        self._dashboard_notifier: Optional[Callable[[str], None]] = None
        self._amendment_applicator = AmendmentApplicator(self._config)
        self._rollback_engine = RollbackEngine(
            self._config,
            self._amendment_applicator.rollback_dir,
            self._amendment_applicator.ledger_path,
        )
        self._last_rollback_ts: Optional[datetime] = None
        self._bootstrap_recovery()
        set_experiment_window_provider(self.federation_window)
        set_experiment_guard_sink(self._handle_experiment_guard_event)

    @property
    def log_path(self) -> Path:
        return self._log_path

    @property
    def runtime_root(self) -> Path:
        return self._runtime_root

    @property
    def memory_mounts(self) -> MemoryMounts:
        return self._memory_mounts

    @property
    def world_bus(self) -> Optional[WorldEventBus]:
        return self._world_bus

    @property
    def cathedral_digest(self) -> CathedralDigest:
        return self._cathedral_digest

    @property
    def config(self) -> Mapping[str, object]:
        return self._config

    @property
    def federation_config(self):
        return self._federation_config

    @property
    def ledger_path(self) -> Path:
        return self._amendment_applicator.ledger_path

    def dream_loop_status(self) -> Dict[str, object]:
        status: Dict[str, object] = {
            "enabled": self._dream_loop_enabled,
            "running": False,
            "last_shard_id": None,
            "last_focus": None,
            "last_summary": None,
            "last_created_at": None,
            "shard_count": count_glow_shards(self._memory_mounts),
        }
        if self._dream_loop:
            loop_status = self._dream_loop.status()
            status.update(loop_status)
            status["running"] = self._dream_loop.is_running()
            if status.get("last_summary") is None:
                entry = most_recent_glow_entry(self._memory_mounts)
                if entry:
                    status["last_summary"] = entry.get("summary")
                    status["last_focus"] = status.get("last_focus") or entry.get("focus")
                    status["last_shard_id"] = status.get("last_shard_id") or entry.get("id")
                    if status.get("last_created_at") is None:
                        status["last_created_at"] = self._coerce_datetime(entry.get("created_at"))
        else:
            entry = most_recent_glow_entry(self._memory_mounts)
            if entry:
                status["last_shard_id"] = entry.get("id")
                status["last_focus"] = entry.get("focus")
                status["last_summary"] = entry.get("summary")
                created = entry.get("created_at")
                status["last_created_at"] = self._coerce_datetime(created)
        return status

    def get_dream_snapshot(self) -> Dict[str, object]:
        snapshot = self.dream_loop_status()
        created = snapshot.get("last_created_at")
        if isinstance(created, datetime):
            snapshot["last_created_at"] = created.astimezone(timezone.utc)
        return snapshot

    def get_persona_snapshot(self) -> Optional[Dict[str, object]]:
        loop = self._persona_loop
        if loop is None:
            return None
        state = loop.state
        if state is None:
            return None
        snapshot: Dict[str, object] = {
            "mood": state.mood,
            "energy": state.energy,
            "last_reflection": state.last_reflection,
            "recent_reflection": state.recent_reflection,
        }
        if state.last_update_ts is not None:
            ts = state.last_update_ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            snapshot["last_update_ts"] = ts.astimezone(timezone.utc)
        return snapshot

    def get_federation_state(self) -> FederationState:
        if self._federation_poller:
            return self._federation_poller.state
        return FederationState()

    def federation_window(self) -> Optional[FederationWindow]:
        if self._federation_poller:
            return self._federation_poller.get_window()
        return None

    def get_peer_sync_views(self) -> Dict[str, PeerSyncView]:
        if self._federation_poller:
            return self._federation_poller.get_peer_sync_views()
        return {}

    def get_federation_replay_state(self):
        if self._federation_poller:
            return self._federation_poller.get_replay_state()
        return {}

    def replay_peer(self, peer_id: str):
        if self._federation_poller:
            return self._federation_poller.replay_peer(peer_id)
        return None

    def consume_guard_events_since(self, since_ts: datetime) -> List[Dict[str, object]]:
        cutoff = since_ts
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        else:
            cutoff = cutoff.astimezone(timezone.utc)
        with self._guard_lock:
            return [event for event in self._guard_events if event.get("ts") > cutoff]

    def _persona_guard_event_source(self) -> List[Dict[str, object]]:
        events: List[Dict[str, object]] = []
        window = self.federation_window()
        if window and window.is_cluster_unstable:
            events.append(
                {
                    "kind": "federation_guard",
                    "state": "unstable",
                    "ts": datetime.now(timezone.utc),
                }
            )
        with self._guard_lock:
            while self._guard_event_buffer:
                events.append(self._guard_event_buffer.popleft())
        return events

    def _record_guard_event(self, category: str, decision: str, payload: Dict[str, object]) -> None:
        event = dict(payload)
        event.update({
            "category": category,
            "decision": decision,
            "ts": datetime.now(timezone.utc),
        })
        with self._guard_lock:
            self._guard_events.append(event)
            if decision.lower() == "hold":
                persona_event = {
                    "kind": "federation_guard",
                    "state": "hold",
                    "category": category,
                    "payload": dict(payload),
                    "ts": event["ts"],
                }
                self._guard_event_buffer.append(persona_event)

    def _handle_experiment_guard_event(
        self,
        decision: ExperimentGuardDecision,
        payload: Dict[str, object],
    ) -> None:
        decision_text = str(decision)
        experiment_id = str(payload.get("experiment_id") or "unknown")
        risk_level = str(payload.get("risk_level") or "medium")
        message: Optional[str] = None
        if decision_text == "hold":
            self._experiment_guard_hold_total += 1
            message = (
                f"Experiments: holding {experiment_id} due to federation instability "
                f"(risk={risk_level})"
            )
        elif decision_text == "warn":
            message = (
                f"Experiments: running {experiment_id} with drift warnings "
                f"(risk={risk_level})"
            )
        if message:
            self._log(message, extra={"experiment_id": experiment_id, "decision": decision_text})
            self._notify_dashboard(message)
        self._record_guard_event(
            "experiments",
            decision_text,
            {"experiment_id": experiment_id, "risk_level": risk_level},
        )

    def _hold_amendment_for_federation(
        self,
        amendment: Amendment,
        window: Optional[FederationWindow],
    ) -> None:
        self._pending_federation_amendments[amendment.id] = amendment
        self._cathedral_digest = self._cathedral_digest.record_pending_federation(amendment)
        self._cathedral_guard_hold_total += 1
        message = (
            f"Cathedral: holding amendment {amendment.id} due to federation instability "
            f"(risk={amendment.risk_level})"
        )
        self._log(message, extra={"amendment_id": amendment.id, "risk_level": amendment.risk_level})
        self._notify_dashboard(message)
        publish_event(
            {
                "kind": "cathedral",
                "event": "amendment_held",
                "amendment_id": amendment.id,
                "risk_level": amendment.risk_level,
                "ts": datetime.now(timezone.utc).isoformat(),
                "window_unstable": bool(window.is_cluster_unstable) if window else True,
            }
        )
        self._record_guard_event(
            "cathedral",
            "hold",
            {"amendment_id": amendment.id, "risk_level": amendment.risk_level},
        )

    def _apply_amendment_with_guard(
        self,
        amendment: Amendment,
        decision: GuardDecision,
        *,
        from_pending: bool = False,
    ):
        message: Optional[str] = None
        if from_pending:
            if decision == "warn":
                message = (
                    f"Cathedral: applying pending amendment {amendment.id} with drift warnings "
                    f"(risk={amendment.risk_level})"
                )
            else:
                message = (
                    f"Cathedral: applying pending amendment {amendment.id} after federation recovery "
                    f"(risk={amendment.risk_level})"
                )
        elif decision == "warn":
            message = (
                f"Cathedral: applying amendment {amendment.id} with drift warnings "
                f"(risk={amendment.risk_level})"
            )
        if message:
            self._log(message, extra={"amendment_id": amendment.id, "decision": decision})
            self._notify_dashboard(message)
            publish_event(
                {
                    "kind": "cathedral",
                    "event": "amendment_guard",
                    "decision": decision,
                    "amendment_id": amendment.id,
                    "risk_level": amendment.risk_level,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )
        if decision in {"warn", "hold"}:
            self._record_guard_event(
                "cathedral",
                decision,
                {"amendment_id": amendment.id, "risk_level": amendment.risk_level},
            )
        apply_result = self._amendment_applicator.apply(amendment)
        self._config = copy.deepcopy(self._amendment_applicator.runtime_config)
        self._rollback_engine.runtime_config = copy.deepcopy(self._config)
        self._cathedral_digest = self._cathedral_digest.record_application(amendment, apply_result.status)
        if from_pending:
            self._cathedral_digest = self._cathedral_digest.resolve_pending_federation(amendment.id)
        self._handle_application_result(amendment, apply_result)
        self._run_post_apply_checks(amendment, apply_result)
        return apply_result

    def _attempt_pending_amendments(self, window: FederationWindow) -> None:
        if not window.is_quorum_healthy:
            return
        pending_items = list(self._pending_federation_amendments.items())
        for amendment_id, amendment in pending_items:
            decision = should_accept_amendment(window, getattr(amendment, "risk_level", "medium"))
            if decision == "hold":
                continue
            self._pending_federation_amendments.pop(amendment_id, None)
            self._apply_amendment_with_guard(amendment, decision, from_pending=True)

    def on_federation_window(self, window: FederationWindow) -> None:
        self._attempt_pending_amendments(window)

    def register_dashboard_notifier(self, callback: Optional[Callable[[str], None]]) -> None:
        self._dashboard_notifier = callback

    def _notify_dashboard(self, message: str) -> None:
        if not self._dashboard_notifier:
            return
        try:
            self._dashboard_notifier(message)
        except Exception:  # pragma: no cover - defensive logging
            self._log("Failed to notify dashboard", extra={"message": message})

    def submit_amendment(self, amendment: Amendment) -> ReviewResult:
        """Run an amendment through the Cathedral review pipeline."""

        result = review_amendment(amendment)
        self._cathedral_digest = self._cathedral_digest.record(amendment, result)

        status = result.status
        if status == "accepted":
            self._log(
                "Amendment accepted",
                extra={
                    "amendment_id": amendment.id,
                    "digest": amendment_digest(amendment),
                    "summary": amendment.summary,
                },
            )
            window = self.federation_window()
            decision = should_accept_amendment(window, getattr(amendment, "risk_level", "medium"))
            if decision == "hold":
                self._hold_amendment_for_federation(amendment, window)
                return result
            apply_result = self._apply_amendment_with_guard(amendment, decision)
        elif status == "quarantined":
            errors = list(result.invariant_errors) + list(result.validation_errors)
            first_error = errors[0] if errors else "Quarantined pending review"
            message = f"⚠️ Amendment {amendment.id} quarantined: {first_error}"
            self._log(
                message,
                extra={
                    "amendment_id": amendment.id,
                    "errors": errors,
                    "quarantine_path": result.quarantine_path,
                },
            )
            if self._dashboard_notifier:
                try:
                    self._dashboard_notifier(message)
                except Exception:  # pragma: no cover - defensive logging
                    self._log("Failed to notify dashboard", extra={"amendment_id": amendment.id})
            if self._speak_callback is not None:
                try:
                    self._speak_callback("Amendment quarantined due to invariant violation.")
                except Exception:  # pragma: no cover - defensive logging
                    self._log("Failed to emit TTS alert", extra={"amendment_id": amendment.id})
        else:
            self._log(
                "Amendment rejected",
                extra={
                    "amendment_id": amendment.id,
                    "errors": list(result.validation_errors) + list(result.invariant_errors),
                },
            )

        return result

    def _handle_application_result(self, amendment: Amendment, apply_result) -> None:
        status = apply_result.status
        applied = apply_result.applied
        skipped = apply_result.skipped
        errors = apply_result.errors

        if status == "applied":
            message = f"✅ Amendment {amendment.id} applied"
        elif status == "partial":
            message = f"⚠️ Amendment {amendment.id} applied with warnings"
        elif status == "error":
            message = f"❌ Amendment {amendment.id} failed to apply"
        else:
            message = f"ℹ️ Amendment {amendment.id} made no changes"

        details = {
            "amendment_id": amendment.id,
            "status": status,
            "applied": applied,
            "skipped": skipped,
            "errors": errors,
        }
        self._log(message, extra=details)

        if self._dashboard_notifier:
            try:
                self._dashboard_notifier(message)
            except Exception:  # pragma: no cover - defensive logging
                self._log("Failed to notify dashboard", extra={"amendment_id": amendment.id})

        if self._speak_callback is not None:
            phrase: Optional[str] = None
            if status == "applied":
                phrase = "Amendment applied cleanly."
            elif status == "partial":
                phrase = "Amendment applied with warnings."
            elif status == "error":
                phrase = "Amendment application failed."
            if phrase:
                try:
                    self._speak_callback(phrase)
                except Exception:  # pragma: no cover - defensive logging
                    self._log("Failed to emit TTS alert", extra={"amendment_id": amendment.id})

    def _run_post_apply_checks(self, amendment: Amendment, apply_result) -> None:
        status = getattr(apply_result, "status", "")
        if status not in {"applied", "partial"}:
            return
        violations = evaluate_invariants(amendment)
        if not violations:
            return
        message = (
            f"Amendment {amendment.id} violated invariants after application. Auto-reverted."
        )
        extra = {"amendment_id": amendment.id, "violations": violations}
        self._log(message, extra=extra)
        if self._dashboard_notifier:
            try:
                self._dashboard_notifier(message)
            except Exception:  # pragma: no cover - defensive logging
                self._log("Failed to notify dashboard", extra={"amendment_id": amendment.id})

        rollback_result = self.rollback(
            amendment.id,
            auto=True,
            reason="Invariant violation after apply",
        )

        quarantine_reasons = list(dict.fromkeys(violations + ["Invalidated after apply"]))
        quarantine_path = quarantine_amendment(amendment, quarantine_reasons)
        self._cathedral_digest = self._cathedral_digest.record_post_apply_quarantine(
            amendment, violations[0]
        )
        self._log(
            "Amendment quarantined after auto-revert",
            extra={
                "amendment_id": amendment.id,
                "violations": violations,
                "quarantine_path": quarantine_path,
                "rollback_status": rollback_result.status,
            },
        )

    def rollback(
        self,
        amendment_id: str,
        *,
        auto: bool = False,
        reason: Optional[str] = None,
    ) -> RollbackResult:
        if not amendment_id:
            raise ValueError("amendment_id is required for rollback")

        start_message = f"Initiating rollback for amendment {amendment_id}…"
        log_extra: Dict[str, object] = {"amendment_id": amendment_id, "auto": auto}
        if reason:
            log_extra["reason"] = reason
        self._log(start_message, extra=log_extra)
        if self._dashboard_notifier:
            try:
                self._dashboard_notifier("Initiating rollback…")
            except Exception:  # pragma: no cover - defensive logging
                self._log("Failed to notify dashboard", extra={"amendment_id": amendment_id})

        result = self._rollback_engine.revert(amendment_id, auto=auto)

        if result.status in {"success", "partial"}:
            self._config = copy.deepcopy(self._rollback_engine.runtime_config)
            self._amendment_applicator.runtime_config = copy.deepcopy(self._config)
            self._cathedral_digest = self._cathedral_digest.record_rollback(
                amendment_id, result.status, auto=auto
            )
            completion_message = "Rollback complete."
            completion_extra: Dict[str, object] = {
                "amendment_id": amendment_id,
                "auto": auto,
                "status": result.status,
                "reverted": result.reverted,
                "skipped": result.skipped,
            }
            if reason:
                completion_extra["reason"] = reason
            self._log(completion_message, extra=completion_extra)
            if self._dashboard_notifier:
                try:
                    self._dashboard_notifier(completion_message)
                except Exception:  # pragma: no cover - defensive logging
                    self._log("Failed to notify dashboard", extra={"amendment_id": amendment_id})
            publish_event({
                "kind": "cathedral",
                "event": "rollback",
                "amendment_id": amendment_id,
                "auto": auto,
            })
            self._last_rollback_ts = datetime.now(timezone.utc)
            if auto and self._speak_callback is not None:
                try:
                    self._speak_callback("A change violated system integrity. I reverted to a safe state.")
                except Exception:  # pragma: no cover - defensive logging
                    self._log("Failed to emit TTS alert", extra={"amendment_id": amendment_id})
        else:
            if result.status == "not_found":
                failure_message = "Rollback metadata not found."
            else:
                failure_message = "Rollback failed — see logs."
            failure_extra: Dict[str, object] = {
                "amendment_id": amendment_id,
                "auto": auto,
                "status": result.status,
                "errors": result.errors,
            }
            if reason:
                failure_extra["reason"] = reason
            self._log(failure_message, extra=failure_extra)
            if self._dashboard_notifier:
                try:
                    self._dashboard_notifier(failure_message)
                except Exception:  # pragma: no cover - defensive logging
                    self._log("Failed to notify dashboard", extra={"amendment_id": amendment_id})

        return result

    def _bootstrap_recovery(self) -> None:
        mismatch = self._detect_bootstrap_mismatch()
        if mismatch is None:
            return
        amendment_id, details = mismatch
        self._log(
            "Configuration mismatch detected on startup; initiating rollback",
            extra={"amendment_id": amendment_id, "mismatches": details},
        )
        self.rollback(
            amendment_id,
            auto=True,
            reason="Configuration mismatch detected during bootstrap",
        )

    def _detect_bootstrap_mismatch(self) -> Optional[Tuple[str, Dict[str, Dict[str, Any]]]]:
        ledger_path = self._amendment_applicator.ledger_path
        if not ledger_path.exists():
            return None
        try:
            lines = ledger_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None

        last_apply: Optional[Mapping[str, Any]] = None
        for raw in lines:
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, Mapping):
                continue
            event = entry.get("event")
            if event not in (None, "apply", "application"):
                continue
            if isinstance(entry.get("applied"), Mapping):
                last_apply = entry

        if last_apply is None:
            return None

        applied_snapshot = last_apply.get("applied")
        if not isinstance(applied_snapshot, Mapping):
            return None

        expected = self._extract_applied_values(applied_snapshot)
        if not expected:
            return None

        mismatches: Dict[str, Dict[str, Any]] = {}
        for path, expected_value in expected.items():
            domain = path[0]
            segments = path[1:]
            actual = self._resolve_config_value(domain, segments, self._config)
            if actual != expected_value:
                mismatches[self._format_path(domain, segments)] = {
                    "expected": expected_value,
                    "actual": actual,
                }

        if not mismatches:
            return None

        amendment_id = str(last_apply.get("amendment_id") or "").strip()
        if not amendment_id:
            return None
        return amendment_id, mismatches

    def _extract_applied_values(
        self, applied_snapshot: Mapping[str, Any]
    ) -> Dict[Tuple[str, ...], Any]:
        values: Dict[Tuple[str, ...], Any] = {}
        for domain, snapshot in applied_snapshot.items():
            if not isinstance(snapshot, Mapping):
                continue
            self._collect_applied_values(str(domain), snapshot, (), values)
        return values

    def _collect_applied_values(
        self,
        domain: str,
        snapshot: Mapping[str, Any],
        prefix: Tuple[str, ...],
        values: Dict[Tuple[str, ...], Any],
    ) -> None:
        for key, value in snapshot.items():
            key_str = str(key)
            if isinstance(value, Mapping) and "value" in value:
                values[(domain,) + prefix + (key_str,)] = copy.deepcopy(value["value"])
            elif isinstance(value, Mapping):
                self._collect_applied_values(domain, value, prefix + (key_str,), values)

    def _resolve_config_value(
        self,
        domain: str,
        segments: Tuple[str, ...],
        config: Mapping[str, Any],
    ) -> Any:
        if domain == "config":
            current: Any = config
        else:
            section = config.get(domain)
            if not isinstance(section, Mapping):
                return None
            current = section
        for segment in segments:
            if not isinstance(current, Mapping):
                return None
            current = current.get(segment)
        return copy.deepcopy(current)

    def _format_path(self, domain: str, segments: Tuple[str, ...]) -> str:
        parts = [domain]
        parts.extend(segments)
        return ".".join(parts)

    def start(self) -> None:
        """Start all managed services in deterministic order."""

        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._log("Starting runtime shell")
        self.start_llama_server()
        self.start_relay()
        self.start_core()
        self._start_world_polling()
        self._start_persona_loop()
        self._start_dream_loop()
        self._start_federation_poller()
        self._monitor_thread = threading.Thread(target=self.monitor_processes, daemon=True)
        self._monitor_thread.start()

    def start_llama_server(self) -> None:
        runtime = _ensure_runtime_config(self._config)
        llama_path = str(runtime.get("llama_server_path"))
        model_path = str(runtime.get("model_path"))
        command = [llama_path, "--model", model_path]
        self._register_process("llama", command)
        self._log("llama.cpp server launched", extra={"command": command})

    def start_relay(self) -> None:
        runtime = _ensure_runtime_config(self._config)
        host = str(runtime.get("relay_host", "127.0.0.1"))
        port = str(runtime.get("relay_port", 65432))
        command = [
            "python",
            "-m",
            "sentientos.oracle_relay",
            "--host",
            host,
            "--port",
            str(port),
        ]
        self._register_process("relay", command)
        self._log("Relay server launched", extra={"command": command})

    def start_core(self) -> None:
        """Start core daemons required for SentientOS."""

        integrity_cmd = [
            "python",
            "-m",
            "sentientos.daemons.integrity_daemon",
        ]
        scheduler_cmd = [
            "python",
            str(Path("autonomous_ops.py").resolve()),
        ]
        self._register_process("integrity_daemon", integrity_cmd)
        self._register_process("autonomous_ops", scheduler_cmd)
        self._log("Core daemons launched", extra={"daemons": list(self._processes.keys())})

    def _start_persona_loop(self) -> None:
        if not self._persona_enabled:
            return
        if not self._persona_loop:
            self._persona_loop = PersonaLoop(
                initial_state(),
                tick_interval_seconds=self._persona_tick_interval,
                event_source=self._persona_event_source,
                max_message_length=self._persona_max_message_length,
                speak_callback=self._speak_callback,
                reflection_loader=self._load_recent_reflection,
            )
        else:
            self._persona_loop.set_reflection_loader(self._load_recent_reflection)
        self._persona_loop.start()
        self._log(
            "Persona loop launched",
            extra={
                "tick_interval_seconds": self._persona_tick_interval,
                "max_message_length": self._persona_max_message_length,
            },
        )

    def _start_dream_loop(self) -> None:
        if not self._dream_loop_enabled:
            return
        if self._dream_loop is None:
            self._dream_loop = DreamLoop(
                self,
                self._memory_mounts,
                interval_seconds=self._dream_loop_interval,
                log_cb=lambda message, extra=None: self._log(message, extra=extra),
                max_recent_shards=self._dream_loop_max_recent,
            )
        self._dream_loop.start()
        self._log(
            "Dream loop launched",
            extra={
                "interval_seconds": self._dream_loop_interval,
                "max_recent_shards": self._dream_loop_max_recent,
            },
        )

    def _start_world_polling(self) -> None:
        if not self._world_enabled or self._world_bus is None:
            return
        if not self._world_sources:
            return
        if self._world_thread and self._world_thread.is_alive():
            return
        self._world_stop_event.clear()
        self._world_thread = threading.Thread(
            target=self._run_world_polling,
            name="WorldEventPoller",
            daemon=True,
        )
        self._world_thread.start()
        self._log(
            "World event poller started",
            extra={"sources": [type(source).__name__ for source in self._world_sources]},
        )

    def _run_world_polling(self) -> None:
        assert self._world_bus is not None
        while not self._world_stop_event.is_set():
            for source in self._world_sources:
                try:
                    events = source.poll()
                except Exception as exc:  # pragma: no cover - defensive logging
                    self._log(
                        "World source error",
                        extra={"source": type(source).__name__, "error": str(exc)},
                    )
                    continue
                for event in events:
                    self._world_bus.push(event)
            if self._world_stop_event.wait(self._world_poll_interval):
                break

    def _start_federation_poller(self) -> None:
        if not getattr(self, "_federation_config", None):
            return
        if not self._federation_config.enabled:
            return
        if self._federation_poller is None:
            self._federation_poller = FederationPoller(self._federation_config, self, self._log)
        self._federation_poller.start()

    def _build_world_sources(self, config: Mapping[str, object]) -> List[WorldSource]:
        sources: List[WorldSource] = []
        interval_default = DEFAULT_WORLD_CONFIG.get("idle_pulse_interval_seconds", 60)
        interval_value = config.get("idle_pulse_interval_seconds", interval_default)
        interval = self._safe_float(interval_value, float(interval_default))
        if interval > 0:
            try:
                sources.append(IdlePulseSource(interval))
            except ValueError:
                pass

        if bool(config.get("scripted_timeline_enabled")):
            timeline_entries = self._parse_timeline(config.get("scripted_timeline"))
            if timeline_entries:
                sources.append(ScriptedTimelineSource(timeline_entries))

        demo_cfg = config.get("demo_trigger")
        if isinstance(demo_cfg, Mapping) and demo_cfg.get("enabled"):
            demo_name = str(demo_cfg.get("demo_name") or "demo_simple_success").strip() or "demo_simple_success"
            default_trigger = DEFAULT_WORLD_CONFIG.get("demo_trigger", {}).get("trigger_after_seconds", 60)
            trigger = self._safe_float(demo_cfg.get("trigger_after_seconds"), float(default_trigger))
            sources.append(DemoTriggerSource(demo_name, trigger_after_seconds=trigger))

        return sources

    def _parse_timeline(self, raw: object) -> List[Tuple[float, WorldEvent]]:
        entries: List[Tuple[float, WorldEvent]] = []
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return entries
        for item in raw:
            entry = self._coerce_timeline_entry(item)
            if entry is not None:
                entries.append(entry)
        return entries

    def _coerce_timeline_entry(self, item: object) -> Optional[Tuple[float, WorldEvent]]:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            offset, event = item
            if isinstance(offset, (int, float)) and isinstance(event, WorldEvent):
                return float(offset), event
        if isinstance(item, Mapping):
            offset_value = item.get("offset_seconds", item.get("offset"))
            try:
                offset = float(offset_value)
            except (TypeError, ValueError):
                return None
            payload = item.get("event")
            event: Optional[WorldEvent]
            if isinstance(payload, WorldEvent):
                event = payload
            elif isinstance(payload, Mapping):
                event = self._build_world_event_from_mapping(payload)
            else:
                event = self._build_world_event_from_mapping(item)
            if event is None:
                return None
            return offset, event
        return None

    def _build_world_event_from_mapping(self, payload: Mapping[str, object]) -> Optional[WorldEvent]:
        kind = payload.get("kind")
        if not isinstance(kind, str) or not kind:
            return None
        summary_value = payload.get("summary")
        summary = str(summary_value).strip() if isinstance(summary_value, str) and summary_value else f"{kind} event"
        data_value = payload.get("data")
        if isinstance(data_value, Mapping):
            event_data = dict(data_value)
        else:
            event_data = {}
            for key in ("subject", "source", "title", "starts_in_minutes", "level", "demo_name"):
                if key in payload:
                    event_data[key] = payload[key]
        return WorldEvent(kind, datetime.now(timezone.utc), summary, event_data)

    @staticmethod
    def _coerce_datetime(value: object) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return None
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return None

    @staticmethod
    def _safe_float(value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _load_recent_reflection(self) -> Optional[str]:
        entry = most_recent_glow_entry(self._memory_mounts)
        return render_reflection_line(entry)

    def monitor_processes(self, run_once: bool = False) -> None:
        """Watch managed processes and restart on unexpected exit."""

        while not self._stop_event.is_set():
            with self._lock:
                items = list(self._processes.items())
            for name, process in items:
                if process.poll() is None:
                    continue
                exit_code = process.returncode
                self._log(
                    "Process exited; restarting",
                    extra={"process": name, "exit_code": exit_code},
                )
                self._spawn_process(name)
            if run_once:
                break
            self._stop_event.wait(self._watchdog_interval)

    def shutdown(self) -> None:
        """Stop the monitor and gracefully terminate processes."""

        if not self._running:
            return
        self._log("Shutdown requested")
        self._running = False
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=self._watchdog_interval * 2)
            self._monitor_thread = None
        if self._world_thread:
            self._world_stop_event.set()
            self._world_thread.join(timeout=self._world_poll_interval * 2)
            self._world_thread = None
        if self._persona_loop:
            self._persona_loop.stop()
            self._persona_loop = None
        if self._dream_loop:
            self._dream_loop.stop()
            self._dream_loop = None
        if self._federation_poller:
            self._federation_poller.stop()
            self._federation_poller = None
        set_experiment_guard_sink(None)
        set_experiment_window_provider(None)
        with self._lock:
            items = list(self._processes.items())
        for name, process in items:
            if process.poll() is not None:
                continue
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        self._log("Runtime shell stopped")

    def _register_process(
        self,
        name: str,
        command: Iterable[str],
        *,
        cwd: Optional[str | os.PathLike[str]] = None,
        env: Optional[MutableMapping[str, str]] = None,
    ) -> None:
        self._process_commands[name] = (
            tuple(command),
            {"cwd": cwd, "env": dict(env) if env else None},
        )
        self._spawn_process(name)

    def _spawn_process(self, name: str) -> None:
        command, options = self._process_commands[name]
        kwargs: Dict[str, object] = {}
        if options["cwd"] is not None:
            kwargs["cwd"] = options["cwd"]
        if options["env"] is not None:
            kwargs["env"] = options["env"]
        if os.name == "nt" or self._windows_mode:
            creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            kwargs["creationflags"] = creation_flags
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(list(command), **kwargs)
        with self._lock:
            self._processes[name] = process

    def _log(self, message: str, *, extra: Optional[Mapping[str, object]] = None) -> None:
        payload = {"message": message}
        if extra:
            payload.update(extra)
        self._logger.info(json.dumps(payload, sort_keys=True))

    def _configure_voice(self, voice_section: Mapping[str, object]) -> None:
        enabled = bool(voice_section.get("enabled", False))
        if not enabled:
            return
        tts_section = voice_section.get("tts")
        if not isinstance(tts_section, Mapping):
            return
        try:
            tts_config = parse_tts_config(tts_section)
        except Exception as exc:  # pragma: no cover - defensive logging
            self._log("Failed to parse TTS configuration", extra={"error": str(exc)})
            return
        if not tts_config.enabled:
            return
        engine = TtsEngine(tts_config)
        self._tts_engine = engine
        self._speak_callback = engine.speak
        if self._persona_loop:
            self._persona_loop.set_speak_callback(self._speak_callback)
        self._log(
            "Voice TTS engine initialised",
            extra={
                "rate": tts_config.rate,
                "voice": tts_config.voice_name or "default",
            },
        )


def _ensure_runtime_config(config: MutableMapping[str, object]) -> MutableMapping[str, object]:
    runtime_section = config.get("runtime", {})
    if not isinstance(runtime_section, Mapping):
        runtime_section = {}
    runtime = dict(runtime_section)
    base_override = runtime.get("root")
    if isinstance(base_override, (str, Path)) and base_override:
        defaults = bootstrap.build_default_config(Path(base_override)).get("runtime", {})
    else:
        defaults = bootstrap.build_default_config().get("runtime", {})
    updated = False
    for key, default in defaults.items():
        if key not in runtime:
            runtime[key] = default
            updated = True
    if "runtime" not in config or updated:
        config["runtime"] = runtime
    return runtime


def _ensure_persona_config(config: MutableMapping[str, object]) -> MutableMapping[str, object]:
    persona_section = config.get("persona", {})
    if not isinstance(persona_section, Mapping):
        persona_section = {}
    persona = dict(persona_section)
    updated = False
    for key, default in DEFAULT_PERSONA_CONFIG.items():
        if key not in persona:
            persona[key] = default
            updated = True
    if "persona" not in config or updated:
        config["persona"] = persona
    return persona


def _ensure_world_config(config: MutableMapping[str, object]) -> MutableMapping[str, object]:
    world_section = config.get("world", {})
    if not isinstance(world_section, Mapping):
        world_section = {}
    world = dict(world_section)
    defaults = DEFAULT_WORLD_CONFIG
    updated = False
    for key, default in defaults.items():
        if isinstance(default, Mapping):
            existing = world.get(key)
            merged = dict(default)
            if isinstance(existing, Mapping):
                merged.update(existing)
            if world.get(key) != merged:
                world[key] = merged
                updated = True
        else:
            if key not in world:
                world[key] = default
                updated = True
    if "world" not in config or updated:
        config["world"] = world
    return world


def _ensure_federation_config(config: MutableMapping[str, object]) -> MutableMapping[str, object]:
    section = config.get("federation", {})
    if not isinstance(section, Mapping):
        section = {}
    defaults = bootstrap.build_default_config().get("federation", {})
    federation = dict(defaults)
    indexes_value = section.get("indexes") if isinstance(section, Mapping) else None
    indexes_present = isinstance(indexes_value, Mapping)
    federation.update(section)
    if not indexes_present:
        federation.pop("indexes", None)
    config["federation"] = federation
    return federation


def _ensure_voice_config(config: MutableMapping[str, object]) -> MutableMapping[str, object]:
    voice_section = config.get("voice", {})
    if not isinstance(voice_section, Mapping):
        voice_section = {}
    voice = dict(voice_section)
    defaults = DEFAULT_VOICE_CONFIG
    updated = False
    for key, default in defaults.items():
        if isinstance(default, Mapping):
            existing = voice.get(key)
            merged = dict(default)
            if isinstance(existing, Mapping):
                merged.update(existing)
            if voice.get(key) != merged:
                voice[key] = merged
                updated = True
        else:
            if key not in voice:
                voice[key] = default
                updated = True
    if "voice" not in config or updated:
        config["voice"] = voice
    return voice


def _ensure_dashboard_config(config: MutableMapping[str, object]) -> MutableMapping[str, object]:
    dashboard_section = config.get("dashboard", {})
    if not isinstance(dashboard_section, Mapping):
        dashboard_section = {}
    dashboard = dict(dashboard_section)
    defaults = bootstrap.build_default_config().get("dashboard", {})
    updated = False
    for key, default in defaults.items():
        if key not in dashboard:
            dashboard[key] = default
            updated = True
    if "dashboard" not in config or updated:
        config["dashboard"] = dashboard
    return dashboard


def _ensure_dream_loop_config(config: MutableMapping[str, object]) -> MutableMapping[str, object]:
    section = config.get("dream_loop", {})
    if not isinstance(section, Mapping):
        section = {}
    defaults = bootstrap.build_default_config().get("dream_loop", {})
    dream_loop = dict(defaults)
    dream_loop.update(section)
    config["dream_loop"] = dream_loop
    return dream_loop


def _ensure_cathedral_config(config: MutableMapping[str, object]) -> MutableMapping[str, object]:
    cathedral_section = config.get("cathedral", {})
    if not isinstance(cathedral_section, Mapping):
        cathedral_section = {}
    cathedral = dict(cathedral_section)
    updated = False
    for key, default in DEFAULT_CATHEDRAL_CONFIG.items():
        if key not in cathedral:
            cathedral[key] = default
            updated = True
    if "cathedral" not in config or updated:
        config["cathedral"] = cathedral
    return cathedral


def load_or_init_config(path: Path) -> Dict[str, object]:
    """Load runtime configuration, writing defaults on first run."""

    base_dir = path.parents[2] if len(path.parents) >= 3 else bootstrap.get_base_dir()
    bootstrap.ensure_runtime_dirs(base_dir)
    config_path = bootstrap.ensure_default_config(path.parent)
    path = config_path
    existing_text = None
    if path.exists():
        try:
            existing_text = path.read_text(encoding="utf-8")
            data = json.loads(existing_text)
            if not isinstance(data, dict):
                data = {}
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    runtime = _ensure_runtime_config(data)
    persona = _ensure_persona_config(data)
    world = _ensure_world_config(data)
    voice = _ensure_voice_config(data)
    dashboard = _ensure_dashboard_config(data)
    cathedral = _ensure_cathedral_config(data)
    dream_loop = _ensure_dream_loop_config(data)
    data["runtime"] = runtime
    data["persona"] = persona
    data["world"] = world
    data["voice"] = voice
    data["dashboard"] = dashboard
    data["cathedral"] = cathedral
    data["dream_loop"] = dream_loop
    serialized = json.dumps(data, indent=2)
    if existing_text != serialized:
        config_path.write_text(serialized, encoding="utf-8")
    return data


def _handler_targets(path: Path, handler: logging.Handler) -> bool:
    if not isinstance(handler, logging.FileHandler):
        return False
    handler_path = Path(getattr(handler, "baseFilename", ""))
    return handler_path == path
from sentientos.federation.config import load_federation_config
from sentientos.federation.poller import FederationPoller, FederationState
