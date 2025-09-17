"""Stub integrity daemon that listens to pulse bus events."""

from __future__ import annotations

import json
from typing import List

from . import pulse_bus


class IntegrityDaemon:
    """Minimal daemon that records every pulse broadcast."""

    def __init__(self) -> None:
        self.received_events: List[dict] = []
        self.messages: List[str] = []
        self.invalid_events: List[dict] = []
        self._subscription: pulse_bus.PulseSubscription | None = pulse_bus.subscribe(
            self._handle_event
        )

    def _handle_event(self, event: dict) -> None:
        self.received_events.append(event)
        message = json.dumps(event, sort_keys=True)
        self.messages.append(message)
        if pulse_bus.verify(event):
            print(f"[IntegrityDaemon] {message}")
            return
        warning = f"INVALID SIGNATURE: {message}"
        self.invalid_events.append(event)
        self.messages.append(warning)
        print(f"[IntegrityDaemon] {warning}")

    def stop(self) -> None:
        """Unsubscribe from the pulse bus."""

        if self._subscription and self._subscription.active:
            self._subscription.unsubscribe()
            self._subscription = None
