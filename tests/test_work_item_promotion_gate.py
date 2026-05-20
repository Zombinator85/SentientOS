from __future__ import annotations

from sentientos.work_item_promotion_gate import WorkItemPromotionPolicy, WorkItemPromotionRequest, evaluate_work_item_promotion


def _packet(**overrides):
    base = {
        "review_packet_id": "wir_1",
        "digest": "abc",
        "source_work_item_id": "w1",
        "operator_action": "ready_for_workspace_admission_review",
        "dry_run_closure_status": "dry_run_closed_clean",
        "lifecycle_dry_run_invoked": True,
        "lifecycle_mode_used": "dry_run_full_lifecycle",
        "artifact_records": [{"stage": "review", "digest": "1"}],
        "contradiction_source": "none",
    }
    base.update(overrides)
    return base


def test_clean_packet_ready() -> None:
    result = evaluate_work_item_promotion(WorkItemPromotionRequest(review_packet=_packet()))
    assert result.decision.status == "promotion_ready_for_admission_review"


def test_warning_policy_toggle() -> None:
    req = WorkItemPromotionRequest(review_packet=_packet(dry_run_closure_status="dry_run_closed_with_warnings"))
    assert evaluate_work_item_promotion(req).decision.status == "promotion_ready_with_warnings"
    assert evaluate_work_item_promotion(req, policy=WorkItemPromotionPolicy(allow_warning_promotion=False)).decision.status == "promotion_blocked_authority"


def test_manual_and_clarification() -> None:
    assert evaluate_work_item_promotion(WorkItemPromotionRequest(review_packet=_packet(operator_action="manual_review_required"))).decision.status == "promotion_requires_manual_review"
    assert evaluate_work_item_promotion(WorkItemPromotionRequest(review_packet=_packet(operator_action="request_clarification"))).decision.status == "promotion_requires_clarification"


def test_contradiction_and_authority_blocks() -> None:
    assert evaluate_work_item_promotion(WorkItemPromotionRequest(review_packet=_packet(contradiction_source="closure", contradiction_codes=["x"]))).decision.status == "promotion_contradicted"
    assert evaluate_work_item_promotion(WorkItemPromotionRequest(review_packet=_packet(network_requested=True))).decision.status == "promotion_blocked_authority"


def test_matrix_required() -> None:
    req = WorkItemPromotionRequest(review_packet=_packet())
    assert evaluate_work_item_promotion(req, policy=WorkItemPromotionPolicy(matrix_required=True)).decision.status == "promotion_insufficient_evidence"
    assert evaluate_work_item_promotion(WorkItemPromotionRequest(review_packet=_packet(), matrix_report={"status": "failed"})).decision.status == "promotion_blocked_authority"
