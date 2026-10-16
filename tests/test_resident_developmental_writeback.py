from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.governed_local_model_invocation import LocalModelInvocationBudget, LocalModelInvocationReceipt
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_writeback import (
    EFFECTS, PRINCIPAL, PURPOSE, CognitionObservation, DevelopmentalCandidate, DevelopmentalHistoryStore,
    DevelopmentalWritebackError, ResidentDevelopmentalWritebackController,
    SelectedEvidence, _has_bounded_integrity_controller_observation, _identity,
    measure_changed_cognition,
)
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from sentientos.world_state_board import WorldStateBoardBuilder

pytestmark = pytest.mark.no_legacy_skip


def snapshot():
    return WorldStateBoardBuilder().build([
        {"source_id":"source-a", "source_kind":"capability_registry", "subject_id":"subject-a", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":1}},
        {"source_id":"source-b", "source_kind":"audit_trust", "subject_id":"subject-b", "stage":"observation", "disposition":"contradicted", "observed_at":"2026-01-02T00:00:00+00:00", "payload":{"value":2}},
    ])


def controller(tmp_path: Path):
    ledger = AdmissionLedger(tmp_path / "authority" / "admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
    return ResidentDevelopmentalWritebackController(history_root=tmp_path / "developmental-history", admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger), current_sequence=lambda: 1), RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger)


class FakeInvoker:
    def __init__(self, output: object): self.output = output; self.request = None; self.persist = None
    def build_request(self, **kwargs):
        self.request = type("Request", (), {})()
        for key, value in kwargs.items(): setattr(self.request, key, value)
        self.request.model_id = "model-a"; self.request.model_artifact_digest = "artifact-a"
        semantic = {"purpose":kwargs["purpose"],"correlation_id":kwargs["correlation_id"],"upstream_evidence":kwargs["upstream_evidence"]}
        self.request.request_digest = digest_payload(semantic); self.request.request_id = "lmreq-" + self.request.request_digest[:24]
        self.request.to_receipt_request_dict = lambda: {**semantic,"request_id":self.request.request_id,"request_digest":self.request.request_digest,"model_id":"model-a","model_artifact_digest":"artifact-a"}
        return self.request
    def invoke(self, request, *, persist, include_output_in_receipt):
        self.persist = persist
        text = self.output if isinstance(self.output, str) else json.dumps(self.output)
        return LocalModelInvocationReceipt(request=request.to_receipt_request_dict(), status="admitted_completed", reason_codes=("completed",), output_text=text, output_digest=digest_payload({"output":text}), output_size_bytes=len(text), generation_config={}, admission_decision_ref="local-model-decision", purpose=PURPOSE, latency_ms=1, output_truncated=False, fallback_occurred=False, effects={"local_model_inference":True}, observed_at="2026-01-03T00:00:00+00:00")


def candidate_for(ctrl, snap=None, invoker=None):
    snap = snap or snapshot(); selection = ctrl.select_evidence(snap, fact_ids=[snap.facts[0].fact_id])
    fake = invoker or FakeInvoker({"interpretation":"A bounded historical pattern.","uncertainty":"medium","authority":True,"current_truth":True})
    # Extra model claims are intentionally rejected rather than promoted.
    if isinstance(fake.output, dict) and set(fake.output) != {"interpretation", "uncertainty"}:
        fake.output = {"interpretation":fake.output["interpretation"],"uncertainty":fake.output["uncertainty"]}
    return selection, ctrl.infer_candidate(selection, invoker=fake, correlation_id="corr-1"), fake


def issue(authority, candidate, *, operation_id="op-1", principal=PRINCIPAL, effects=EFFECTS, config=None, suffix="1", sequence=1):
    return authority.issue(admission_id=f"admission-{suffix}", capability_id=RESIDENT_DEVELOPMENTAL_WRITEBACK, definition_version=1, subsystem_kind="memory_context_reflection", principal_id=principal, principal_kind=PRINCIPAL, effects=effects, subject_id=candidate.candidate_id, request_configuration_digest=config or ResidentDevelopmentalWritebackController.admission_configuration_digest(candidate, operation_id=operation_id), provenance="operator-runtime-grant", issued_sequence=sequence, valid_through_sequence=4, affirmative_preconditions=RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION.approval_requirements)


def test_integrity_controller_v2_digest_is_bounded_before_cognition_qualification() -> None:
    def selection(*, schema: str, failed_digest: object) -> SelectedEvidence:
        fact = {
            "source": {"kind": "audit_trust", "source_id": "integrity-controller:resident-daemon"},
            "subject": {"subject_kind": "integrity_controller_observation"},
            "stage": "observation", "disposition": "degraded",
            "evidence_strength": "source_integrity_status",
            "payload": {
                "observation_schema": schema,
                "source_owner": "sentientos.integrity_controller.evaluate_integrity",
                "controller_posture": "fail", "gate_count": 1,
                "gate_results": [{"name": "snapshot-signature", "status": "fail",
                    "reason": "signature_invalid", "checked_at": "2026-10-12T00:00:00Z",
                    "failed_record_sha256": failed_digest}],
                "cause_unknown": True, "attack_established": False,
                "hostile_activity_established": False, "compromise_established": False,
                "effect_proven": False, "effect_authority": False,
                "authority": False, "current_truth": False, "read_only": True,
            },
        }
        return SelectedEvidence("snapshot", "sha256:snapshot", (fact,), (), ())

    assert _has_bounded_integrity_controller_observation(selection(
        schema="sentientos.integrity_controller_observation:v1", failed_digest=None))
    assert _has_bounded_integrity_controller_observation(selection(
        schema="sentientos.integrity_controller_observation:v2", failed_digest="a" * 64))
    assert not _has_bounded_integrity_controller_observation(selection(
        schema="sentientos.integrity_controller_observation:v2", failed_digest="A" * 64))
    assert not _has_bounded_integrity_controller_observation(selection(
        schema="sentientos.integrity_controller_observation:v2", failed_digest="short"))


def test_successful_selected_evidence_candidate_admitted_append_receipt_retrieval_and_restart(tmp_path: Path) -> None:
    ctrl, authority = controller(tmp_path); selection, candidate, fake = candidate_for(ctrl)
    admission = issue(authority, candidate)
    record, receipt = ctrl.append(candidate, admission=admission, operation_id="op-1", correlation_id="corr-1", created_at="2026-01-03T00:00:00+00:00")
    assert fake.request.purpose == PURPOSE and fake.persist is True
    assert fake.request.budget.max_calls_per_correlation == 1 and fake.request.budget.max_new_tokens <= 512
    assert record.candidate["selected_sources"] == list(selection.sources) or tuple(record.candidate["selected_sources"]) == selection.sources
    assert receipt.storage_verified and not receipt.grants_authority
    fresh, _ = controller(tmp_path)
    projection = fresh.retrieve([record.record_id])
    assert projection.read_only and projection.records[0]["record_digest"] == record.record_digest
    assert not projection.current_truth and not projection.authority and not projection.canonical_explicit_user_retention
    assert fresh.store.get_receipt(receipt.receipt_id) == receipt
    recovered = fresh.inspect_completed_records()
    assert len(recovered) == 1
    recovered_candidate = recovered[0][0].candidate
    assert recovered_candidate["selected_sources"] == [dict(source) for source in selection.sources]
    assert [fact["source"] for fact in recovered_candidate["selected_facts"]] == [
        dict(selection.sources[0])]


def test_recovery_rejects_duplicate_source_binding_after_identity_reconstruction(tmp_path: Path) -> None:
    ctrl, authority = controller(tmp_path)
    _selection, candidate, _fake = candidate_for(ctrl)
    record, receipt = ctrl.append(
        candidate, admission=issue(authority, candidate), operation_id="op-1",
        correlation_id="c", created_at="fixed")
    record_path = ctrl.store.records_root / f"{record.record_id}.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    candidate_payload = payload["candidate"]
    candidate_payload["selected_fact_ids"] = tuple(candidate_payload["selected_fact_ids"])
    candidate_payload["selected_sources"] = tuple(candidate_payload["selected_sources"])
    candidate_payload["selected_facts"] = tuple(candidate_payload["selected_facts"])
    candidate_payload["selected_sources"] += (dict(candidate_payload["selected_sources"][0]),)
    recovered_candidate = DevelopmentalCandidate(**candidate_payload)
    candidate_id, candidate_digest = _identity(
        "devcand", recovered_candidate.semantic_payload())
    recovered_candidate = replace(
        recovered_candidate, candidate_id=candidate_id, candidate_digest=candidate_digest)
    tampered_record = replace(record, record_id="", record_digest="",
        candidate=asdict(recovered_candidate))
    record_id, record_digest = _identity("devrec", tampered_record.semantic_payload())
    tampered_record = replace(tampered_record, record_id=record_id, record_digest=record_digest)

    # Simulate storage corruption with internally recomputed content identities.
    # The original admission cannot legitimize the duplicate source row, and
    # recovery must reject it before treating the missing receipt as repairable.
    record_path.unlink()
    (ctrl.store.receipts_root / f"{receipt.receipt_id}.json").unlink()
    tampered_path = ctrl.store.records_root / f"{record_id}.json"
    tampered_path.write_text(
        json.dumps(asdict(tampered_record), sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    tampered_path.chmod(0o600)
    with pytest.raises(DevelopmentalWritebackError, match="candidate_source_binding_invalid"):
        ctrl.inspect_completed_records()


def test_snapshot_validation_membership_and_provenance_tampering_fail_closed(tmp_path: Path) -> None:
    ctrl, _ = controller(tmp_path); snap = snapshot()
    with pytest.raises(DevelopmentalWritebackError, match="selected_fact_not_in_snapshot"): ctrl.select_evidence(snap, fact_ids=["missing"])
    with pytest.raises(DevelopmentalWritebackError, match="snapshot_digest_mismatch"): ctrl.select_evidence(replace(snap, digest="tampered"), fact_ids=[snap.facts[0].fact_id])
    source = replace(snap.sources[0], digest="tampered")
    with pytest.raises(DevelopmentalWritebackError, match="snapshot_digest_mismatch"): ctrl.select_evidence(replace(snap, sources=(source, *snap.sources[1:])), fact_ids=[snap.facts[0].fact_id])


def test_inference_is_bounded_structured_and_candidate_digest_is_deterministic(tmp_path: Path) -> None:
    ctrl, _ = controller(tmp_path); selection, first, fake = candidate_for(ctrl)
    second = ctrl.candidate_from_receipt(selection, fake.invoke(fake.request, persist=True, include_output_in_receipt=False))
    assert first == second
    assert fake.request.expected_output_format == "json" and fake.request.structured_output_schema["additionalProperties"] is False
    assert first.epistemic_status == "untrusted_historical_interpretation_candidate"
    assert not hasattr(first, "authority") and not hasattr(first, "current_truth") and not hasattr(first, "storage_outcome")
    with pytest.raises(DevelopmentalWritebackError, match="budget_unbounded"):
        ctrl.infer_candidate(selection, invoker=fake, correlation_id="other", budget=LocalModelInvocationBudget(max_calls_per_correlation=2))


@pytest.mark.parametrize("output", ["not-json", {}, {"interpretation":"x","uncertainty":"certain"}, {"interpretation":"x","uncertainty":"low","authority":True}])
def test_malformed_or_authoritative_model_output_is_rejected(tmp_path: Path, output: object) -> None:
    ctrl, _ = controller(tmp_path); snap = snapshot(); selection = ctrl.select_evidence(snap, fact_ids=[snap.facts[0].fact_id])
    with pytest.raises(DevelopmentalWritebackError, match="malformed_developmental_output"):
        ctrl.infer_candidate(selection, invoker=FakeInvoker(output), correlation_id="corr-bad")


def test_missing_wrong_or_crossed_runtime_admission_is_rejected(tmp_path: Path) -> None:
    ctrl, authority = controller(tmp_path); _, candidate, _ = candidate_for(ctrl)
    with pytest.raises((AttributeError, DevelopmentalWritebackError)): ctrl.append(candidate, admission=None, operation_id="op-1", correlation_id="c")  # type: ignore[arg-type]
    for admission in (
        issue(authority, candidate, principal="other", suffix="wrong", sequence=1),
        issue(authority, candidate, effects=EFFECTS[:-1], suffix="effects", sequence=2),
        issue(authority, candidate, config="sha256:crossed", suffix="crossed", sequence=3),
    ):
        with pytest.raises(DevelopmentalWritebackError): ctrl.append(candidate, admission=admission, operation_id="op-1", correlation_id="c")


def test_candidate_tamper_and_store_identity_collision_fail_closed(tmp_path: Path) -> None:
    ctrl, authority = controller(tmp_path); _, candidate, _ = candidate_for(ctrl); admission = issue(authority, candidate)
    with pytest.raises(DevelopmentalWritebackError, match="candidate_digest_mismatch"):
        ctrl.append(replace(candidate, interpretation="changed"), admission=admission, operation_id="op-1", correlation_id="c")
    record, _ = ctrl.append(candidate, admission=admission, operation_id="op-1", correlation_id="c", created_at="fixed")
    ctrl.append(candidate, admission=admission, operation_id="op-1", correlation_id="c", created_at="fixed")
    path = ctrl.store.records_root / f"{record.record_id}.json"; payload = json.loads(path.read_text()); payload["operation_id"] = "changed"; path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    with pytest.raises(DevelopmentalWritebackError, match="record_digest_mismatch"): ctrl.store.get(record.record_id)


def test_retrieval_is_exact_bounded_and_preserves_contradiction_visibility(tmp_path: Path) -> None:
    ctrl, authority = controller(tmp_path); snap = snapshot(); selection = ctrl.select_evidence(snap, fact_ids=[f.fact_id for f in snap.facts])
    candidate = ctrl.infer_candidate(selection, invoker=FakeInvoker({"interpretation":"conflicting history remains visible","uncertainty":"high"}), correlation_id="c")
    record, _ = ctrl.append(candidate, admission=issue(authority, candidate), operation_id="op-1", correlation_id="c", created_at="fixed")
    assert ctrl.retrieve([record.record_id]).records[0]["candidate"]["transformation_provenance"]
    with pytest.raises(DevelopmentalWritebackError, match="retrieval_bounds_invalid"): ctrl.retrieve([record.record_id], limit=0)


def test_controlled_changed_cognition_measurement_reports_difference_not_learning() -> None:
    measured = measure_changed_cognition(with_record=CognitionObservation("condition-with","cognition-a","sha256:a",("devrec-a",)), without_record=CognitionObservation("condition-withheld","cognition-b","sha256:b",()), expected_record_ids=("devrec-a",))
    assert measured.observable_difference
    assert measured.interpretation == "difference_only_not_improvement_learning_or_correctness"
    assert all(word not in measured.__dict__ for word in ("improvement","learning","correctness","selfhood","consciousness"))


def test_developmental_history_is_physically_separate_from_canonical_memory(tmp_path: Path) -> None:
    ctrl, _ = controller(tmp_path)
    assert ctrl.store.root == tmp_path / "developmental-history"
    assert "canonical" not in ctrl.store.root.name and "memory" not in ctrl.store.root.name
    import sentientos.canonical_memory as canonical_memory
    assert not hasattr(canonical_memory, "resident_developmental_writeback")


def test_dangling_record_root_is_not_recovered_as_empty(tmp_path: Path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("dangling symlink fixture requires POSIX filesystem semantics")
    store = DevelopmentalHistoryStore(tmp_path / "history")
    store.root.mkdir()
    store.records_root.symlink_to(tmp_path / "missing-records-target", target_is_directory=True)
    with pytest.raises(DevelopmentalWritebackError, match="durable_record_root_invalid"):
        store.records()


def test_dangling_receipt_root_is_not_recovered_as_empty(tmp_path: Path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("dangling symlink fixture requires POSIX filesystem semantics")
    store = DevelopmentalHistoryStore(tmp_path / "history")
    store.root.mkdir()
    store.receipts_root.symlink_to(tmp_path / "missing-receipts-target", target_is_directory=True)
    with pytest.raises(DevelopmentalWritebackError, match="durable_receipt_root_invalid"):
        store.receipts()


def test_recovery_rejects_receipt_without_its_durable_record(tmp_path: Path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("durable publication fixture requires POSIX semantics")
    ctrl, authority = controller(tmp_path)
    _, candidate, _ = candidate_for(ctrl)
    record, _receipt = ctrl.append(
        candidate, admission=issue(authority, candidate), operation_id="op-1",
        correlation_id="c", created_at="fixed")
    (ctrl.store.records_root / f"{record.record_id}.json").unlink()
    with pytest.raises(DevelopmentalWritebackError, match="durable_receipt_orphaned"):
        ctrl.recover_completed_records()


def test_recovery_repairs_interrupted_receipt_publication_idempotently(tmp_path: Path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("immutable receipt repair requires POSIX publication")
    ctrl, authority = controller(tmp_path)
    _, candidate, _ = candidate_for(ctrl)
    record, expected_receipt = ctrl.append(
        candidate, admission=issue(authority, candidate), operation_id="op-1",
        correlation_id="c", created_at="fixed")
    record_path = ctrl.store.records_root / f"{record.record_id}.json"
    original_record = record_path.read_bytes()
    (ctrl.store.receipts_root / f"{expected_receipt.receipt_id}.json").unlink()

    recovered = ctrl.recover_completed_records()
    assert len(recovered) == 1
    assert recovered[0][0].record_id == record.record_id
    assert recovered[0][0].record_digest == record.record_digest
    assert recovered[0][1] == expected_receipt
    assert record_path.read_bytes() == original_record
    assert ctrl.store.get_receipt(expected_receipt.receipt_id) == expected_receipt
    assert ctrl.recover_completed_records() == recovered


def test_history_publication_uses_private_descriptor_bound_immutable_files(tmp_path: Path) -> None:
    import os
    import stat

    if os.name != "posix":
        pytest.skip("descriptor-relative immutable publication requires POSIX")
    from sentientos.resident_developmental_writeback import (
        _publish_store_json,
    )

    path = tmp_path / "history" / "records" / "devrec-test.json"
    payload = {"value": "original"}
    _publish_store_json(path, payload, collision_error="record_identity_collision")

    metadata = path.stat()
    root_metadata = path.parent.stat()
    assert stat.S_ISREG(metadata.st_mode)
    assert metadata.st_uid == os.geteuid()
    assert metadata.st_mode & 0o077 == 0
    assert root_metadata.st_uid == os.geteuid()
    assert root_metadata.st_mode & 0o022 == 0
    assert DevelopmentalHistoryStore._read_json(path) == payload

    _publish_store_json(path, payload, collision_error="record_identity_collision")
    with pytest.raises(DevelopmentalWritebackError, match="record_identity_collision"):
        _publish_store_json(path, {"value": "substituted"},
                            collision_error="record_identity_collision")


def test_history_publication_rejects_symlinked_directory_components(tmp_path: Path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("no-follow directory publication requires POSIX")
    from sentientos.resident_developmental_writeback import _publish_store_json

    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    with pytest.raises(DevelopmentalWritebackError,
                       match="durable_store_root_unavailable|durable_store_path_permissions_invalid"):
        _publish_store_json(alias / "records" / "devrec-test.json", {"safe": True},
                            collision_error="record_identity_collision")
    assert list(outside.iterdir()) == []


def test_developmental_store_rejects_canonical_memory_custody(tmp_path: Path) -> None:
    from sentientos.canonical_memory import sentientos_memory_dir

    with pytest.raises(DevelopmentalWritebackError,
                       match="durable_store_root_overlaps_canonical_memory"):
        DevelopmentalHistoryStore(sentientos_memory_dir())


def test_developmental_store_rejects_storage_inside_canonical_memory(tmp_path: Path) -> None:
    from sentientos.canonical_memory import sentientos_memory_dir

    memory_root = sentientos_memory_dir()
    with pytest.raises(DevelopmentalWritebackError,
                       match="durable_store_root_overlaps_canonical_memory"):
        DevelopmentalHistoryStore(memory_root / "retained-user-content")


def test_concurrent_retry_of_one_operation_reuses_durable_record(tmp_path: Path) -> None:
    import os
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    if os.name != "posix":
        pytest.skip("POSIX operation lock is required")
    first, authority = controller(tmp_path)
    second, _ = controller(tmp_path)
    _selection, candidate, _fake = candidate_for(first)
    admission = issue(authority, candidate, operation_id="one-operation",
        config=ResidentDevelopmentalWritebackController.admission_configuration_digest(
            candidate, operation_id="one-operation"))
    barrier = Barrier(2)

    def append_with(owner):
        barrier.wait()
        return owner.append(candidate, admission=admission,
            operation_id="one-operation", correlation_id="one-correlation")

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(append_with, first)
        right = pool.submit(append_with, second)
        left_record, left_receipt = left.result()
        right_record, right_receipt = right.result()

    assert left_record.record_id == right_record.record_id
    assert left_receipt.receipt_id == right_receipt.receipt_id
    assert len(first.store.records()) == 1
    assert len(first.store.receipts()) == 1


def test_developmental_history_inventory_rejects_linked_json_file(tmp_path: Path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("POSIX descriptor inventory is required")
    store = DevelopmentalHistoryStore(tmp_path / "developmental-history")
    store.records_root.mkdir(parents=True, mode=0o700)
    external = tmp_path / "outside.json"
    external.write_text("{}", encoding="utf-8")
    (store.records_root / "linked.json").symlink_to(external)
    with pytest.raises(DevelopmentalWritebackError):
        store.records()
    assert external.read_text(encoding="utf-8") == "{}"


def test_completed_inventory_exports_receipt_digest_from_receipt_identity(tmp_path: Path) -> None:
    ctrl, authority = controller(tmp_path)
    _selection, candidate, _fake = candidate_for(ctrl)
    record, receipt = ctrl.append(candidate, admission=issue(authority, candidate),
        operation_id="op-1", correlation_id="receipt-evidence", created_at="fixed")

    verified = ctrl.inspect_completed_records()
    assert len(verified) == 1
    inventory_record, inventory_receipt = verified[0]
    assert inventory_record.record_id == record.record_id
    assert inventory_receipt.receipt_id == receipt.receipt_id
    evidence = {
        "record_digest": inventory_record.record_digest,
        "writeback_receipt_id": inventory_receipt.receipt_id,
        "writeback_receipt_digest": inventory_receipt.receipt_digest,
    }

    assert evidence["record_digest"] == record.record_digest
    assert evidence["writeback_receipt_digest"] == receipt.receipt_digest
    assert evidence["writeback_receipt_digest"] != evidence["record_digest"]
    assert evidence["writeback_receipt_id"].startswith("devreceipt-")
