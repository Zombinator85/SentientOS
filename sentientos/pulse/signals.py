from dataclasses import dataclass
from typing import Any, Literal

PulseLevel = Literal["STABLE", "WARNING", "DEGRADED"]


@dataclass(frozen=True)
class PulseSignal:
    level: PulseLevel
    reason: str
    metrics: dict[str, Any]
    window: int
