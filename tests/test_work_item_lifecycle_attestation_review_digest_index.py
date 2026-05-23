from sentientos.work_item_lifecycle_attestation_review_digest_index import WorkItemLifecycleAttestationReviewDigestIndexPolicy, WorkItemLifecycleAttestationReviewDigestIndexRequest, build_work_item_lifecycle_attestation_review_digest_index


def _digest(did: str, ddg: str, status: str = "lifecycle_attestation_review_digest_clear"):
    return {"digest": {"review_digest_id": did, "review_digest_digest": ddg, "digest_status": status, "reviewer_posture": "reviewer_can_accept_index", "work_item_count": 1, "attention_required_count": 0, "blocked_count": 0, "contradicted_count": 0, "insufficient_count": 0, "blocker_codes": [], "warning_codes": [], "contradiction_codes": [], "unresolved_risks": []}}


def test_ready_single_clear():
    r = build_work_item_lifecycle_attestation_review_digest_index(WorkItemLifecycleAttestationReviewDigestIndexRequest(review_digests=(_digest("a", "d"),)), policy=WorkItemLifecycleAttestationReviewDigestIndexPolicy(require_clear=False))
    assert r.status == "lifecycle_attestation_review_digest_index_ready"


def test_duplicate_detected():
    r = build_work_item_lifecycle_attestation_review_digest_index(WorkItemLifecycleAttestationReviewDigestIndexRequest(review_digests=(_digest("a", "d"), _digest("a", "d"))))
    assert r.status == "lifecycle_attestation_review_digest_index_contradicted"


def test_require_verifier_reports_missing_insufficient():
    r = build_work_item_lifecycle_attestation_review_digest_index(WorkItemLifecycleAttestationReviewDigestIndexRequest(review_digests=(_digest("a", "d"),)), policy=WorkItemLifecycleAttestationReviewDigestIndexPolicy(require_clear=False, require_verifier_reports=True))
    assert r.status == "lifecycle_attestation_review_digest_index_blocked"


def test_matrix_required_blocks():
    r = build_work_item_lifecycle_attestation_review_digest_index(WorkItemLifecycleAttestationReviewDigestIndexRequest(review_digests=(_digest("a", "d"),), matrix_report={"status": "failed"}), policy=WorkItemLifecycleAttestationReviewDigestIndexPolicy(require_clear=False, matrix_required=True))
    assert r.status == "lifecycle_attestation_review_digest_index_blocked"
