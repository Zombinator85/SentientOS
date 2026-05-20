from sentientos.work_item_execution_review import OperatorExecutionReviewPolicy, OperatorExecutionReviewRequest, evaluate_operator_execution_review


def _preflight(status: str = "preflight_run_ready", tx: bool = True, invoked: bool = True):
    return {"status": status, "packet": {"preflight_run_packet_id": "p1", "preflight_run_packet_digest": "d1", "work_item_id": "w1", "preflight_controller_invoked": invoked, "transaction_plan_ready": tx, "preflight_warning_codes": ["warn"] if status.endswith("warnings") else [], "artifact_references": ["a"]}}


def _proposal(wid: str = "w1"):
    return {"work_item_id": wid, "proposal_id": "prop1", "proposed_targets": [{"operation": "create_file", "relative_target_path": "docs/a.md"}]}


def test_ready_status():
    r = evaluate_operator_execution_review(OperatorExecutionReviewRequest(preflight_run_packet=_preflight(), proposal=_proposal()))
    assert r.status == "execution_review_ready"
    assert r.packet.candidate_manual_execution_command is not None


def test_warning_policy_and_manual_review():
    blocked = evaluate_operator_execution_review(OperatorExecutionReviewRequest(preflight_run_packet=_preflight("preflight_run_ready_with_warnings"), proposal=_proposal()))
    assert blocked.status == "execution_review_manual_review_required"
    allowed = evaluate_operator_execution_review(OperatorExecutionReviewRequest(preflight_run_packet=_preflight("preflight_run_ready_with_warnings"), proposal=_proposal()), policy=OperatorExecutionReviewPolicy(allow_warning_preflight=True))
    assert allowed.status == "execution_review_ready_with_warnings"


def test_policy_and_evidence_failures():
    assert evaluate_operator_execution_review(OperatorExecutionReviewRequest(preflight_run_packet=_preflight(invoked=False), proposal=_proposal())).status == "execution_review_blocked_by_policy"
    assert evaluate_operator_execution_review(OperatorExecutionReviewRequest(preflight_run_packet=_preflight(tx=False), proposal=_proposal())).status == "execution_review_blocked_by_preflight"
    assert evaluate_operator_execution_review(OperatorExecutionReviewRequest(preflight_run_packet=_preflight(), proposal=None)).status == "execution_review_insufficient_evidence"
    assert evaluate_operator_execution_review(OperatorExecutionReviewRequest(preflight_run_packet=_preflight(), proposal=_proposal("w2"))).status == "execution_review_contradicted"


def test_matrix_and_artifacts_policy():
    req = OperatorExecutionReviewRequest(preflight_run_packet=_preflight(), proposal=_proposal(), matrix_report={"status": "failed"})
    assert evaluate_operator_execution_review(req, policy=OperatorExecutionReviewPolicy(matrix_required=True)).status == "execution_review_blocked_by_policy"
    req2 = OperatorExecutionReviewRequest(preflight_run_packet={"status": "preflight_run_ready", "packet": {"work_item_id": "w1", "preflight_controller_invoked": True, "transaction_plan_ready": True}}, proposal=_proposal())
    assert evaluate_operator_execution_review(req2, policy=OperatorExecutionReviewPolicy(artifacts_required=True)).status == "execution_review_insufficient_evidence"
