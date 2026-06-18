from sentientos.work_item_lifecycle_attestation_review_digest_index_verifier import (
    WorkItemLifecycleAttestationReviewDigestIndexVerificationPolicy,
    WorkItemLifecycleAttestationReviewDigestIndexVerificationRequest,
    evaluate_work_item_lifecycle_attestation_review_digest_index_verification,
)


def _index(status: str = "lifecycle_attestation_review_digest_index_ready") -> dict[str, object]:
    return {
        "index": {
            "review_digest_index_id": "i1",
            "review_digest_index_digest": "d1",
            "index_status": status,
            "indexed_count": 1,
            "duplicate_count": 0,
            "duplicate_keys": [],
            "skipped_count": 0,
            "skipped_inputs": [],
            "aggregate_reviewer_posture": "reviewer_can_accept_all",
            "entries": [
                {
                    "entry_id": "e1",
                    "sort_key": "a|b",
                    "review_digest_id": "a",
                    "review_digest_digest": "b",
                    "digest_status": "lifecycle_attestation_review_digest_clear",
                    "attention_required": False,
                    "attention_required_count": 0,
                    "warning_codes": [],
                    "blocker_codes": [],
                    "contradiction_codes": [],
                }
            ],
        }
    }


def test_ready_index_passes() -> None:
    r = evaluate_work_item_lifecycle_attestation_review_digest_index_verification(WorkItemLifecycleAttestationReviewDigestIndexVerificationRequest(review_digest_index=_index()))
    assert r.status == "lifecycle_attestation_review_digest_index_verification_passed"


def test_warning_index_policy() -> None:
    req = WorkItemLifecycleAttestationReviewDigestIndexVerificationRequest(review_digest_index=_index("lifecycle_attestation_review_digest_index_ready_with_warnings"))
    blocked = evaluate_work_item_lifecycle_attestation_review_digest_index_verification(req)
    assert blocked.status.endswith("blocked")
    ok = evaluate_work_item_lifecycle_attestation_review_digest_index_verification(req, policy=WorkItemLifecycleAttestationReviewDigestIndexVerificationPolicy(allow_warning_index=True))
    assert ok.status == "lifecycle_attestation_review_digest_index_verification_passed_with_warnings"


def test_digest_alignment_and_matrix_requirement() -> None:
    req = WorkItemLifecycleAttestationReviewDigestIndexVerificationRequest(
        review_digest_index=_index(),
        review_digests=(("x", {"digest": {"review_digest_id": "a", "review_digest_digest": "b"}}),),
        matrix_report={"status": "failed"},
    )
    r = evaluate_work_item_lifecycle_attestation_review_digest_index_verification(req, policy=WorkItemLifecycleAttestationReviewDigestIndexVerificationPolicy(matrix_required=True))
    assert r.status == "lifecycle_attestation_review_digest_index_verification_blocked"


def test_contradiction_for_indexed_count_mismatch() -> None:
    bad = _index()
    bad["index"]["indexed_count"] = 9  # type: ignore[index]
    r = evaluate_work_item_lifecycle_attestation_review_digest_index_verification(WorkItemLifecycleAttestationReviewDigestIndexVerificationRequest(review_digest_index=bad))
    assert r.status == "lifecycle_attestation_review_digest_index_verification_contradicted"


def test_review_digest_index_verifier_matrix_lane_is_registered() -> None:
    from scripts.run_work_item_review_packet_matrix import default_matrix_commands

    commands = {command.label: command for command in default_matrix_commands()}
    lane = commands["work_item_lifecycle_attestation_review_digest_index_verifier_tests"]
    assert lane.required is True
    assert lane.command == (
        "python",
        "-m",
        "scripts.run_tests",
        "-q",
        "tests/test_work_item_lifecycle_attestation_review_digest_index_verifier.py",
        "tests/test_verify_work_item_lifecycle_attestation_review_digest_index_script.py",
    )
