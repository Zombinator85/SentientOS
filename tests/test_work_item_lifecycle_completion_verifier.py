from sentientos.work_item_lifecycle_completion_verifier import WorkItemLifecycleCompletionVerificationPolicy, WorkItemLifecycleCompletionVerificationRequest, evaluate_work_item_lifecycle_completion_verification


def _dossier(status: str = "lifecycle_completion_dossier_complete") -> dict[str, object]:
    return {
        "status": status,
        "completion_dossier_id": "cd1",
        "completion_dossier_digest": "dg1",
        "work_item_id": "w1",
        "stage_summaries": [{"stage_id": "lifecycle_closure_run", "supplied": True, "status": "lifecycle_closure_run_completed", "packet_digest": "x1"}],
        "evidence_artifact_references": ["a"],
    }


def test_pass_and_statement() -> None:
    r = evaluate_work_item_lifecycle_completion_verification(WorkItemLifecycleCompletionVerificationRequest(completion_dossier=_dossier()))
    assert r.status == "lifecycle_completion_verification_passed"
    assert r.report.verified_completion_statement


def test_warning_policy() -> None:
    r = evaluate_work_item_lifecycle_completion_verification(WorkItemLifecycleCompletionVerificationRequest(completion_dossier=_dossier("lifecycle_completion_dossier_complete_with_warnings")), policy=WorkItemLifecycleCompletionVerificationPolicy(allow_warning_completion=True))
    assert r.status == "lifecycle_completion_verification_passed_with_warnings"


def test_full_chain_required() -> None:
    r = evaluate_work_item_lifecycle_completion_verification(WorkItemLifecycleCompletionVerificationRequest(completion_dossier=_dossier()), policy=WorkItemLifecycleCompletionVerificationPolicy(full_chain_required=True))
    assert r.status == "lifecycle_completion_verification_insufficient_evidence"


def test_alignment_contradiction() -> None:
    r = evaluate_work_item_lifecycle_completion_verification(WorkItemLifecycleCompletionVerificationRequest(completion_dossier=_dossier(), closure_run_packet={"status": "lifecycle_closure_run_completed", "packet": {"work_item_id": "w2", "packet_digest": "mismatch"}}))
    assert r.status == "lifecycle_completion_verification_contradicted"
    assert r.report.contradiction_codes
