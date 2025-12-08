"""Sandboxed inner simulation engine for hypothetical cognition cycles."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


class SimulationEngine:
    """Run deterministic, side-effect free inner-world simulations."""

    def simulate(self, orchestrator: Any, hypothetical_state: Dict[str, Any]) -> Dict[str, Any]:
        """Run a deterministic inner simulation and return a sandboxed cycle report."""

        sandbox_state = deepcopy(hypothetical_state or {})
        sandbox_orchestrator = deepcopy(orchestrator)

        ethics = sandbox_orchestrator.evaluate_ethics(
            plan=sandbox_state.get("plan"),
            context=sandbox_state,
        )

        report = sandbox_orchestrator.run_cycle(sandbox_state)

        sanitized_report: Dict[str, Any] = deepcopy(report)
        sanitized_report["ethics"] = deepcopy(ethics)
        sanitized_report["cycle_id"] = -1
        sanitized_report["timestamp"] = None

        return {
            "simulated": True,
            "hypothetical_state": deepcopy(sandbox_state),
            "report": sanitized_report,
        }
