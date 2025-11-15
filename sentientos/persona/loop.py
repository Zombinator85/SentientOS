"""Ambient persona heartbeat loop for Lumos Light."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional

from .logger import get_persona_logger
from .state import PersonaState, decay_energy, update_from_pulse
from .text import format_persona_message

EventSource = Callable[[], Iterable[Dict[str, object]]]


class PersonaLoop:
    """Periodic loop that maintains persona state and emits heartbeats."""

    def __init__(
        self,
        state: PersonaState,
        *,
        tick_interval_seconds: float = 60.0,
        event_source: Optional[EventSource] = None,
        max_message_length: int = 200,
        logger: Optional[logging.Logger] = None,
        speak_callback: Optional[Callable[[str], None]] = None,
        reflection_loader: Optional[Callable[[], Optional[str]]] = None,
    ) -> None:
        self._state = state
        self._tick_interval = max(1.0, float(tick_interval_seconds))
        self._event_source = event_source
        self._max_message_length = max(40, int(max_message_length))
        self._logger = logger or get_persona_logger()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_tick: Optional[datetime] = None
        self._lock = threading.Lock()
        self._speak_callback = speak_callback
        self._reflection_loader = reflection_loader

    @property
    def state(self) -> PersonaState:
        return self._state

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="PersonaLoop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is None:
            return
        thread.join(timeout=self._tick_interval * 2)
        self._thread = None

    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._tick_once()
            if self._stop_event.wait(self._tick_interval):
                break

    def _collect_events(self) -> List[Dict[str, object]]:
        if not self._event_source:
            return []
        try:
            events = list(self._event_source())
        except Exception:  # pragma: no cover - defensive logging
            self._logger.exception("Persona event source failed")
            return []
        filtered: List[Dict[str, object]] = []
        for event in events:
            if isinstance(event, dict):
                filtered.append(dict(event))
        return filtered

    def _build_summary(self, events: List[Dict[str, object]]) -> str:
        cathedral_events = [
            event for event in events if event.get("kind") == "cathedral" and event.get("event") == "rollback"
        ]
        if cathedral_events:
            return "I detected an inconsistency and restored my previous stable configuration."

        guard_holds = [
            event for event in events if event.get("kind") == "federation_guard" and event.get("state") == "hold"
        ]
        if guard_holds:
            return "I’m noticing disagreement across nodes, so I’m pausing high-impact changes until we’re aligned again."

        federation_events = [
            event
            for event in events
            if event.get("kind") in {"federation", "federation_guard"}
            and str(event.get("state") or event.get("level") or "").lower() in {"drift", "incompatible", "unstable"}
        ]
        if federation_events:
            return "I’m noticing disagreement across nodes, so I’m pausing high-impact changes until we’re aligned again."

        if not events:
            if self._state.mood in {"tired", "idle"}:
                return "Quietly tending the cadence while I recharge."
            return "All systems look steady."

        def _join_descriptions(parts: List[str]) -> str:
            if not parts:
                return "something new"
            if len(parts) == 1:
                return parts[0]
            return ", ".join(parts[:-1]) + f" and {parts[-1]}"

        world_events = [e for e in events if e.get("kind") == "world"]
        if world_events:
            descriptors: List[str] = []
            urgent = False
            for event in world_events:
                world_kind = str(event.get("world_kind") or "")
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                if world_kind == "message":
                    descriptors.append("a new message")
                elif world_kind == "calendar":
                    descriptors.append("an upcoming calendar item")
                    urgent = True
                elif world_kind == "system_load":
                    level = str(data.get("level") or "").lower()
                    if level in {"high", "busy", "medium"}:
                        descriptors.append("busy system load")
                        urgent = True
                    else:
                        descriptors.append("a calm system load")
                elif world_kind == "heartbeat":
                    descriptors.append("the idle pulse")
                elif world_kind == "demo_trigger":
                    descriptors.append("a demo opportunity")
                elif world_kind:
                    descriptors.append(world_kind)
            description = _join_descriptions([d for d in descriptors if d])
            if urgent:
                return f"I noticed {description} — staying focused and ready."
            return f"I noticed {description} and I’m feeling calm and curious."

        experiment_failures = [
            e for e in events if e.get("kind") == "experiment_result" and not e.get("success")
        ]
        if experiment_failures:
            description = next(
                (str(e.get("description")) for e in experiment_failures if e.get("description")),
                None,
            )
            if description:
                return f"I noticed a failed experiment ({description}); staying attentive."
            return "I noticed a failed experiment and I’m staying attentive."

        runtime_errors = [
            e
            for e in events
            if e.get("kind") == "runtime_status"
            and str(e.get("status", "")).lower() == "error"
        ]
        if runtime_errors:
            components = sorted(
                {str(e.get("component") or "a component") for e in runtime_errors}
            )
            joined = ", ".join(components)
            return f"One component needed care ({joined}); I’m keeping watch."

        experiment_successes = [
            e for e in events if e.get("kind") == "experiment_result" and e.get("success")
        ]
        if experiment_successes:
            count = len(experiment_successes)
            if count > 1:
                return "Several experiments completed smoothly; optimism is steady."
            description = experiment_successes[0].get("description")
            if description:
                return f"An experiment succeeded ({description}); momentum feels good."
            return "An experiment succeeded; momentum feels good."

        return "I’m tracking the day’s signals and keeping the sanctuary steady."

    def _tick_once(self) -> str:
        with self._lock:
            now = datetime.now(timezone.utc)
            last_tick = self._last_tick
            self._last_tick = now
            dt = (now - last_tick).total_seconds() if last_tick else self._tick_interval

            decay_energy(self._state, dt)
            events = self._collect_events()
            for event in events:
                update_from_pulse(self._state, event)

            summary = self._build_summary(events)
            reflection_line = self._load_recent_reflection()
            if reflection_line:
                summary = f"{summary} {reflection_line}".strip()
                self._state.recent_reflection = reflection_line
            message = format_persona_message(
                self._state, summary, max_length=self._max_message_length
            )
            self._state.last_reflection = summary
            speak_callback = self._speak_callback

        self._logger.info(message)
        if speak_callback:
            try:
                speak_callback(message)
            except Exception:  # pragma: no cover - defensive logging
                self._logger.exception("Persona speak callback failed")
        return message

    def set_speak_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        with self._lock:
            self._speak_callback = callback

    def set_reflection_loader(self, loader: Optional[Callable[[], Optional[str]]]) -> None:
        with self._lock:
            self._reflection_loader = loader

    def _load_recent_reflection(self) -> Optional[str]:
        loader = self._reflection_loader
        if loader is None:
            return None
        try:
            reflection = loader()
        except Exception:  # pragma: no cover - defensive logging
            self._logger.exception("Persona reflection loader failed")
            return None
        if reflection:
            text = str(reflection).strip()
            return text if text else None
        return None
