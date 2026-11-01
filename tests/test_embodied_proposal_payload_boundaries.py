from __future__ import annotations

import pytest

from sentientos.embodiment_proposal_diagnostic import summarize_recent_embodied_proposals
from sentientos.embodiment_proposal_review import summarize_embodied_proposal_review_status
from sentientos.embodiment_proposals import build_embodied_proposal_record

pytestmark = pytest.mark.no_legacy_skip


def test_proposal_summary_accepts_sequences_and_ignores_malformed_optional_fields() -> None:
    proposal = build_embodied_proposal_record(
        source_module="test",
        gate_mode="proposal_only",
        blocked_effect_type="memory_write",
        ingress_receipt={"ingress_id": "ingress-1"},
        created_at=1.0,
    )
    proposal["created_at"] = "invalid"
    proposal["risk_flags"] = {"emotion_sensitive": {"unexpected": True}}
    proposal["candidate_payload_summary"] = object()
    proposals = [proposal]

    summary = summarize_recent_embodied_proposals(proposals, review_receipts=[])

    assert summary["pending_review_count"] == 1
    assert summary["oldest_pending_created_at"] is None
    assert summary["high_risk_counts"]["biometric_or_emotion_sensitive"] == 1


def test_review_status_summary_ignores_non_mapping_risk_flags() -> None:
    summary = summarize_embodied_proposal_review_status(
        proposals=[{"proposal_id": "p1", "risk_flags": None}],
        review_receipts=[],
    )

    assert summary["pending_without_review_count"] == 1
    assert summary["review_posture"] == "pending_review_items"


def test_review_status_summary_uses_safe_timestamp_for_malformed_receipts() -> None:
    summary = summarize_embodied_proposal_review_status(
        proposals=[{"proposal_id": "p1", "risk_flags": None}],
        review_receipts=[{
            "proposal_id": "p1",
            "review_outcome": "reviewed_rejected",
            "created_at": "invalid",
        }],
    )

    assert summary["rejected_count"] == 1
