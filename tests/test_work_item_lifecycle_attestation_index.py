from sentientos.work_item_lifecycle_attestation_index import WorkItemLifecycleAttestationIndexPolicy, WorkItemLifecycleAttestationIndexRequest, evaluate_work_item_lifecycle_attestation_index


def _bundle(work_item_id: str = "w1", digest: str = "d1", status: str = "lifecycle_final_attestation_sealed") -> dict[str, object]:
    return {"bundle": {"final_attestation_bundle_id": f"b_{work_item_id}", "final_attestation_bundle_digest": digest, "work_item_id": work_item_id, "attestation_status": status, "warning_codes": [], "blocker_codes": [], "contradiction_codes": []}}


def test_ready() -> None:
    r = evaluate_work_item_lifecycle_attestation_index(WorkItemLifecycleAttestationIndexRequest(attestation_bundles=(("a.json", _bundle()),)))
    assert r.status == "lifecycle_attestation_index_ready"


def test_nonsealed_manual_review_when_required() -> None:
    r = evaluate_work_item_lifecycle_attestation_index(WorkItemLifecycleAttestationIndexRequest(attestation_bundles=(("a.json", _bundle(status="lifecycle_final_attestation_manual_review_required")),)), policy=WorkItemLifecycleAttestationIndexPolicy(require_sealed=True))
    assert r.status == "lifecycle_attestation_index_manual_review_required"


def test_duplicates_contradicted() -> None:
    r = evaluate_work_item_lifecycle_attestation_index(WorkItemLifecycleAttestationIndexRequest(attestation_bundles=(("a.json", _bundle("w1", "d1")), ("b.json", _bundle("w1", "d2")))))
    assert r.status == "lifecycle_attestation_index_contradicted"


def test_matrix_required() -> None:
    r = evaluate_work_item_lifecycle_attestation_index(WorkItemLifecycleAttestationIndexRequest(attestation_bundles=(("a.json", _bundle()),), matrix_report={"status": "failed"}), policy=WorkItemLifecycleAttestationIndexPolicy(matrix_required=True))
    assert r.status == "lifecycle_attestation_index_blocked"
