from sentientos.work_item_lifecycle_closure_run import OperatorConfirmedLifecycleClosurePolicy, OperatorConfirmedLifecycleClosureRequest, evaluate_operator_confirmed_lifecycle_closure


def _closure_review(status: str = "closure_review_ready"):
    return {"status": status, "packet": {"closure_review_packet_id": "c1", "closure_review_packet_digest": "d1", "work_item_id": "w1", "artifact_references": ["a"]}}


def _proposal() -> dict:
    return {
        "work_item_id": "w1", "proposal_id": "p1", "manifest": {"manifest_id": "m1", "manifest_digest": "md", "declared_target_count": 0, "targets": []},
        "preflight_report": {"report_id": "r1", "manifest_id": "m1", "manifest_digest": "md", "status": "preflight_clear", "target_results": [], "warning_codes": [], "blocker_codes": [], "created_at": "1970-01-01T00:00:00+00:00", "digest": "d"},
        "rollback_plan": {"rollback_plan_id": "rb1", "manifest_id": "m1", "rollback_steps": [], "blocked_actions": [], "status": "rollback_plan_ready", "created_at": "1970-01-01T00:00:00+00:00", "digest": "d"},
        "transaction_plan": {"transaction_plan_id": "tp1", "manifest_id": "m1", "status": "transaction_plan_ready", "steps": [], "created_at": "1970-01-01T00:00:00+00:00", "digest": "d"},
        "execution_request": {"request_id": "e1", "manifest_id": "m1", "transaction_plan_id": "tp1", "rollback_plan_id": "rb1", "status": "execution_requested", "created_at": "1970-01-01T00:00:00+00:00", "digest": "d"},
        "execution_result": {"result_id": "er1", "request_id": "e1", "status": "execution_completed", "target_results": [], "created_at": "1970-01-01T00:00:00+00:00", "digest": "d"},
        "execution_receipt": {"receipt_id": "rec1", "result_id": "er1", "status": "execution_receipt_recorded", "created_at": "1970-01-01T00:00:00+00:00", "digest": "d"},
        "verification_result": {"verification_id": "v1", "status": "verified_clean", "created_at": "1970-01-01T00:00:00+00:00", "digest": "d"},
    }


def test_policy_blocks_and_review_only() -> None:
    r = evaluate_operator_confirmed_lifecycle_closure(OperatorConfirmedLifecycleClosureRequest(closure_review_packet=_closure_review(), proposal=_proposal(), operator_confirmation=False))
    assert r.status == "lifecycle_closure_run_blocked_by_policy"
    rr = evaluate_operator_confirmed_lifecycle_closure(OperatorConfirmedLifecycleClosureRequest(closure_review_packet=_closure_review(), proposal=_proposal(), operator_confirmation=False), policy=OperatorConfirmedLifecycleClosurePolicy(review_only=True))
    assert rr.status == "lifecycle_closure_run_completed"
    assert rr.packet.lifecycle_closure_wing_invoked is False


def test_matrix_and_artifact_and_contradiction_checks() -> None:
    assert evaluate_operator_confirmed_lifecycle_closure(OperatorConfirmedLifecycleClosureRequest(closure_review_packet=_closure_review(), proposal=None, operator_confirmation=True)).status == "lifecycle_closure_run_insufficient_evidence"
    bad = evaluate_operator_confirmed_lifecycle_closure(OperatorConfirmedLifecycleClosureRequest(closure_review_packet=_closure_review(), proposal={"work_item_id": "w2"}, operator_confirmation=True))
    assert bad.status == "lifecycle_closure_run_contradicted"
    m = evaluate_operator_confirmed_lifecycle_closure(OperatorConfirmedLifecycleClosureRequest(closure_review_packet=_closure_review(), proposal=_proposal(), operator_confirmation=True, matrix_report={"status": "failed"}), policy=OperatorConfirmedLifecycleClosurePolicy(matrix_required=True))
    assert m.status == "lifecycle_closure_run_blocked_by_policy"


def test_can_invoke_closure_wing() -> None:
    ok = evaluate_operator_confirmed_lifecycle_closure(OperatorConfirmedLifecycleClosureRequest(closure_review_packet=_closure_review(), proposal=_proposal(), operator_confirmation=True), policy=OperatorConfirmedLifecycleClosurePolicy(allow_warning_review=True))
    assert ok.packet.lifecycle_closure_wing_invoked is True
    assert ok.status in {"lifecycle_closure_run_completed", "lifecycle_closure_run_completed_with_warnings", "lifecycle_closure_run_insufficient_evidence"}
