import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.embodiment_proposal_handoff import resolve_embodied_handoff_candidates, build_embodied_handoff_candidate
from sentientos.embodiment_governance_bridge import resolve_embodied_governance_bridge_candidates, build_embodied_governance_bridge_candidate
from sentientos.embodiment_proposal_diagnostic import summarize_recent_embodied_proposals


def _proposal(pid: str, kind: str):
    return {
        "proposal_id": pid,
        "proposal_kind": kind,
        "source_module": "sentientos.embodiment_ingress",
        "ingress_receipt_ref": f"ing:{pid}",
        "source_event_refs": [f"evt:{pid}"],
        "risk_flags": {},
        "privacy_retention_posture": "review",
        "consent_posture": "granted",
        "candidate_payload_summary": {"x": 1},
        "rationale": ["r"],
    }


def _review(pid: str, outcome: str, ts: float, rid: str):
    return {"proposal_id": pid, "review_outcome": outcome, "created_at": ts, "review_receipt_id": rid}


def test_handoff_filters_only_review_approved_and_latest_wins():
    proposals = [_proposal("p1", "memory_ingress_candidate"), _proposal("p2", "feedback_action_candidate")]
    reviews = [
        _review("p1", "reviewed_rejected", 1.0, "r1"),
        _review("p1", "reviewed_approved_for_next_stage", 2.0, "r2"),
        _review("p2", "reviewed_deferred", 3.0, "r3"),
    ]
    resolved = resolve_embodied_handoff_candidates(proposals=proposals, review_receipts=reviews, created_at=10.0)
    assert len(resolved["handoff_candidates"]) == 1
    row = resolved["handoff_candidates"][0]
    assert row["source_proposal_id"] == "p1"
    assert row["handoff_posture"] == "eligible_for_next_stage_review"
    assert row["handoff_is_not_fulfillment"] is True


def test_handoff_kind_mapping_and_non_authority_fields():
    kinds = {
        "memory_ingress_candidate": "memory_ingress_handoff_candidate",
        "feedback_action_candidate": "feedback_action_handoff_candidate",
        "screen_retention_candidate": "screen_retention_handoff_candidate",
        "vision_retention_candidate": "vision_retention_handoff_candidate",
        "multimodal_retention_candidate": "multimodal_retention_handoff_candidate",
        "operator_attention_candidate": "operator_attention_handoff_candidate",
    }
    for i, (pk, hk) in enumerate(kinds.items()):
        row = build_embodied_handoff_candidate(
            proposal_record=_proposal(f"p{i}", pk),
            review_receipt=_review(f"p{i}", "reviewed_approved_for_next_stage", 1.0, f"r{i}"),
        )
        assert row["handoff_candidate_kind"] == hk
        assert row["approval_is_not_execution"] is True
        assert row["does_not_admit_work"] is True


def test_bridge_candidate_behavior_and_privacy_hold():
    handoff = build_embodied_handoff_candidate(
        proposal_record={**_proposal("p9", "screen_retention_candidate"), "privacy_retention_posture": "sensitive", "consent_posture": "not_asserted"},
        review_receipt=_review("p9", "reviewed_approved_for_next_stage", 1.0, "r9"),
    )
    bridge = build_embodied_governance_bridge_candidate(handoff_candidate=handoff)
    assert bridge["bridge_posture"] == "blocked_privacy_or_consent_required"
    assert bridge["bridge_is_not_admission"] is True


def test_bridge_resolver_emits_only_eligible_and_no_executor_imports():
    ok = build_embodied_handoff_candidate(
        proposal_record=_proposal("p10", "memory_ingress_candidate"),
        review_receipt=_review("p10", "reviewed_approved_for_next_stage", 1.0, "r10"),
    )
    blocked = {**ok, "handoff_candidate_id": "x2", "handoff_candidate_kind": "unsupported"}
    out = resolve_embodied_governance_bridge_candidates(handoff_candidates=[ok, blocked], created_at=5.0)
    assert len(out["governance_bridge_candidates"]) == 1
    assert out["blocked_bridge_counts_by_reason"]["blocked_unsupported_kind"] == 1


def test_diagnostic_additive_fields_present():
    proposals = [_proposal("p11", "memory_ingress_candidate")]
    reviews = [_review("p11", "reviewed_approved_for_next_stage", 1.0, "r11")]
    summary = summarize_recent_embodied_proposals(proposals, review_receipts=reviews, generated_at=2.0)
    assert "review_counts_by_outcome" in summary
    assert "handoff_candidate_count" in summary
    assert "governance_bridge_candidate_count" in summary
