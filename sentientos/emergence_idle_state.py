"""Explicit idle state marker for emergence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class IdleSnapshot:
    idle: bool
    governance_polling: bool
    reflection_mode: str
    pruner_status: str
    exit_conditions: tuple[str, ...]
    summary: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> str:
        return json.dumps(
            {
                "idle": self.idle,
                "governance_polling": self.governance_polling,
                "reflection_mode": self.reflection_mode,
                "pruner_status": self.pruner_status,
                "exit_conditions": list(self.exit_conditions),
                "summary": self.summary,
                "timestamp": self.timestamp,
            },
            indent=2,
            sort_keys=True,
        )

    def to_markdown(self) -> str:
        lines = [
            "# Emergence Idle State",
            "",
            f"- Idle: {self.idle}",
            f"- Governance Polling: {self.governance_polling}",
            f"- Reflection Mode: {self.reflection_mode}",
            f"- Context Pruner: {self.pruner_status}",
            "- Exit Conditions:",
            *[f"  - {reason}" for reason in self.exit_conditions],
            "",
            f"_Last updated {self.timestamp}_",
        ]
        return "\n".join(lines).strip() + "\n"


class EmergenceIdleState:
    """Mark and describe intentional idle windows for emergence."""

    def __init__(self, soft_threshold: float = 0.1) -> None:
        self.soft_threshold = float(soft_threshold)

    def evaluate(
        self,
        active_governance: Sequence[Mapping[str, object]],
        reflex_anomalies: Iterable[Mapping[str, object]],
        symbolic_drift: float,
    ) -> dict[str, object]:
        proposals_present = any(active_governance)
        anomalies_present = any(reflex_anomalies)
        drift_active = float(symbolic_drift) > self.soft_threshold

        idle = not (proposals_present or anomalies_present or drift_active)

        exit_conditions = self._exit_conditions(proposals_present, anomalies_present, drift_active)

        snapshot = IdleSnapshot(
            idle=idle,
            governance_polling=not idle,
            reflection_mode="summary" if idle else "full",
            pruner_status="stable" if idle else "tracking",
            exit_conditions=tuple(exit_conditions),
            summary=self._summary(idle, proposals_present, anomalies_present, drift_active),
        )

        return {
            "idle": idle,
            "snapshot": snapshot,
            "json": snapshot.to_json(),
            "markdown": snapshot.to_markdown(),
        }

    def _exit_conditions(self, proposals_present: bool, anomalies_present: bool, drift_active: bool) -> list[str]:
        conditions: list[str] = []
        if proposals_present:
            conditions.append("New governance proposal submitted")
        if anomalies_present:
            conditions.append("Reflex anomaly detected")
        if drift_active:
            conditions.append(f"Symbolic drift above {self.soft_threshold}")
        if not conditions:
            conditions.extend(
                [
                    "Proposal intake resumes",
                    "Reflex anomalies surface",
                    f"Symbolic drift exceeds {self.soft_threshold}",
                ]
            )
        return conditions

    def _summary(
        self, idle: bool, proposals_present: bool, anomalies_present: bool, drift_active: bool
    ) -> str:
        if idle:
            return "System idle: governance paused, reflection summarizing, context stable."

        reasons: list[str] = []
        if proposals_present:
            reasons.append("governance proposals in flight")
        if anomalies_present:
            reasons.append("reflex anomalies observed")
        if drift_active:
            reasons.append("symbolic drift above soft threshold")
        return "Idle suspended: " + ", ".join(reasons)


__all__ = ["EmergenceIdleState", "IdleSnapshot"]
