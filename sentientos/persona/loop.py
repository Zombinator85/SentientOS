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
        if not events:
            if self._state.mood in {"tired", "idle"}:
                return "Quietly tending the cadence while I recharge."
            return "All systems look steady."

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
            message = format_persona_message(
                self._state, summary, max_length=self._max_message_length
            )
            self._state.last_reflection = summary

        self._logger.info(message)
        return message
