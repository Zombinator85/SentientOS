"""Monitoring daemon that surfaces higher priority pulse bus events."""

from __future__ import annotations

import json
from typing import List

from . import pulse_bus


class MonitoringDaemon:
    """Simple subscriber that highlights warning and critical pulses."""

    def __init__(self) -> None:
        self.events: List[dict[str, object]] = []
        self.messages: List[str] = []
        self.warning_events: List[dict[str, object]] = []
        self.critical_events: List[dict[str, object]] = []
        self._subscription: pulse_bus.PulseSubscription | None = pulse_bus.subscribe(
            self._handle_event,
            priorities=("warning", "critical"),
        )

    def _handle_event(self, event: dict[str, object]) -> None:
        priority = str(event.get("priority", "info")).lower()
        self.events.append(event)
        message = json.dumps(event, sort_keys=True)
        self.messages.append(message)
        if priority == "warning":
            self.warning_events.append(event)
        elif priority == "critical":
            self.critical_events.append(event)
        print(f"[MonitoringDaemon] {message}")

    def stop(self) -> None:
        """Unsubscribe from the pulse bus."""

        if self._subscription and self._subscription.active:
            self._subscription.unsubscribe()
            self._subscription = None
