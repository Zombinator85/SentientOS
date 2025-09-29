"""Dashboard view helpers for Codex generated tests."""
from __future__ import annotations

from typing import Any, Mapping

from codex.testcycles import TestProposal, TestSynthesizer

PANEL_TITLE = "Generated Tests"


def _proposal_to_entry(proposal: TestProposal) -> dict[str, Any]:
    entry = {
        "proposal_id": proposal.proposal_id,
        "spec_id": proposal.spec_id,
        "status": proposal.status,
        "coverage_target": proposal.coverage_target,
        "failure_context": proposal.failure_context,
        "feedback": proposal.feedback,
        "test_path": proposal.test_path,
        "style": proposal.style,
        "implementation_paths": list(proposal.implementation_paths),
    }
    if proposal.approved_at:
        entry["approved_at"] = proposal.approved_at
    if proposal.approved_by:
        entry["approved_by"] = proposal.approved_by
    if proposal.rejected_at:
        entry["rejected_at"] = proposal.rejected_at
    if proposal.rejection_reason:
        entry["rejection_reason"] = proposal.rejection_reason
    return entry


def generated_tests_panel_state(
    synthesizer: TestSynthesizer | None = None,
    *,
    spec_id: str | None = None,
) -> Mapping[str, Any]:
    """Summarize generated test proposals for operator dashboards."""

    synth = synthesizer or TestSynthesizer()
    pending = [_proposal_to_entry(item) for item in synth.pending(spec_id=spec_id)]
    approved = [_proposal_to_entry(item) for item in synth.approved(spec_id=spec_id)]
    return {
        "panel": PANEL_TITLE,
        "pending": pending,
        "approved": approved,
    }


__all__ = ["generated_tests_panel_state", "PANEL_TITLE"]
