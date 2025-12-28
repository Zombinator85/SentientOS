from __future__ import annotations

from enum import Enum
from typing import Mapping


class CognitivePosture(str, Enum):
    """Enumerates deterministic qualitative stances derived from pressure."""

    STABLE = "stable"
    TENSE = "tense"
    OVERLOADED = "overloaded"


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


__all__ = ["CognitivePosture", "derive_cognitive_posture"]
