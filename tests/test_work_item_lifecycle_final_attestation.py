from sentientos.work_item_lifecycle_final_attestation import WorkItemLifecycleFinalAttestationPolicy, WorkItemLifecycleFinalAttestationRequest, evaluate_work_item_lifecycle_final_attestation


def _dossier(status: str = "lifecycle_completion_dossier_complete") -> dict[str, object]:
    return {"completion_dossier_id": "d1", "completion_dossier_digest": "cdg", "work_item_id": "w1", "status": status, "completed_stage_order": ["intake"], "stage_count": 1, "evidence_artifact_references": ["a"], "evidence_artifact_digests": ["ad"], "blocker_codes": [], "warning_codes": [], "contradiction_codes": []}


def _report(status: str = "lifecycle_completion_verification_passed") -> dict[str, object]:
    return {"verification_report_id": "r1", "verification_report_digest": "rdg", "work_item_id": "w1", "verification_status": status, "blocker_codes": [], "warning_codes": [], "contradiction_codes": []}


def test_sealed() -> None:
    r = evaluate_work_item_lifecycle_final_attestation(WorkItemLifecycleFinalAttestationRequest(completion_dossier=_dossier(), verification_report=_report()))
    assert r.status == "lifecycle_final_attestation_sealed"
    assert r.bundle.final_attestation_statement


def test_warnings_policy() -> None:
    r = evaluate_work_item_lifecycle_final_attestation(WorkItemLifecycleFinalAttestationRequest(completion_dossier=_dossier("lifecycle_completion_dossier_complete_with_warnings"), verification_report=_report("lifecycle_completion_verification_passed_with_warnings")), policy=WorkItemLifecycleFinalAttestationPolicy(allow_warnings=True))
    assert r.status == "lifecycle_final_attestation_sealed_with_warnings"


def test_required_alignment_and_artifacts() -> None:
    d = _dossier(); d["work_item_id"] = "w2"; d["evidence_artifact_references"] = []
    r = evaluate_work_item_lifecycle_final_attestation(WorkItemLifecycleFinalAttestationRequest(completion_dossier=d, verification_report=_report()), policy=WorkItemLifecycleFinalAttestationPolicy(artifact_refs_required=True))
    assert r.status in {"lifecycle_final_attestation_contradicted", "lifecycle_final_attestation_insufficient_evidence", "lifecycle_final_attestation_blocked"}
    assert "work_item_id_mismatch" in r.bundle.contradiction_codes


def test_matrix_and_proof_requirements() -> None:
    r = evaluate_work_item_lifecycle_final_attestation(WorkItemLifecycleFinalAttestationRequest(completion_dossier=_dossier(), verification_report=_report(), matrix_report={"status": "failed"}), policy=WorkItemLifecycleFinalAttestationPolicy(matrix_required=True))
    assert r.status != "lifecycle_final_attestation_sealed"
