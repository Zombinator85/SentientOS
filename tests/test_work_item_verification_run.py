from sentientos.work_item_verification_run import OperatorConfirmedVerificationPolicy, OperatorConfirmedVerificationRequest, evaluate_operator_confirmed_verification


def _execution(status: str = "execution_run_completed", invoked: bool = True):
    return {"status": status, "packet": {"execution_run_packet_id": "id", "execution_run_packet_digest": "d", "work_item_id": "w1", "execution_wing_invoked": invoked, "workspace_change_set_execution_status": "workspace_change_set_execution_performed", "artifact_references": ["a"]}}


def _proposal():
    return {"work_item_id": "w1", "proposal_id": "p1", "proposed_targets": [{"operation": "write", "relative_target_path": "x.txt"}], "declared_target_count": 1}


def test_missing_confirmation_blocks() -> None:
    r = evaluate_operator_confirmed_verification(OperatorConfirmedVerificationRequest(execution_run_packet=_execution(), proposal=_proposal(), workspace_root="/tmp/x", operator_confirmation=False))
    assert r.status == "verification_run_blocked_by_policy"
    assert r.packet.verification_wing_invoked is False


def test_review_only_allows_non_invoking_packet() -> None:
    r = evaluate_operator_confirmed_verification(OperatorConfirmedVerificationRequest(execution_run_packet=_execution(), proposal=_proposal(), workspace_root="/tmp/x", operator_confirmation=False), policy=OperatorConfirmedVerificationPolicy(review_only=True))
    assert r.status == "verification_run_passed"
    assert r.packet.verification_wing_invoked is False


def test_warning_execution_policy() -> None:
    req = OperatorConfirmedVerificationRequest(execution_run_packet=_execution("execution_run_completed_with_warnings"), proposal=_proposal(), workspace_root="/tmp/x", operator_confirmation=True)
    blocked = evaluate_operator_confirmed_verification(req)
    assert blocked.status == "verification_run_blocked_by_execution"
    allowed = evaluate_operator_confirmed_verification(req, policy=OperatorConfirmedVerificationPolicy(allow_warning_execution=True))
    assert allowed.packet.verification_wing_invoked is True


def test_missing_evidence_and_mismatch() -> None:
    r1 = evaluate_operator_confirmed_verification(OperatorConfirmedVerificationRequest(execution_run_packet=_execution(), proposal=None, workspace_root="/tmp/x", operator_confirmation=True))
    assert r1.status == "verification_run_insufficient_evidence"
    r2 = evaluate_operator_confirmed_verification(OperatorConfirmedVerificationRequest(execution_run_packet=_execution(), proposal={"work_item_id": "w2"}, workspace_root="/tmp/x", operator_confirmation=True))
    assert r2.status == "verification_run_contradicted"


def test_matrix_and_artifact_requirements() -> None:
    req = OperatorConfirmedVerificationRequest(execution_run_packet=_execution(), proposal=_proposal(), workspace_root="/tmp/x", operator_confirmation=True, matrix_report={"status": "failed"})
    r = evaluate_operator_confirmed_verification(req, policy=OperatorConfirmedVerificationPolicy(matrix_required=True))
    assert r.status == "verification_run_blocked_by_policy"
    req2 = OperatorConfirmedVerificationRequest(execution_run_packet={"status": "execution_run_completed", "packet": {"work_item_id": "w1", "execution_wing_invoked": True}}, proposal=_proposal(), workspace_root="/tmp/x", operator_confirmation=True)
    r2 = evaluate_operator_confirmed_verification(req2, policy=OperatorConfirmedVerificationPolicy(artifacts_required=True))
    assert r2.status == "verification_run_insufficient_evidence"
