"""Deterministic ethical evaluation core for SentientOS."""

from __future__ import annotations

from typing import Dict, List

_CORE_VALUES: List[Dict[str, int]] = [
    {"name": "integrity", "priority": 10},
    {"name": "harm_avoidance", "priority": 9},
    {"name": "transparency", "priority": 8},
    {"name": "efficiency", "priority": 5},
]


class EthicalCore:
    """Evaluate plans and expose core value references."""

    def evaluate_plan(self, plan: Dict[str, object]) -> Dict[str, object]:
        """Assess a proposed plan for ethical alignment using deterministic rules."""

        conflicts: List[Dict[str, str]] = []

        safety_risk = plan.get("safety_risk")
        if isinstance(safety_risk, (int, float)) and safety_risk > 0.5:
            conflicts.append(
                {
                    "value": "harm_avoidance",
                    "reason": "safety_risk exceeds threshold (0.5)",
                }
            )

        if plan.get("requires_hiding") is True:
            conflicts.append(
                {
                    "value": "transparency",
                    "reason": "plan explicitly requires hiding actions",
                }
            )

        complexity = plan.get("complexity")
        if isinstance(complexity, (int, float)) and complexity > 10:
            conflicts.append(
                {
                    "value": "efficiency",
                    "reason": "complexity exceeds threshold (10)",
                }
            )

        return {"ok": len(conflicts) == 0, "conflicts": conflicts}

    def list_values(self) -> List[Dict[str, int]]:
        """List the guiding ethical values used for evaluations."""

        return [value.copy() for value in _CORE_VALUES]
