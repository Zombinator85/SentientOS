from sentientos.work_item_execution_run import OperatorConfirmedExecutionPolicy, OperatorConfirmedExecutionRequest, evaluate_operator_confirmed_execution


def _review(status: str = "execution_review_ready"):
    return {"status": status, "packet": {"execution_review_packet_id": "id", "execution_review_packet_digest": "d", "work_item_id": "w1", "transaction_plan_ready": True, "artifact_references": ["a"]}}


def _proposal():
    return {"work_item_id": "w1", "proposal_id": "p1", "proposed_targets": [{"operation": "write", "relative_target_path": "x.txt"}], "declared_target_count": 1}


def test_missing_confirmation_blocks() -> None:
    r = evaluate_operator_confirmed_execution(OperatorConfirmedExecutionRequest(execution_review_packet=_review(), proposal=_proposal(), workspace_root="/tmp/x", operator_confirmation=False))
    assert r.status == "execution_run_blocked_by_policy"
    assert r.packet.execution_wing_invoked is False


def test_review_only_allows_non_invoking_packet() -> None:
    r = evaluate_operator_confirmed_execution(OperatorConfirmedExecutionRequest(execution_review_packet=_review(), proposal=_proposal(), workspace_root="/tmp/x", operator_confirmation=False), policy=OperatorConfirmedExecutionPolicy(review_only=True))
    assert r.status == "execution_run_completed"
    assert r.packet.execution_wing_invoked is False
