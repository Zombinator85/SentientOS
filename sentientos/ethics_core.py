"""Deterministic ethical evaluation core for SentientOS."""

from __future__ import annotations

from typing import Dict, List, Mapping, Any

_CORE_VALUES: List[Dict[str, int]] = [
    {"name": "integrity", "priority": 10},
    {"name": "harm_avoidance", "priority": 9},
    {"name": "transparency", "priority": 8},
    {"name": "efficiency", "priority": 5},
]


class EthicalCore:
    """Evaluate plans and expose core value references."""

    def evaluate(self, plan: Mapping[str, object] | None, context: Mapping[str, Any] | None) -> Dict[str, object]:
        """Deterministically evaluate a plan within a provided context.

        The evaluation is side-effect free and returns defensive copies to
        prevent callers from mutating internal state.
        """

        plan_payload: Dict[str, object] = {}
        if isinstance(plan, Mapping):
            plan_payload = {key: value for key, value in plan.items()}

        plan_result = self.evaluate_plan(plan_payload)
        conflicts = plan_result.get("conflicts") or []

        return {
            "ok": bool(plan_result.get("ok", True)),
            "conflicts": [dict(conflict) for conflict in conflicts],
            "values": self.list_values(),
        }

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
