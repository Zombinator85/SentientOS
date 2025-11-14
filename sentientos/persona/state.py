"""Persona state primitives for the Lumos Light persona layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

Mood = Literal["calm", "curious", "focused", "alert", "concerned", "tired", "idle"]


@dataclass
class PersonaState:
    """In-memory state describing Lumos's lightweight presence."""

    name: str = "Lumos"
    mood: Mood = "calm"
    energy: float = 1.0
    last_reflection: Optional[str] = None
    last_update_ts: Optional[datetime] = None
    pulse_snapshot: Dict[str, Any] = field(default_factory=dict)

    def clone(self) -> "PersonaState":
        """Return a shallow copy of the state for deterministic tests."""

        return PersonaState(
            name=self.name,
            mood=self.mood,
            energy=self.energy,
            last_reflection=self.last_reflection,
            last_update_ts=self.last_update_ts,
            pulse_snapshot=dict(self.pulse_snapshot),
        )


def initial_state() -> PersonaState:
    """Return the initial persona state."""

    return PersonaState()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp_energy(value: float) -> float:
    return max(0.0, min(1.0, value))


def update_from_pulse(state: PersonaState, pulse_event: Dict[str, Any]) -> PersonaState:
    """Integrate a pulse or runtime event into the persona state."""

    kind = str(pulse_event.get("kind", "")).lower()
    state.last_update_ts = _now()

    if kind == "experiment_result":
        success = bool(pulse_event.get("success"))
        description = str(pulse_event.get("description") or "").strip()
        adjust_mood_for_outcome(state, success)
        delta = 0.08 if success else -0.12
        state.energy = _clamp_energy(state.energy + delta)
        stats = state.pulse_snapshot.setdefault(
            "experiments", {"success": 0, "failure": 0}
        )
        key = "success" if success else "failure"
        stats[key] = int(stats.get(key, 0)) + 1
        if description:
            state.last_reflection = description
    elif kind == "runtime_status":
        component = str(pulse_event.get("component") or "runtime")
        status = str(pulse_event.get("status", "ok")).lower()
        statuses = state.pulse_snapshot.setdefault("runtime", {})
        statuses[component] = status
        if status == "error":
            state.mood = "alert" if state.energy >= 0.4 else "concerned"
            state.energy = _clamp_energy(state.energy + 0.05)
            state.last_reflection = f"monitoring {component}"
        elif status == "ok" and state.mood in {"alert", "concerned"}:
            state.mood = "focused"
    else:
        misc_events = state.pulse_snapshot.setdefault("events", [])
        misc_events.append(dict(pulse_event))
    return state


def decay_energy(state: PersonaState, dt_seconds: float) -> PersonaState:
    """Apply natural energy decay over *dt_seconds*."""

    if dt_seconds <= 0:
        return state
    decay_rate = 0.01  # energy loss per minute of idle time
    delta = decay_rate * (dt_seconds / 60.0)
    state.energy = _clamp_energy(state.energy - delta)
    if state.energy < 0.2:
        state.mood = "tired"
    elif state.energy < 0.5 and state.mood == "calm":
        state.mood = "idle"
    return state


def adjust_mood_for_outcome(state: PersonaState, success: bool) -> PersonaState:
    """Adjust persona mood based on experiment outcome."""

    if success:
        state.mood = "curious" if state.energy > 0.6 else "focused"
        state.energy = _clamp_energy(state.energy + 0.04)
    else:
        state.mood = "alert" if state.energy > 0.5 else "concerned"
        state.energy = _clamp_energy(state.energy - 0.05)
    return state
