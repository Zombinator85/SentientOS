from sentientos.work_item_lifecycle_attestation_review_digest import WorkItemLifecycleAttestationReviewDigestPolicy, WorkItemLifecycleAttestationReviewDigestRequest, evaluate_work_item_lifecycle_attestation_review_digest


def _index(status: str = "lifecycle_attestation_index_ready", attention: bool = False) -> dict[str, object]:
    return {"index": {"attestation_index_id": "idx1", "attestation_index_digest": "didx", "index_status": status, "entries": [{"entry_id": "e1", "work_item_id": "w1", "attestation_status": "lifecycle_final_attestation_sealed", "attention_required": attention, "sort_key": "w1"}]}}


def _report(status: str = "lifecycle_attestation_index_verification_passed") -> dict[str, object]:
    return {"report": {"index_verification_report_id": "r1", "index_verification_report_digest": "dr1", "attestation_index_id": "idx1", "attestation_index_digest": "didx", "verification_status": status, "blocker_codes": [], "warning_codes": [], "contradiction_codes": []}}


def test_clear() -> None:
    r = evaluate_work_item_lifecycle_attestation_review_digest(WorkItemLifecycleAttestationReviewDigestRequest(attestation_index=_index(), index_verification_report=_report()))
    assert r.status == "lifecycle_attestation_review_digest_clear"


def test_warnings_policy() -> None:
    r = evaluate_work_item_lifecycle_attestation_review_digest(WorkItemLifecycleAttestationReviewDigestRequest(attestation_index=_index("lifecycle_attestation_index_ready_with_warnings"), index_verification_report=_report("lifecycle_attestation_index_verification_passed_with_warnings")), policy=WorkItemLifecycleAttestationReviewDigestPolicy(allow_warnings=True))
    assert r.status == "lifecycle_attestation_review_digest_clear_with_warnings"


def test_attention_required() -> None:
    r = evaluate_work_item_lifecycle_attestation_review_digest(WorkItemLifecycleAttestationReviewDigestRequest(attestation_index=_index(attention=True), index_verification_report=_report()))
    assert r.status == "lifecycle_attestation_review_digest_attention_required"


def test_require_no_attention_blocks() -> None:
    r = evaluate_work_item_lifecycle_attestation_review_digest(WorkItemLifecycleAttestationReviewDigestRequest(attestation_index=_index(attention=True), index_verification_report=_report()), policy=WorkItemLifecycleAttestationReviewDigestPolicy(require_no_attention_items=True))
    assert r.status == "lifecycle_attestation_review_digest_blocked"


def test_digest_mismatch_contradicted() -> None:
    rep = _report()
    rep["report"]["attestation_index_digest"] = "other"  # type: ignore[index]
    r = evaluate_work_item_lifecycle_attestation_review_digest(WorkItemLifecycleAttestationReviewDigestRequest(attestation_index=_index(), index_verification_report=rep))
    assert r.status == "lifecycle_attestation_review_digest_contradicted"


def test_matrix_required_failed_blocks() -> None:
    r = evaluate_work_item_lifecycle_attestation_review_digest(WorkItemLifecycleAttestationReviewDigestRequest(attestation_index=_index(), index_verification_report=_report(), matrix_report={"status": "failed"}), policy=WorkItemLifecycleAttestationReviewDigestPolicy(matrix_required=True))
    assert r.status == "lifecycle_attestation_review_digest_blocked"


def test_review_digest_matrix_lane_is_registered() -> None:
    from scripts.run_work_item_review_packet_matrix import default_matrix_commands

    commands = {command.label: command for command in default_matrix_commands()}
    lane = commands["work_item_lifecycle_attestation_review_digest_tests"]
    assert lane.required is True
    assert lane.command == (
        "python",
        "-m",
        "scripts.run_tests",
        "-q",
        "tests/test_work_item_lifecycle_attestation_review_digest.py",
        "tests/test_build_work_item_lifecycle_attestation_review_digest_script.py",
    )
