"""Stage 2 implementation for SentientOS identity management."""

from __future__ import annotations

from typing import Any, Dict, List


class IdentityManager:
    """Manage self-referential identity data and reflection events."""

    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []
        self._self_concept: Dict[str, str] = {}
        self._timestamp_counter: int = 0

    def log_event(self, event_type: str, description: str) -> None:
        """Record an identity-related event for later reflection."""
        self._timestamp_counter += 1
        event = {
            "timestamp": self._timestamp_counter,
            "type": event_type,
            "description": description,
        }
        self._events.append(event)

    def get_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent identity events up to the requested limit."""
        if limit <= 0:
            return []

        recent_events = self._events[-limit:]
        return [event.copy() for event in recent_events]

    def summarize(self) -> str:
        """Generate a textual summary of recent identity activity."""
        event_count = len(self._events)
        event_types = {event["type"] for event in self._events}
        trait_count = len(self._self_concept)

        return (
            f"Identity summary: {event_count} events, "
            f"{len(event_types)} event types, "
            f"{trait_count} self-concept traits."
        )

    def get_self_concept(self) -> Dict[str, str]:
        """Return the current self-concept representation."""
        return dict(self._self_concept)

    def update_self_concept(self, key: str, value: str) -> None:
        """Update a single attribute of the self-concept representation."""
        self._self_concept[key] = value
