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
        self.federated_restarts: List[dict[str, object]] = []
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
        if self._is_federated_restart(event):
            summary = self._build_federated_summary(event)
            if summary is not None:
                self.federated_restarts.append(summary)
                print(
                    "[MonitoringDaemon] federated_restart "
                    f"daemon={summary['daemon_name']} "
                    f"requested_by={summary['requested_by']} "
                    f"executor={summary['executor_peer']} "
                    f"outcome={summary['outcome']}"
                )
        print(f"[MonitoringDaemon] {message}")

    def stop(self) -> None:
        """Unsubscribe from the pulse bus."""

        if self._subscription and self._subscription.active:
            self._subscription.unsubscribe()
            self._subscription = None

    def _is_federated_restart(self, event: dict[str, object]) -> bool:
        if str(event.get("event_type", "")).lower() != "daemon_restart":
            return False
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return False
        scope = str(payload.get("scope", "")).lower()
        return scope == "federated"

    def _build_federated_summary(
        self, event: dict[str, object]
    ) -> dict[str, object] | None:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return None
        daemon_name = payload.get("daemon_name") or payload.get("daemon")
        if daemon_name is None:
            return None
        executor = str(event.get("source_peer", "local"))
        requested_by = str(payload.get("requested_by", "unknown"))
        outcome = str(payload.get("outcome", "unknown"))
        summary: dict[str, object] = {
            "daemon_name": str(daemon_name),
            "requested_by": requested_by,
            "executor_peer": executor,
            "outcome": outcome,
        }
        return summary
