"""Stub integrity daemon that listens to pulse bus events."""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, List

from . import pulse_bus


class IntegrityDaemon:
    """Minimal daemon that records every pulse broadcast."""

    def __init__(self) -> None:
        self.received_events: List[dict[str, object]] = []
        self.messages: List[str] = []
        self.invalid_events: List[dict[str, object]] = []
        self.alerts: List[dict[str, object]] = []
        self._restart_window = timedelta(minutes=5)
        self._invalid_times: Deque[datetime] = deque()
        self._last_restart_request: datetime | None = None
        self._subscription: pulse_bus.PulseSubscription | None = pulse_bus.subscribe(
            self._handle_event
        )

    def _handle_event(self, event: dict[str, object]) -> None:
        self.received_events.append(event)
        message = json.dumps(event, sort_keys=True)
        self.messages.append(message)
        priority = str(event.get("priority", "info")).lower()
        if pulse_bus.verify(event):
            print(f"[IntegrityDaemon] {message}")
            if priority == "critical":
                self.alerts.append(event)
                print(f"[IntegrityDaemon][ALERT] {message}")
            return
        warning = f"INVALID SIGNATURE: {message}"
        self.invalid_events.append(event)
        self.messages.append(warning)
        self.alerts.append(event)
        print(f"[IntegrityDaemon] {warning}")
        self._record_invalid_signature()
        violation_timestamp = datetime.now(timezone.utc).isoformat()
        payload = {
            "timestamp": violation_timestamp,
            "source_event": {
                "source_daemon": str(event.get("source_daemon", "unknown")),
                "event_type": str(event.get("event_type", "unknown")),
            },
            "detail": "signature_mismatch",
        }
        pulse_bus.publish(
            {
                "timestamp": violation_timestamp,
                "source_daemon": "integrity",
                "event_type": "integrity_violation",
                "priority": "critical",
                "payload": payload,
            }
        )

    def stop(self) -> None:
        """Unsubscribe from the pulse bus."""

        if self._subscription and self._subscription.active:
            self._subscription.unsubscribe()
            self._subscription = None

    def _record_invalid_signature(self) -> None:
        now = datetime.now(timezone.utc)
        self._invalid_times.append(now)
        cutoff = now - self._restart_window
        while self._invalid_times and self._invalid_times[0] < cutoff:
            self._invalid_times.popleft()
        if len(self._invalid_times) < 3:
            return
        if self._last_restart_request and now - self._last_restart_request < self._restart_window:
            return
        self._publish_restart_request("signature_mismatch")
        self._last_restart_request = now

    def _publish_restart_request(self, reason: str) -> None:
        payload = {
            "action": "restart_daemon",
            "daemon": "integrity",
            "reason": reason,
        }
        pulse_bus.publish(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_daemon": "integrity",
                "event_type": "restart_request",
                "priority": "critical",
                "payload": payload,
            }
        )
