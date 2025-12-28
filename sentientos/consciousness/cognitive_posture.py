from __future__ import annotations

from enum import Enum
from typing import Iterable, Mapping, Sequence


class CognitivePosture(str, Enum):
    """Enumerates deterministic qualitative stances derived from pressure."""

    STABLE = "stable"
    TENSE = "tense"
    OVERLOADED = "overloaded"


DEFAULT_POSTURE_HISTORY_WINDOW = 4


def _normalize_posture(value: str | CognitivePosture | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, CognitivePosture):
        return value.value
    if isinstance(value, str) and value.strip():
        normalized = value.strip().lower()
        if normalized in {posture.value for posture in CognitivePosture}:
            return normalized
    return None


def update_posture_history(
    history: Iterable[str] | None,
    posture: str | CognitivePosture | None,
    *,
    window: int = DEFAULT_POSTURE_HISTORY_WINDOW,
) -> list[str]:
    """Return a bounded history window with the latest posture appended."""

    if window <= 0:
        return []
    normalized_history = []
    if history is not None:
        for item in history:
            normalized = _normalize_posture(item)
            if normalized:
                normalized_history.append(normalized)
    latest = _normalize_posture(posture)
    if latest:
        normalized_history.append(latest)
    if len(normalized_history) > window:
        normalized_history = normalized_history[-window:]
    return normalized_history


def derive_posture_transition(history: Sequence[str]) -> dict[str, object]:
    """Derive posture transition metadata from a bounded history window."""

    normalized = []
    for item in history:
        normalized_item = _normalize_posture(item)
        if normalized_item:
            normalized.append(normalized_item)
    if not normalized:
        return {"current_posture": None, "posture_duration": 0, "posture_transition": None}
    current = normalized[-1]
    duration = 1
    for previous in reversed(normalized[:-1]):
        if previous != current:
            break
        duration += 1
    transition = None
    if len(normalized) >= 2:
        prior = normalized[-2]
        if prior != current:
            transition = f"{prior.upper()}→{current.upper()}"
    return {"current_posture": current, "posture_duration": duration, "posture_transition": transition}


def derive_cognitive_posture(pressure_snapshot: Mapping[str, object]) -> CognitivePosture:
    """Derive a qualitative posture from a deterministic pressure snapshot.

    Mapping rules:
    - OVERLOADED: one or more budgets exceeded (pressure_snapshot["overload"] truthy).
    - TENSE: pressure is accumulating but budgets are not exceeded (total_active_pressure > 0).
    - STABLE: pressure within budget (no overload and no active pressure).
    """

    overload = bool(pressure_snapshot.get("overload"))
    total_pressure = int(pressure_snapshot.get("total_active_pressure", 0) or 0)
    if overload:
        return CognitivePosture.OVERLOADED
    if total_pressure > 0:
        return CognitivePosture.TENSE
    return CognitivePosture.STABLE


__all__ = [
    "CognitivePosture",
    "DEFAULT_POSTURE_HISTORY_WINDOW",
    "derive_cognitive_posture",
    "derive_posture_transition",
    "update_posture_history",
]
