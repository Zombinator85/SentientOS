from __future__ import annotations

from pathlib import Path

from sentientos.embodiment_proposal_diagnostic import summarize_recent_embodied_proposals
from sentientos.embodiment_proposal_review import (
    append_embodied_proposal_review_receipt,
    build_embodied_proposal_review_receipt,
    list_recent_embodied_proposal_review_receipts,
    resolve_embodied_proposal_review_state,
)
from sentientos.embodiment_proposals import build_embodied_proposal_record


def _proposal(pid: str, *, t: float = 1.0):
    row = build_embodied_proposal_record(source_module="mic_bridge", gate_mode="proposal_only", blocked_effect_type="memory_write", ingress_receipt={"ingress_id": f"i-{pid}"}, created_at=t)
    row["proposal_id"] = pid
    return row


def test_phase50_review_builder_shape_and_non_authority():
    proposal = _proposal("p1")
    receipt = build_embodied_proposal_review_receipt(proposal_record=proposal, review_outcome="reviewed_approved_for_next_stage", reviewer_kind="operator", reviewer_label="alice")
    assert receipt["proposal_id"] == "p1"
    assert receipt["review_outcome"] == "reviewed_approved_for_next_stage"
    assert receipt["decision_power"] == "none"
    assert receipt["approval_is_not_execution"] is True
    assert receipt["does_not_write_memory"] is True
    assert receipt["does_not_trigger_feedback"] is True


def test_phase50_append_and_list_review_receipts(tmp_path: Path):
    proposal = _proposal("p2")
    r1 = build_embodied_proposal_review_receipt(proposal_record=proposal, review_outcome="reviewed_deferred", reviewer_kind="test_fixture")
    r2 = build_embodied_proposal_review_receipt(proposal_record=proposal, review_outcome="reviewed_rejected", reviewer_kind="test_fixture", created_at=5.0)
    path = tmp_path / "reviews.jsonl"
    append_embodied_proposal_review_receipt(r1, path=path)
    append_embodied_proposal_review_receipt(r2, path=path)
    rows = list_recent_embodied_proposal_review_receipts(path=path, limit=10)
    assert len(rows) == 2
    assert rows[-1]["review_outcome"] == "reviewed_rejected"


def test_phase50_review_state_resolver_latest_receipt_wins():
    p = _proposal("p3")
    older = build_embodied_proposal_review_receipt(proposal_record=p, review_outcome="reviewed_needs_more_context", reviewer_kind="diagnostic", created_at=1.0)
    newer = build_embodied_proposal_review_receipt(proposal_record=p, review_outcome="reviewed_approved_for_next_stage", reviewer_kind="operator", created_at=3.0)
    state = resolve_embodied_proposal_review_state(proposals=[p], review_receipts=[older, newer])
    assert state["p3"] == "approved_for_next_stage"
    assert resolve_embodied_proposal_review_state(proposals=[p], review_receipts=[])["p3"] == "pending_review"


def test_phase50_summary_integration_review_counts():
    p1 = _proposal("p4", t=1.0)
    p2 = _proposal("p5", t=2.0)
    r1 = build_embodied_proposal_review_receipt(proposal_record=p1, review_outcome="reviewed_rejected", reviewer_kind="operator")
    summary = summarize_recent_embodied_proposals([p1, p2], review_receipts=[r1], generated_at=9.0)
    assert summary["rejected_count"] == 1
    assert summary["pending_without_review_count"] == 1
    assert summary["approved_for_next_stage_count"] == 0
    assert summary["decision_power"] == "none"
