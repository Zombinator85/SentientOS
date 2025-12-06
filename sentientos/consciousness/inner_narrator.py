from __future__ import annotations

# NOTE:
# This module is part of the Consciousness Layer scaffolding.
# It does not perform autonomous execution.
# All operations must be driven by explicit orchestrator calls.
# Guardrails and covenant autoalignment remain authoritative.
"""Narrator scaffold that records bounded introspection outputs.

Reflections remain internal and only update self-model state or introspection
storage.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Mapping, Tuple

from sentientos.glow.self_state import (
    DEFAULT_SELF_STATE,
    save as save_self_state,
    validate as validate_self_state,
)
from sentientos.integrity import covenant_autoalign

# The narrator remains intentionally quiet; avoid noisy logging that could
# escape the privacy boundary.

IMPERATIVE_BLOCKLIST = {"modify", "alter", "create", "escalate", "override", "command"}
EXTERNAL_REFERENCES = {"user", "external", "customer", "client", "operator"}


def validate_reflection(text: str) -> str:
    """Validate reflection constraints and guardrails.

    Raises ``ValueError`` when constraints are violated.
    """

    if len(text) >= 400:
        raise ValueError("Reflection exceeds 400 character limit")
    lowered = text.lower()
    tokens = {token.strip(".,;:!?") for token in lowered.split()}
    for verb in IMPERATIVE_BLOCKLIST:
        if verb in tokens:
            raise ValueError(f"Imperative verb '{verb}' is not permitted in reflections")
    for token in EXTERNAL_REFERENCES:
        if token in lowered:
            raise ValueError("Reflections must not reference external entities or users")
    return text


def _derive_focus(pulse_snapshot: Mapping[str, object], self_model: Mapping[str, object]) -> str:
    focus_candidates = [
        pulse_snapshot.get("focus"),
        pulse_snapshot.get("primary_focus"),
    ]
    attention = pulse_snapshot.get("attention")
    if isinstance(attention, Mapping):
        focus_candidates.append(attention.get("target"))
    events = pulse_snapshot.get("events")
    if isinstance(events, list) and events:
        first = events[0]
        if isinstance(first, Mapping) and "type" in first:
            focus_candidates.append(str(first.get("type")))
        elif isinstance(first, str):
            focus_candidates.append(first)
    for candidate in focus_candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    fallback = self_model.get("last_focus")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return "introspection"


def _derive_mood(pulse_snapshot: Mapping[str, object], self_model: Mapping[str, object]) -> str:
    events = pulse_snapshot.get("events")
    warnings_present = bool(pulse_snapshot.get("warnings"))
    if warnings_present:
        return "uncertain"
    if isinstance(events, list) and events:
        return "curious"
    current = self_model.get("mood")
    if isinstance(current, str) and current in {"stable", "curious", "uncertain"}:
        return current
    return "stable"


def _derive_attention_level(pulse_snapshot: Mapping[str, object]) -> str:
    events = pulse_snapshot.get("events")
    if isinstance(events, list):
        if len(events) > 5:
            return "high"
        if len(events) > 0:
            return "elevated"
    return "baseline"


def generate_reflection(
    pulse_snapshot: Mapping[str, object], self_model: Mapping[str, object]
) -> Tuple[str, str, str, str]:
    """Create a deterministic, bounded reflection.

    Returns a tuple of reflection text, mood, focus, and attention level.
    """

    focus = _derive_focus(pulse_snapshot, self_model)
    mood = _derive_mood(pulse_snapshot, self_model)
    attention_level = _derive_attention_level(pulse_snapshot)
    cycle = pulse_snapshot.get("cycle") or pulse_snapshot.get("cycle_id")
    cycle_descriptor = f"cycle {cycle}" if cycle is not None else "current cycle"

    events = pulse_snapshot.get("events")
    event_note = "stable"
    if isinstance(events, list) and events:
        event_note = f"processed {len(events)} event(s)"

    attention_context = pulse_snapshot.get("attention", {}) if isinstance(pulse_snapshot.get("attention"), Mapping) else {}
    if isinstance(attention_context, Mapping) and attention_context.get("context"):
        context_desc = str(attention_context.get("context"))
    else:
        context_desc = focus

    sentences = [
        f"System {cycle_descriptor} {event_note}; noticed {focus}.",
        f"Internal interpretation steady; mood {mood}.",
        f"Attention directed toward {context_desc} due to recent pulse metadata.",
    ]
    reflection = " ".join(sentences[:3])
    validate_reflection(reflection)
    return reflection, mood, focus, attention_level


def _default_introspection_log() -> Path:
    return Path(os.getenv("SENTIENTOS_INTROSPECTION_LOG", "/daemon/logs/introspection.jsonl"))


def _introspection_log_path(log_path: Path | None = None) -> Path:
    """Resolve the introspection log path, creating parents as needed."""

    target = Path(log_path) if log_path else _default_introspection_log()
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def write_introspection_entry(
    reflection: str, focus: str, mood: str, cycle: object | None, *, log_path: Path | None = None
) -> Path:
    """Append an introspection entry within the glow mount."""

    target = _introspection_log_path(log_path)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reflection": reflection,
        "focus": focus,
        "mood": mood,
        "cycle": cycle,
    }
    line = json.dumps(entry, separators=(",", ":"))
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return target


def run_cycle(
    pulse_snapshot: Mapping[str, object], self_model: Mapping[str, object], *, log_path: Path | None = None
) -> str:
    """Generate and store an internal reflection without emitting externally."""

    covenant_autoalign.autoalign_before_cycle()
    reflection, mood, focus, attention_level = generate_reflection(pulse_snapshot, self_model)
    updated_model: Dict[str, object] = {**DEFAULT_SELF_STATE, **dict(self_model)}
    updated_model.update(
        {
            "last_reflection_summary": reflection,
            "mood": mood,
            "attention_level": attention_level,
            "last_focus": focus,
        }
    )
    validated = validate_self_state(updated_model)
    save_self_state(validated)
    write_introspection_entry(
        reflection,
        focus,
        mood,
        pulse_snapshot.get("cycle") or pulse_snapshot.get("cycle_id"),
        log_path=log_path,
    )
    return reflection


__all__ = [
    "generate_reflection",
    "run_cycle",
    "validate_reflection",
    "write_introspection_entry",
]
