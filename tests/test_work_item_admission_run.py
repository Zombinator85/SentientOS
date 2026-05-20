from sentientos.work_item_admission_run import OperatorConfirmedAdmissionPolicy, OperatorConfirmedAdmissionRequest, evaluate_operator_confirmed_admission


def _review(status: str = 'admission_review_ready'):
    return {"status": status, "packet": {"admission_review_packet_id": "r1", "admission_review_packet_digest": "d1", "work_item_id": "w1", "required_operator_acknowledgements": ["ok"]}}


def _proposal():
    return {"declared_target_count": 1, "proposed_targets": [{"target_id": "a", "relative_target_path": "docs/a.txt", "operation": "create_file", "declared_payload_byte_count": 1, "declared_payload_digest": "sha256:a"}]}


def test_ready_invokes_and_accepts():
    r = evaluate_operator_confirmed_admission(OperatorConfirmedAdmissionRequest(operator_review_packet=_review(), proposal=_proposal()))
    assert r.decision.admission_controller_invoked is True
    assert r.status in {"admission_run_accepted", "admission_run_accepted_with_warnings"}


def test_warning_review_policy_blocks_by_default():
    r = evaluate_operator_confirmed_admission(OperatorConfirmedAdmissionRequest(operator_review_packet=_review('admission_review_ready_with_warnings'), proposal=_proposal()))
    assert r.status == 'admission_run_blocked_by_policy'


def test_warning_review_allowed():
    r = evaluate_operator_confirmed_admission(OperatorConfirmedAdmissionRequest(operator_review_packet=_review('admission_review_ready_with_warnings'), proposal=_proposal()), policy=OperatorConfirmedAdmissionPolicy(allow_warning_review=True))
    assert r.decision.admission_controller_invoked is True


def test_manual_review_blocks():
    r = evaluate_operator_confirmed_admission(OperatorConfirmedAdmissionRequest(operator_review_packet=_review('admission_review_manual_review_required'), proposal=_proposal()))
    assert r.status == 'admission_run_blocked_by_operator_review'


def test_missing_proposal_insufficient():
    r = evaluate_operator_confirmed_admission(OperatorConfirmedAdmissionRequest(operator_review_packet=_review(), proposal=None))
    assert r.status == 'admission_run_insufficient_evidence'


def test_matrix_required_blocks_when_not_passed():
    r = evaluate_operator_confirmed_admission(OperatorConfirmedAdmissionRequest(operator_review_packet=_review(), proposal=_proposal(), matrix_report={"status": "failed"}), policy=OperatorConfirmedAdmissionPolicy(matrix_required=True))
    assert r.status == 'admission_run_blocked_by_policy'


def test_dry_run_review_only_no_invocation():
    r = evaluate_operator_confirmed_admission(OperatorConfirmedAdmissionRequest(operator_review_packet=_review(), proposal=_proposal()), policy=OperatorConfirmedAdmissionPolicy(dry_run_review_only=True))
    assert r.decision.admission_controller_invoked is False
