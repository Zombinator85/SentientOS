"""Unified orchestration layer for SentientOS subsystems.

This module intentionally wires together deterministic surfaces only. All
approval-gated operations defer to the SSA agent's explicit checks and never
persist data unless an approval flag is provided at construction time.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agents.forms.ssa_disability_agent import SSADisabilityAgent

from sentientos.consciousness.integration import run_consciousness_cycle


class SentientOrchestrator:
    """Expose a stable façade for orchestrating SentientOS capabilities."""

    def __init__(self, profile: Optional[dict] = None, approval: bool = False):
        self.profile = profile
        self.approval = approval
        self.agent: Optional["SSADisabilityAgent"] = (
            self._build_agent(profile) if profile is not None else None
        )

    @staticmethod
    def _build_agent(profile: dict):
        from agents.forms.ssa_disability_agent import SSADisabilityAgent

        return SSADisabilityAgent(profile)

    def _require_agent(self) -> Dict[str, str]:
        return {"error": "no_profile_loaded"}

    def run_consciousness_cycle(self) -> Dict[str, Any]:
        """Run a deterministic consciousness cycle with no side effects."""

        return run_consciousness_cycle({})

    def ssa_prefill_827(self) -> Dict[str, Any]:
        if self.agent is None:
            return self._require_agent()
        return self.agent.prefill_ssa_827(approval_flag=self.approval)

    def ssa_dry_run(self) -> Dict[str, Any]:
        if self.agent is None:
            return self._require_agent()
        return self.agent.dry_run()

    def ssa_execute(self, relay) -> Dict[str, Any]:
        if self.agent is None:
            return self._require_agent()
        return self.agent.execute(relay, approval_flag=self.approval)

    def ssa_review_bundle(self, execution_result: Dict[str, Any], pdf_bytes: bytes):
        if self.agent is None:
            return self._require_agent()
        return self.agent.build_review_bundle(execution_result, pdf_bytes)

    def export_review_bundle(self, bundle: Any):
        if self.agent is None:
            return self._require_agent()
        return self.agent.export_review_bundle(bundle, approved=self.approval)


__all__ = ["SentientOrchestrator"]
