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
    MAX_COMPLETE_CONSEQUENCE_CYCLE_SELECTED_EVIDENCE_BYTES,
    MAX_COMPLETE_CONSEQUENCE_CYCLE_INPUT_CHARS,
    MAX_DEVELOPMENTAL_EXPERIMENT_SELECTED_EVIDENCE_BYTES, MAX_SELECTED_EVIDENCE_BYTES,
    MAX_OBJECTIVE_TASK_FAMILY_SELECTED_EVIDENCE_BYTES,
    _selected_fact_byte_limit, _writeback_input_limit, measure_changed_cognition,
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


def test_receipt_consequence_cycle_requires_valid_lineage_for_expanded_budget() -> None:
    from dataclasses import asdict

    from sentientos.avatar_renderer_report_ingress import RendererReportReceiptIdentity

    identity = RendererReportReceiptIdentity(
        report_id="godot-renderer:godot-demo-budget-test:1",
        report_digest="sha256:" + "a" * 64,
        renderer_source_id="godot-adopted-body-demo",
        renderer_generation_id="godot-demo-budget-test", sequence=1,
        session_id="session-test", turn_id="turn-test",
        output_digest="b" * 64,
        expectation_id="expectation-test", expectation_digest="sha256:" + "c" * 64,
        handoff_id="handoff-test", handoff_digest="sha256:" + "d" * 64,
        correlation_id="correlation-test", body_generation=1,
    )
    component_kinds = (
        "embodied_action_expectation", "avatar_renderer_handoff",
        "avatar_independently_observed_state", "embodied_consequence_attribution",
        "embodied_prediction_comparison",
    )
    component_ids = [identity.expectation_id, identity.handoff_id, "component:2",
        "component:3", "component:4"]
    component_digests = ["sha256:" + format(index, "064x")
        for index, _ in enumerate(component_kinds)]
    facts = []
    for kind, source_id, source_digest in zip(
            component_kinds, component_ids, component_digests):
        payload = {"bounded_context": "x" * 1300}
        if kind == "embodied_action_expectation":
            payload.update({"expectation_id": identity.expectation_id,
                "expectation_digest": identity.expectation_digest,
                "correlation_id": identity.correlation_id,
                "body_generation": identity.body_generation})
        elif kind == "avatar_renderer_handoff":
            payload.update({"handoff_id": identity.handoff_id,
                "handoff_digest": identity.handoff_digest})
        elif kind == "avatar_independently_observed_state":
            payload.update({"renderer_report_id": identity.report_id,
                "renderer_report_digest": identity.report_digest})
        elif kind == "embodied_consequence_attribution":
            payload["observation_authentication_receipt"] = {
                "transport_authenticated_at_ingress": True,
                "observation_time_posture":
                    "authenticated_request_correlated_receiver_time",
                "capture_request_id": "e" * 32,
                "capture_provenance": {"capture_scope":
                    "allowlisted_foreground_game_client_area"},
                "renderer_report_receipt_identity": asdict(identity),
            }
        facts.append({"source": {"kind": "embodiment", "source_id": source_id,
                "digest": source_digest},
            "subject": {"subject_kind": kind}, "payload": payload,
            "effect_proven": False, "effect_claimed": False})

    chain_id = "chain:receipt-budget"
    chain_digest = "sha256:" + "f" * 64
    facts.append({"source": {"kind": "embodiment", "source_id": chain_id,
            "digest": chain_digest},
        "subject": {"subject_kind": "embodied_consequence_chain"},
        "payload": {"chain_id": chain_id, "effect_proven": False,
            "current_truth": False, "component_source_ids": component_ids,
            "component_record_digests": component_digests,
            "bounded_context": "x" * 1300},
        "effect_proven": False, "effect_claimed": False})
    facts.extend((
        {"source": {"kind": "embodiment", "source_id": "screen:test",
            "digest": "sha256:" + "1" * 64},
         "subject": {"subject_kind": "allowlisted_foreground_game_screen"},
         "payload": {"capture_scope": "allowlisted_foreground_game_client_area",
             "raw_frame_retained": False, "bounded_context": "x" * 1300},
         "effect_proven": False, "effect_claimed": False},
        {"source": {"kind": "embodiment", "source_id": "proprioception:test",
            "digest": "sha256:" + "2" * 64},
         "subject": {"subject_kind": "proprioceptive_state"},
         "payload": {"embodiment_evidence_class": "sensor_observation",
             "observer_issuer_posture": "unverified_caller_assertion",
             "bounded_context": "x" * 1300},
         "effect_proven": False, "effect_claimed": False},
    ))

    facts = [{**fact, "fact_id": f"fact-{index}"}
        for index, fact in enumerate(facts)]
    assert len(facts) == 8
    assert _selected_fact_byte_limit(facts) == (
        MAX_COMPLETE_CONSEQUENCE_CYCLE_SELECTED_EVIDENCE_BYTES)
    selection = SelectedEvidence("snapshot", "sha256:snapshot", tuple(facts), (), ())
    assert _writeback_input_limit(selection.facts) == (
        MAX_COMPLETE_CONSEQUENCE_CYCLE_INPUT_CHARS)
    fake = FakeInvoker({"interpretation": "A bounded historical pattern.",
        "uncertainty": "medium"})
    ResidentDevelopmentalWritebackController.infer_candidate(
        selection, invoker=fake, correlation_id="consequence-cycle-budget")
    assert fake.request.budget.max_input_chars == (
        MAX_COMPLETE_CONSEQUENCE_CYCLE_INPUT_CHARS)
    assert json.loads(fake.request.prompt)["selection"] == selection.semantic_payload()
    assert MAX_SELECTED_EVIDENCE_BYTES < sum(
        len(json.dumps(fact, sort_keys=True).encode("utf-8")) for fact in facts)

    malformed = json.loads(json.dumps(facts))
    malformed[3]["payload"]["observation_authentication_receipt"][
        "renderer_report_receipt_identity"]["handoff_id"] = "different-handoff"
    assert _selected_fact_byte_limit(malformed) == MAX_SELECTED_EVIDENCE_BYTES
    assert _writeback_input_limit(malformed) == 8000


def test_objective_task_family_trial_gets_narrow_selected_evidence_and_prompt_budgets():
    fact = {
        "source": {"kind": "embodiment", "source_id": "developmental-history-run:trial",
            "digest": "sha256:" + "a" * 64},
        "subject": {"subject_kind": "developmental_history_intervention_experiment"},
        "payload": {
            "current_truth": False, "authority": False, "learning_established": False,
            "task_family_posture": "operator_declared_protocol_bound",
            "objective_task_commitment_posture": "salted_private_oracle_commitment:v1",
            "objective_task_family": "synthetic-affine-family",
            "interpretation_projection": {
                "schema_version": "sentientos.developmental_history_interpretation_projection:v1"},
            "objective_task_descriptor": {"task_family_id": "synthetic-affine-family",
                "task_digest_posture": "salted_private_oracle_commitment:v1",
                "task_digest": "sha256:" + "b" * 64},
            "objective_scores": [
                {"condition_id": "history_present", "score_digest": "sha256:" + "c" * 64,
                 "schema_version": "sentientos.objective_task_score:v3",
                 "plan_digest": "sha256:" + "d" * 64,
                 "task_digest": "sha256:" + "b" * 64,
                 "evaluator": "deterministic_exact_integer_suite_oracle_v2",
                 "status": "incorrect"},
                *[{"condition_id": condition, "score_digest": "sha256:" + "c" * 64,
                   "status": "incorrect"} for condition in (
                    "history_withheld", "history_restored")]],
            "conditions": [{
                "condition_id": condition,
                "observation_id": f"observation-{index}",
                "observation_digest": "sha256:" + format(index, "064x"),
                "output_digest": "sha256:" + format(index + 1, "064x"),
                "request_id": f"request-{index}",
                "request_digest": "sha256:" + format(index + 2, "064x"),
                "inference_receipt_id": f"lmrec-{index}",
                "inference_receipt_digest": "sha256:" + format(index + 3, "064x"),
                "serving_session_id": "serving-session-test",
                "observed_at": f"2026-01-0{index + 1}T00:00:00+00:00",
            } for index, condition in enumerate((
                "history_present", "history_withheld", "history_restored"))],
            "condition_event_times": [
                "2026-01-01T00:00:01+00:00", "2026-01-02T00:00:01+00:00",
                "2026-01-03T00:00:01+00:00"],
            "event_time_posture": "all_condition_invocation_receipt_times_verified",
            "execution_evidence_conditions": [{
                "condition_id": condition,
                "invocation_receipt_id": f"lmrec-{index}",
                "invocation_receipt_digest": "sha256:" + format(index + 3, "064x"),
                "receipt_identity_verified": True,
                "receipt_status": "admitted_simulation",
                "local_model_inference_effect": False,
                "fallback_occurred": False,
                "posture": "receipt_reports_simulation_or_no_backend_entry",
                "independent_backend_observation": False,
            } for index, condition in enumerate((
                "history_present", "history_withheld", "history_restored"))],
            "execution_evidence_posture": (
                "one_or_more_conditions_simulated_or_no_backend_entry"),
            "execution_evidence_scope": (
                "authenticated_owner_receipt_not_independent_backend_observation"),
            "independent_backend_observation": False,
            "acquisition_examples": [{"probe_input": 7, "observed_answer": 20,
                "evaluator_correct": False, "source_score_digest": "sha256:" + "c" * 64,
                "source_condition": "history_present"}],
        },
        "effect_proven": False,
    }

    assert _selected_fact_byte_limit([fact]) == (
        MAX_OBJECTIVE_TASK_FAMILY_SELECTED_EVIDENCE_BYTES)
    assert MAX_OBJECTIVE_TASK_FAMILY_SELECTED_EVIDENCE_BYTES == 12_288
    assert _writeback_input_limit([fact]) == 16_384

    malformed = json.loads(json.dumps(fact))
    malformed["payload"]["task_family_posture"] = "unbound"
    assert _selected_fact_byte_limit([malformed]) == (
        MAX_DEVELOPMENTAL_EXPERIMENT_SELECTED_EVIDENCE_BYTES)
    assert _writeback_input_limit([malformed]) == 8000

    mismatched_receipt = json.loads(json.dumps(fact))
    mismatched_receipt["payload"]["execution_evidence_conditions"][0][
        "invocation_receipt_id"] = "different-receipt"
    assert _selected_fact_byte_limit([mismatched_receipt]) == (
        MAX_DEVELOPMENTAL_EXPERIMENT_SELECTED_EVIDENCE_BYTES)
    unverified_receipt = json.loads(json.dumps(fact))
    unverified_receipt["payload"]["execution_evidence_conditions"][0][
        "receipt_identity_verified"] = False
    assert _selected_fact_byte_limit([unverified_receipt]) == (
        MAX_DEVELOPMENTAL_EXPERIMENT_SELECTED_EVIDENCE_BYTES)


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
