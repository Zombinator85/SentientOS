from sentientos.work_item_preflight_run import OperatorConfirmedPreflightPolicy, OperatorConfirmedPreflightRequest, evaluate_operator_confirmed_preflight


def _admission(status: str = 'admission_run_accepted', invoked: bool = True, ws: str = 'admission_accepted'):
    return {"status": status, "packet": {"admission_run_packet_id":"a1","admission_run_packet_digest":"d1","work_item_id":"w1","admission_controller_invoked":invoked,"workspace_change_set_admission_status":ws,"operator_acknowledgements":["ok"]}}


def _proposal(wid: str = 'w1'):
    return {"work_item_id": wid, "declared_target_count":1, "proposed_targets":[{"target_id":"a","relative_target_path":"docs/a.txt","operation":"create_file","declared_payload_digest":"sha256:a"}]}


def test_ready_invokes_preflight(tmp_path):
    r = evaluate_operator_confirmed_preflight(OperatorConfirmedPreflightRequest(admission_run_packet=_admission(), proposal=_proposal(), workspace_root=str(tmp_path)))
    assert r.decision.preflight_controller_invoked is True
    assert r.status in {'preflight_run_ready', 'preflight_run_ready_with_warnings', 'preflight_run_blocked_by_preflight'}


def test_warning_admission_policy():
    r = evaluate_operator_confirmed_preflight(OperatorConfirmedPreflightRequest(admission_run_packet=_admission('admission_run_accepted_with_warnings'), proposal=_proposal(), workspace_root='.'))
    assert r.status == 'preflight_run_blocked_by_admission'


def test_missing_inputs_insufficient():
    r = evaluate_operator_confirmed_preflight(OperatorConfirmedPreflightRequest(admission_run_packet=_admission(), proposal=None, workspace_root='.'))
    assert r.status == 'preflight_run_insufficient_evidence'


def test_work_item_mismatch_contradicted():
    r = evaluate_operator_confirmed_preflight(OperatorConfirmedPreflightRequest(admission_run_packet=_admission(), proposal=_proposal('w2'), workspace_root='.'))
    assert r.status == 'preflight_run_contradicted'


def test_matrix_required_blocks():
    r = evaluate_operator_confirmed_preflight(OperatorConfirmedPreflightRequest(admission_run_packet=_admission(), proposal=_proposal(), workspace_root='.', matrix_report={'status':'failed'}), policy=OperatorConfirmedPreflightPolicy(matrix_required=True))
    assert r.status == 'preflight_run_blocked_by_policy'


def test_review_only_no_invoke():
    r = evaluate_operator_confirmed_preflight(OperatorConfirmedPreflightRequest(admission_run_packet=_admission(invoked=False), proposal=_proposal(), workspace_root='.'), policy=OperatorConfirmedPreflightPolicy(review_only=True))
    assert r.decision.preflight_controller_invoked is False
