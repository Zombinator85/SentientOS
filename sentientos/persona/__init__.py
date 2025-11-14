"""Lightweight persona subsystem for Lumos."""

from .state import (
    Mood,
    PersonaState,
    adjust_mood_for_outcome,
    decay_energy,
    initial_state,
    update_from_pulse,
)
from .events_bridge import make_persona_event_source
from .loop import PersonaLoop
from .text import format_persona_message

__all__ = [
    "Mood",
    "PersonaState",
    "PersonaLoop",
    "adjust_mood_for_outcome",
    "decay_energy",
    "format_persona_message",
    "initial_state",
    "make_persona_event_source",
    "update_from_pulse",
]
