from sentientos.work_item_lifecycle_closure_review import OperatorLifecycleClosureReviewPolicy, OperatorLifecycleClosureReviewRequest, evaluate_operator_lifecycle_closure_review


def _verification(status: str = "verification_run_passed", invoked: bool = True):
    return {"status": status, "packet": {"verification_run_packet_id": "v1", "verification_run_packet_digest": "d1", "work_item_id": "w1", "verification_controller_invoked": invoked, "artifact_references": ["a"], "verification_warning_codes": ["warn"] if status.endswith("warnings") else []}}


def _proposal(wid: str = "w1"):
    return {"work_item_id": wid, "proposal_id": "prop1", "proposed_targets": [{"operation": "update_file", "relative_target_path": "docs/a.md"}]}


def test_ready_status():
    r = evaluate_operator_lifecycle_closure_review(OperatorLifecycleClosureReviewRequest(verification_run_packet=_verification(), proposal=_proposal()))
    assert r.status == "closure_review_ready"
    assert r.packet.candidate_manual_closure_command is not None


def test_warning_policy_and_manual_review():
    blocked = evaluate_operator_lifecycle_closure_review(OperatorLifecycleClosureReviewRequest(verification_run_packet=_verification("verification_run_passed_with_warnings"), proposal=_proposal()))
    assert blocked.status == "closure_review_manual_review_required"
    allowed = evaluate_operator_lifecycle_closure_review(OperatorLifecycleClosureReviewRequest(verification_run_packet=_verification("verification_run_passed_with_warnings"), proposal=_proposal()), policy=OperatorLifecycleClosureReviewPolicy(allow_warning_verification=True))
    assert allowed.status == "closure_review_ready_with_warnings"


def test_blocked_and_contradicted_and_insufficient():
    assert evaluate_operator_lifecycle_closure_review(OperatorLifecycleClosureReviewRequest(verification_run_packet=_verification("verification_run_failed"), proposal=_proposal())).status == "closure_review_blocked_by_verification"
    assert evaluate_operator_lifecycle_closure_review(OperatorLifecycleClosureReviewRequest(verification_run_packet=_verification(invoked=False), proposal=_proposal())).status == "closure_review_blocked_by_policy"
    assert evaluate_operator_lifecycle_closure_review(OperatorLifecycleClosureReviewRequest(verification_run_packet=_verification(), proposal=None)).status == "closure_review_insufficient_evidence"
    assert evaluate_operator_lifecycle_closure_review(OperatorLifecycleClosureReviewRequest(verification_run_packet=_verification(), proposal=_proposal("w2"))).status == "closure_review_contradicted"


def test_matrix_artifacts_and_deterministic_checklist():
    req = OperatorLifecycleClosureReviewRequest(verification_run_packet=_verification(), proposal=_proposal(), matrix_report={"status": "failed"})
    assert evaluate_operator_lifecycle_closure_review(req, policy=OperatorLifecycleClosureReviewPolicy(matrix_required=True)).status == "closure_review_blocked_by_policy"
    req2 = OperatorLifecycleClosureReviewRequest(verification_run_packet={"status": "verification_run_passed", "packet": {"work_item_id": "w1", "verification_controller_invoked": True}}, proposal=_proposal())
    assert evaluate_operator_lifecycle_closure_review(req2, policy=OperatorLifecycleClosureReviewPolicy(artifacts_required=True)).status == "closure_review_insufficient_evidence"
    ids = [i.id for i in evaluate_operator_lifecycle_closure_review(OperatorLifecycleClosureReviewRequest(verification_run_packet=_verification(), proposal=_proposal())).packet.operator_checklist]
    assert ids[0] == "review_original_work_item_scope"
