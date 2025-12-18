"""Read-only pressure governor for memory flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class PressureAdvisory:
    pressure: float
    slow_down: bool
    archive_aggressiveness: float
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "pressure": self.pressure,
            "slow_down": self.slow_down,
            "archive_aggressiveness": self.archive_aggressiveness,
            "notes": list(self.notes),
        }


class MemoryPressureGovernor:
    """Compute advisory pressure without mutating any upstream ledgers."""

    def __init__(
        self,
        context_budget_bytes: int = 512_000,
        archive_capacity_per_cycle: float = 12.0,
        ledger_growth_capacity: float = 500.0,
        slowdown_threshold: float = 0.72,
    ) -> None:
        self.context_budget_bytes = max(1, int(context_budget_bytes))
        self.archive_capacity_per_cycle = max(0.1, float(archive_capacity_per_cycle))
        self.ledger_growth_capacity = max(0.1, float(ledger_growth_capacity))
        self.slowdown_threshold = float(slowdown_threshold)

    def evaluate(
        self,
        context_pruner_output: Mapping[str, object],
        archive_rate_per_cycle: float,
        ledger_growth_velocity: float,
    ) -> dict[str, object]:
        totals = context_pruner_output.get("totals", {}) if isinstance(context_pruner_output, Mapping) else {}
        context_bytes = float(totals.get("bytes", 0)) if hasattr(totals, "get") else 0.0
        context_pressure = context_bytes / self.context_budget_bytes

        archive_pressure = float(archive_rate_per_cycle) / self.archive_capacity_per_cycle
        ledger_pressure = float(ledger_growth_velocity) / self.ledger_growth_capacity

        pressure_score = self._clamp(0.5 * context_pressure + 0.25 * archive_pressure + 0.25 * ledger_pressure)
        advisory = PressureAdvisory(
            pressure=round(pressure_score, 3),
            slow_down=pressure_score >= self.slowdown_threshold,
            archive_aggressiveness=round(self._clamp(pressure_score + archive_pressure * 0.25), 3),
            notes=self._notes(context_bytes, archive_rate_per_cycle, ledger_growth_velocity, pressure_score),
        )

        return {
            "pressure": advisory.pressure,
            "advisory": advisory,
            "inputs": {
                "context_bytes": context_bytes,
                "archive_rate_per_cycle": float(archive_rate_per_cycle),
                "ledger_growth_velocity": float(ledger_growth_velocity),
            },
        }

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def _notes(
        self, context_bytes: float, archive_rate_per_cycle: float, ledger_growth_velocity: float, pressure_score: float
    ) -> tuple[str, ...]:
        notes: list[str] = []
        if pressure_score < 0.25:
            notes.append("Memory pressure nominal")
        if context_bytes >= self.context_budget_bytes:
            notes.append("Context footprint at or above budget")
        if archive_rate_per_cycle > self.archive_capacity_per_cycle:
            notes.append("Archive velocity exceeds capacity")
        if ledger_growth_velocity > self.ledger_growth_capacity:
            notes.append("Ledger growth exceeds velocity budget")
        if pressure_score >= self.slowdown_threshold:
            notes.append("Advisory slow-down triggered")
        return tuple(notes)


__all__ = ["MemoryPressureGovernor", "PressureAdvisory"]
