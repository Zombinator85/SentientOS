from sentientos.work_item_lifecycle_attestation_index_verifier import WorkItemLifecycleAttestationIndexVerificationPolicy, WorkItemLifecycleAttestationIndexVerificationRequest, evaluate_work_item_lifecycle_attestation_index_verification


def _index(status: str = "lifecycle_attestation_index_ready") -> dict[str, object]:
    return {"index": {"attestation_index_id": "idx1", "attestation_index_digest": "dig1", "index_status": status, "indexed_count": 1, "duplicate_count": 0, "duplicate_keys": [], "skipped_count": 0, "skipped_inputs": [], "entries": [{"entry_id": "e1", "sort_key": "a", "final_attestation_bundle_id": "b1", "final_attestation_bundle_digest": "bd1", "work_item_id": "w1", "attestation_status": "lifecycle_final_attestation_sealed", "warning_codes": [], "blocker_codes": [], "contradiction_codes": [], "attention_required": False}]}}


def _bundle() -> dict[str, object]:
    return {"bundle": {"final_attestation_bundle_id": "b1", "final_attestation_bundle_digest": "bd1", "work_item_id": "w1"}}


def test_ready_passes() -> None:
    r = evaluate_work_item_lifecycle_attestation_index_verification(WorkItemLifecycleAttestationIndexVerificationRequest(attestation_index=_index()))
    assert r.status == "lifecycle_attestation_index_verification_passed"


def test_warning_index_policy() -> None:
    denied = evaluate_work_item_lifecycle_attestation_index_verification(WorkItemLifecycleAttestationIndexVerificationRequest(attestation_index=_index("lifecycle_attestation_index_ready_with_warnings")))
    assert denied.status == "lifecycle_attestation_index_verification_blocked"
    allowed = evaluate_work_item_lifecycle_attestation_index_verification(WorkItemLifecycleAttestationIndexVerificationRequest(attestation_index=_index("lifecycle_attestation_index_ready_with_warnings")), policy=WorkItemLifecycleAttestationIndexVerificationPolicy(allow_warning_index=True))
    assert allowed.status == "lifecycle_attestation_index_verification_passed_with_warnings"


def test_source_bundle_required() -> None:
    r = evaluate_work_item_lifecycle_attestation_index_verification(WorkItemLifecycleAttestationIndexVerificationRequest(attestation_index=_index()), policy=WorkItemLifecycleAttestationIndexVerificationPolicy(source_bundles_required=True))
    assert r.status == "lifecycle_attestation_index_verification_insufficient_evidence"


def test_bundle_mismatch_contradiction() -> None:
    b = _bundle(); b["bundle"]["final_attestation_bundle_digest"] = "x"  # type: ignore[index]
    r = evaluate_work_item_lifecycle_attestation_index_verification(WorkItemLifecycleAttestationIndexVerificationRequest(attestation_index=_index(), attestation_bundles=(("b.json", b),)))
    assert r.status == "lifecycle_attestation_index_verification_contradicted"
