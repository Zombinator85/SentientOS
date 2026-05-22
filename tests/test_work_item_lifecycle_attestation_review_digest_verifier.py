from sentientos.work_item_lifecycle_attestation_review_digest_verifier import WorkItemLifecycleAttestationReviewDigestVerificationPolicy, WorkItemLifecycleAttestationReviewDigestVerificationRequest, evaluate_work_item_lifecycle_attestation_review_digest_verification


def _digest(*, status: str = "lifecycle_attestation_review_digest_clear", posture: str = "reviewer_can_accept_index") -> dict[str, object]:
    return {"digest": {"review_digest_id": "d1", "review_digest_digest": "dd1", "attestation_index_id": "i1", "attestation_index_digest": "id1", "index_verification_report_id": "r1", "index_verification_report_digest": "rd1", "digest_status": status, "reviewer_posture": posture, "work_item_count": 1, "sealed_count": 1, "attention_required_count": 0, "blocked_count": 0, "contradicted_count": 0, "warning_codes": [], "entries": [{"entry_id": "e1", "work_item_id": "w1", "attention_required": False, "blocker_codes": [], "contradiction_codes": []}]}}


def _index(status: str = "lifecycle_attestation_index_ready") -> dict[str, object]:
    return {"index": {"attestation_index_id": "i1", "attestation_index_digest": "id1", "index_status": status, "indexed_count": 1, "entries": [{"entry_id": "e1", "work_item_id": "w1", "attestation_status": "lifecycle_final_attestation_sealed"}]}}


def _report(status: str = "lifecycle_attestation_index_verification_passed", warnings: list[str] | None = None) -> dict[str, object]:
    return {"report": {"index_verification_report_id": "r1", "index_verification_report_digest": "rd1", "verification_status": status, "warning_codes": warnings or [], "blocker_codes": [], "contradiction_codes": []}}


def test_passed() -> None:
    out = evaluate_work_item_lifecycle_attestation_review_digest_verification(WorkItemLifecycleAttestationReviewDigestVerificationRequest(review_digest=_digest(), attestation_index=_index(), index_verification_report=_report()))
    assert out.status == "lifecycle_attestation_review_digest_verification_passed"


def test_passed_with_warnings_policy() -> None:
    out = evaluate_work_item_lifecycle_attestation_review_digest_verification(WorkItemLifecycleAttestationReviewDigestVerificationRequest(review_digest=_digest(status="lifecycle_attestation_review_digest_clear_with_warnings", posture="reviewer_can_accept_with_warnings"), attestation_index=_index("lifecycle_attestation_index_ready_with_warnings"), index_verification_report=_report("lifecycle_attestation_index_verification_passed_with_warnings", ["w"])), policy=WorkItemLifecycleAttestationReviewDigestVerificationPolicy(allow_warnings=True))
    assert out.status == "lifecycle_attestation_review_digest_verification_passed_with_warnings"


def test_contradiction_on_mismatch() -> None:
    d = _digest()
    d["digest"]["attestation_index_id"] = "other"  # type: ignore[index]
    out = evaluate_work_item_lifecycle_attestation_review_digest_verification(WorkItemLifecycleAttestationReviewDigestVerificationRequest(review_digest=d, attestation_index=_index(), index_verification_report=_report()))
    assert out.status == "lifecycle_attestation_review_digest_verification_contradicted"


def test_matrix_required_blocks() -> None:
    out = evaluate_work_item_lifecycle_attestation_review_digest_verification(WorkItemLifecycleAttestationReviewDigestVerificationRequest(review_digest=_digest(), attestation_index=_index(), index_verification_report=_report(), matrix_report={"status": "failed"}), policy=WorkItemLifecycleAttestationReviewDigestVerificationPolicy(matrix_required=True))
    assert out.status == "lifecycle_attestation_review_digest_verification_blocked"
