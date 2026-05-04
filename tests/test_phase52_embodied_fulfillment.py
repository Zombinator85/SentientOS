from pathlib import Path

from sentientos.embodiment_fulfillment import (
    append_embodied_fulfillment_receipt,
    build_embodied_fulfillment_candidate,
    build_embodied_fulfillment_receipt,
    classify_embodied_fulfillment_candidate_kind,
    classify_embodied_fulfillment_outcome,
    list_recent_embodied_fulfillment_receipts,
    resolve_embodied_fulfillment_candidates,
    resolve_embodied_fulfillment_state,
    summarize_embodied_fulfillment_status,
)
from sentientos.embodiment_proposal_diagnostic import summarize_recent_embodied_proposals


def _bridge(kind="memory_governance_review_candidate", posture="eligible_for_governance_review", privacy="review", consent="granted"):
    return {
        "governance_bridge_candidate_id": "gbc_1",
        "governance_bridge_candidate_kind": kind,
        "bridge_posture": posture,
        "source_handoff_candidate_ref": "handoff_candidate:h1",
        "source_proposal_id": "p1",
        "source_review_receipt_id": "r1",
        "source_ingress_receipt_ref": "ing:p1",
        "source_event_refs": ["evt:p1"],
        "correlation_id": "c1",
        "source_module": "sentientos.embodiment_ingress",
        "proposal_kind": "memory_ingress_candidate",
        "risk_flags": {"biometric_sensitive": True},
        "privacy_retention_posture": privacy,
        "consent_posture": consent,
        "candidate_payload_summary": {"x": 1},
        "rationale": ["r"],
    }


def test_candidate_builder_shape_and_invariants():
    row = build_embodied_fulfillment_candidate(governance_bridge_candidate=_bridge(), created_at=1.0)
    assert row["schema_version"].endswith("v1")
    assert row["fulfillment_candidate_kind"] == "memory_fulfillment_candidate"
    assert row["decision_power"] == "none"
    assert row["fulfillment_candidate_is_not_effect"] is True


def test_candidate_resolver_filters_and_blocks():
    ok = _bridge()
    blocked = _bridge(posture="blocked_handoff_not_eligible")
    unsupported = _bridge(kind="weird_kind")
    out = resolve_embodied_fulfillment_candidates(governance_bridge_candidates=[ok, blocked, unsupported], created_at=2.0)
    assert len(out["fulfillment_candidates"]) == 1
    assert out["blocked_fulfillment_counts_by_reason"]["blocked_bridge_not_eligible"] == 1
    assert out["blocked_fulfillment_counts_by_reason"]["blocked_unsupported_kind"] == 1


def test_privacy_consent_hold_and_kind_classification():
    row = build_embodied_fulfillment_candidate(governance_bridge_candidate=_bridge(privacy="sensitive", consent="required"))
    assert row["fulfillment_posture"] == "blocked_privacy_or_consent_required"
    assert classify_embodied_fulfillment_candidate_kind("vision_retention_governance_review_candidate") == "vision_retention_fulfillment_candidate"


def test_receipt_builder_and_outcome_normalization():
    candidate = build_embodied_fulfillment_candidate(governance_bridge_candidate=_bridge(), created_at=1.0)
    receipt = build_embodied_fulfillment_receipt(fulfillment_candidate=candidate, fulfillment_outcome="bogus", fulfiller_kind="test_fixture", created_at=2.0)
    assert receipt["fulfillment_outcome"] == "fulfillment_failed_validation"
    assert classify_embodied_fulfillment_outcome("fulfilled_by_governed_path") == "fulfilled_by_governed_path"
    assert receipt["fulfillment_receipt_is_not_effect"] is True
    assert receipt["receipt_does_not_prove_side_effect"] is True


def test_append_and_list_receipts(tmp_path: Path):
    p = tmp_path / "receipts.jsonl"
    candidate = build_embodied_fulfillment_candidate(governance_bridge_candidate=_bridge())
    r1 = build_embodied_fulfillment_receipt(fulfillment_candidate=candidate, fulfillment_outcome="fulfillment_declined", fulfiller_kind="operator")
    append_embodied_fulfillment_receipt(path=p, receipt=r1)
    rows = list_recent_embodied_fulfillment_receipts(path=p)
    assert len(rows) == 1


def test_fulfillment_state_and_summary():
    c = build_embodied_fulfillment_candidate(governance_bridge_candidate=_bridge(), created_at=1.0)
    state = resolve_embodied_fulfillment_state(fulfillment_candidate=c, fulfillment_receipts=[])
    assert state["fulfillment_outcome"] == "pending_fulfillment_review"
    r1 = build_embodied_fulfillment_receipt(fulfillment_candidate=c, fulfillment_outcome="fulfillment_declined", fulfiller_kind="operator", created_at=2.0)
    r2 = build_embodied_fulfillment_receipt(fulfillment_candidate=c, fulfillment_outcome="fulfilled_external_manual", fulfiller_kind="operator", created_at=3.0)
    state2 = resolve_embodied_fulfillment_state(fulfillment_candidate=c, fulfillment_receipts=[r1, r2])
    assert state2["fulfillment_outcome"] == "fulfilled_external_manual"
    summary = summarize_embodied_fulfillment_status(fulfillment_candidates=[c], fulfillment_receipts=[r1, r2])
    assert summary["fulfillment_counts_by_kind"]["memory_fulfillment_candidate"] == 1
    assert summary["fulfilled_receipt_count"] == 1


def test_diagnostic_additive_fulfillment_fields_present():
    proposals = [{"proposal_id": "p1", "proposal_kind": "memory_ingress_candidate", "source_module": "sentientos.embodiment_ingress", "source_event_refs": [], "rationale": [], "risk_flags": {}, "review_status": "pending_review", "ingress_receipt_ref": "ing:p1", "privacy_retention_posture": "review", "consent_posture": "granted", "candidate_payload_summary": {}}]
    reviews = [{"proposal_id": "p1", "review_outcome": "reviewed_approved_for_next_stage", "created_at": 1.0, "review_receipt_id": "r1"}]
    s = summarize_recent_embodied_proposals(proposals, review_receipts=reviews, generated_at=1.0)
    for key in ["fulfillment_candidate_count", "fulfillment_counts_by_kind", "blocked_fulfillment_counts_by_reason", "fulfillment_counts_by_outcome", "pending_fulfillment_review_count", "fulfilled_receipt_count", "fulfillment_posture"]:
        assert key in s
