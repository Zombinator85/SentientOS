"""
Simulation Engine scaffold for private counterfactual reasoning.

Supports lightweight, deterministic simulations that can be consumed by the
Sentience Kernel before emitting proposals.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class SimulationResult:
    name: str
    outcome: str
    confidence: float
    participants: List[str]


class SimulationEngine:
    """Executes simple simulated conversations between virtual agents."""

    def __init__(self) -> None:
        self.history: List[SimulationResult] = []

    def run(self, name: str, hypothesis: str, participants: Iterable[str] | None = None) -> SimulationResult:
        participants_list = list(participants) if participants else ["observer"]
        outcome = f"Hypothesis evaluated: {hypothesis}" if hypothesis else "No hypothesis provided"
        confidence = min(1.0, 0.3 + 0.05 * len(participants_list))
        result = SimulationResult(
            name=name,
            outcome=outcome,
            confidence=confidence,
            participants=participants_list,
        )
        self.history.append(result)
        return result

    def last_result(self) -> SimulationResult | None:
        return self.history[-1] if self.history else None


__all__ = ["SimulationEngine", "SimulationResult"]
