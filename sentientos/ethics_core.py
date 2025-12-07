"""Stage 0 scaffolding for SentientOS ethical evaluation core."""

from __future__ import annotations

from typing import Dict, List


class EthicalCore:
    """Evaluate plans and expose core value references."""

    def evaluate_plan(self, plan: Dict[str, str]) -> Dict[str, str]:
        """Assess a proposed plan for ethical alignment."""
        raise NotImplementedError("EthicalCore.evaluate_plan is not implemented yet")

    def list_values(self) -> List[str]:
        """List the guiding ethical values used for evaluations."""
        raise NotImplementedError("EthicalCore.list_values is not implemented yet")
