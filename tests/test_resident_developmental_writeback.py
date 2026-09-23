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
    EFFECTS, PRINCIPAL, PURPOSE, CognitionObservation, DevelopmentalHistoryStore,
    DevelopmentalWritebackError, ResidentDevelopmentalWritebackController,
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
    path = ctrl.store.records_root / f"{record.record_id}.json"; payload = json.loads(path.read_text()); payload["operation_id"] = "changed"; path.write_text(json.dumps(payload))
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
