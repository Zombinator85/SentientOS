from __future__ import annotations

from enum import Enum
from typing import Iterable, Mapping, Sequence


class CognitivePosture(str, Enum):
    """Enumerates deterministic qualitative stances derived from pressure."""

    STABLE = "stable"
    TENSE = "tense"
    OVERLOADED = "overloaded"


class LoadNarrative(str, Enum):
    """Low-resolution load narrative descriptor derived from posture history."""

    STABLE_OPERATION = "STABLE_OPERATION"
    ACCUMULATING_TENSION = "ACCUMULATING_TENSION"
    SUSTAINED_TENSION = "SUSTAINED_TENSION"
    OVERLOADED = "OVERLOADED"
    RECOVERING = "RECOVERING"


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


def derive_load_narrative(
    posture_history: Sequence[str] | None,
    transitions: Mapping[str, object] | None,
) -> LoadNarrative:
    """Derive a deterministic, non-causal load narrative from posture history.

    Mapping rules (cycle-count-based only):
    - OVERLOADED: current posture is ``overloaded`` (any duration).
    - SUSTAINED_TENSION: current posture is ``tense`` with duration >= 3 cycles.
    - ACCUMULATING_TENSION: current posture is ``tense`` with duration < 3 cycles.
    - RECOVERING: current posture is ``stable`` after a tense/overloaded transition
      within the last 1-2 cycles.
    - STABLE_OPERATION: default baseline for steady stable posture or empty history.
    """

    history = posture_history or []
    transition_data = transitions
    if transition_data is None:
        transition_data = derive_posture_transition(history)
    current_posture = transition_data.get("current_posture")
    if isinstance(current_posture, CognitivePosture):
        current_posture = current_posture.value
    duration = int(transition_data.get("posture_duration") or 0)
    transition = transition_data.get("posture_transition")
    if not isinstance(current_posture, str) or not current_posture:
        return LoadNarrative.STABLE_OPERATION
    if current_posture == CognitivePosture.OVERLOADED.value:
        return LoadNarrative.OVERLOADED
    if current_posture == CognitivePosture.TENSE.value:
        if duration >= 3:
            return LoadNarrative.SUSTAINED_TENSION
        return LoadNarrative.ACCUMULATING_TENSION
    if current_posture == CognitivePosture.STABLE.value:
        prior = None
        if isinstance(transition, str) and "→" in transition:
            prior = transition.split("→", maxsplit=1)[0].lower()
        if prior in {CognitivePosture.TENSE.value, CognitivePosture.OVERLOADED.value} and duration <= 2:
            return LoadNarrative.RECOVERING
        return LoadNarrative.STABLE_OPERATION
    return LoadNarrative.STABLE_OPERATION


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
    "LoadNarrative",
    "DEFAULT_POSTURE_HISTORY_WINDOW",
    "derive_cognitive_posture",
    "derive_load_narrative",
    "derive_posture_transition",
    "update_posture_history",
]
