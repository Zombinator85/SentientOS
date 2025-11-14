"""Formatting helpers for Lumos persona messaging."""

from __future__ import annotations

from typing import Mapping

from .state import Mood, PersonaState


_MOOD_PHRASES: Mapping[Mood, str] = {
    "calm": "I’m feeling calm and observant.",
    "curious": "Curiosity is guiding me gently forward.",
    "focused": "Staying focused on the work ahead.",
    "alert": "Remaining alert and ready to steady things.",
    "concerned": "I’m concerned but keeping a careful watch.",
    "tired": "My energy is lower, so I’m pacing myself.",
    "idle": "Quietly observing while things stay still.",
}


def format_persona_message(
    state: PersonaState,
    summary: str,
    *,
    max_length: int = 200,
) -> str:
    """Return a short, one-line persona message in Lumos’s tone."""

    summary = " ".join(summary.strip().split())
    mood_phrase = _MOOD_PHRASES.get(state.mood, "Staying present with you.")
    message = f"{state.name}: {summary} {mood_phrase}".strip()
    if len(message) > max_length:
        truncated = message[: max_length - 1].rstrip()
        message = f"{truncated}…"
    return message
