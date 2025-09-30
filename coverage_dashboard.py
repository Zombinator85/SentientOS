"""Dashboard helpers for Codex coverage mapping."""
from __future__ import annotations

from typing import Any, Mapping

from codex.coverage import CoverageAnalyzer
from codex.testcycles import TestProposal, TestSynthesizer

PANEL_TITLE = "Coverage Map"


def _proposal_entry(proposal: TestProposal) -> dict[str, Any]:
    payload = {
        "proposal_id": proposal.proposal_id,
        "spec_id": proposal.spec_id,
        "status": proposal.status,
        "coverage_target": proposal.coverage_target,
        "created_at": proposal.created_at,
        "test_path": proposal.test_path,
        "style": proposal.style,
    }
    if proposal.approved_at:
        payload["approved_at"] = proposal.approved_at
    if proposal.approved_by:
        payload["approved_by"] = proposal.approved_by
    if proposal.rejected_at:
        payload["rejected_at"] = proposal.rejected_at
    if proposal.rejection_reason:
        payload["rejection_reason"] = proposal.rejection_reason
    return payload


def coverage_panel_state(
    analyzer: CoverageAnalyzer | None = None,
    *,
    synthesizer: TestSynthesizer | None = None,
) -> Mapping[str, Any]:
    """Return structured state for the Coverage Map dashboard."""

    coverage_analyzer = analyzer or CoverageAnalyzer()
    synth = synthesizer or coverage_analyzer.synthesizer
    coverage_map = coverage_analyzer.load_map()
    pending = [_proposal_entry(item) for item in synth.pending()]
    approved = [_proposal_entry(item) for item in synth.approved()]
    return {
        "panel": PANEL_TITLE,
        "coverage": coverage_map,
        "pending_proposals": pending,
        "approved_proposals": approved,
        "requires_operator_approval": bool(pending),
    }


def approve_coverage_proposal(
    proposal_id: str,
    *,
    operator: str,
    synthesizer: TestSynthesizer | None = None,
) -> dict[str, Any]:
    synth = synthesizer or TestSynthesizer()
    proposal = synth.approve(proposal_id, operator=operator)
    return _proposal_entry(proposal)


def reject_coverage_proposal(
    proposal_id: str,
    *,
    operator: str,
    reason: str,
    synthesizer: TestSynthesizer | None = None,
) -> dict[str, Any]:
    synth = synthesizer or TestSynthesizer()
    proposal = synth.reject(proposal_id, operator=operator, reason=reason)
    return _proposal_entry(proposal)


__all__ = [
    "PANEL_TITLE",
    "coverage_panel_state",
    "approve_coverage_proposal",
    "reject_coverage_proposal",
]
