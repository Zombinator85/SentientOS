from sentientos.work_item_lifecycle_completion_dossier import WorkItemLifecycleCompletionPolicy, WorkItemLifecycleCompletionRequest, evaluate_work_item_lifecycle_completion_dossier


def _closure(status="lifecycle_closure_run_completed"):
    return {"status": status, "packet": {"work_item_id": "w1", "lifecycle_closure_run_packet_id": "c1", "lifecycle_closure_run_packet_digest": "d1", "lifecycle_closure_wing_invoked": True, "artifact_references": ["a"]}}


def _proposal():
    return {"work_item_id": "w1", "proposal_id": "p1", "proposal_digest": "pd"}


def test_complete():
    r = evaluate_work_item_lifecycle_completion_dossier(WorkItemLifecycleCompletionRequest(lifecycle_closure_run_packet=_closure(), proposal=_proposal()))
    assert r.status == "lifecycle_completion_dossier_complete"
    assert r.dossier.final_completion_statement


def test_warning_policy():
    r = evaluate_work_item_lifecycle_completion_dossier(WorkItemLifecycleCompletionRequest(lifecycle_closure_run_packet=_closure("lifecycle_closure_run_completed_with_warnings"), proposal=_proposal()), policy=WorkItemLifecycleCompletionPolicy(allow_warning_closure=True))
    assert r.status == "lifecycle_completion_dossier_complete_with_warnings"


def test_matrix_required_blocks():
    r = evaluate_work_item_lifecycle_completion_dossier(WorkItemLifecycleCompletionRequest(lifecycle_closure_run_packet=_closure(), proposal=_proposal()), policy=WorkItemLifecycleCompletionPolicy(matrix_required=True))
    assert r.status == "lifecycle_completion_dossier_blocked_by_closure"
