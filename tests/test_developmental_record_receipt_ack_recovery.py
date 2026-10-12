from __future__ import annotations

import pytest

from sentientos.resident_developmental_cognition import ResidentDevelopmentalCognitionError
from sentientos.world_state_board import WorldStateBoardBuilder
from tests.test_developmental_model_replacement_experiment import experiment
from tests.test_resident_developmental_cognition import FakeInvoker, owner, snapshot

pytestmark = pytest.mark.no_legacy_skip


def test_restart_repairs_history_record_published_before_receipt_acknowledgement(tmp_path) -> None:
    interrupted, _fake = owner(tmp_path)

    def fail_receipt_acknowledgement(receipt):
        # The canonical record publication has already succeeded when this
        # method is called. Simulate process loss before receipt custody.
        assert len(interrupted.writeback.store.records()) == 1
        assert interrupted.writeback.store.receipts() == ()
        raise ResidentDevelopmentalCognitionError("simulated_before_receipt_publication")

    interrupted.writeback.store.write_receipt = fail_receipt_acknowledgement
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="simulated_before_receipt_publication"):
        interrupted.run_tick(snapshot=snapshot(), tick_id="tick-before-receipt")

    durable_records = interrupted.writeback.store.records()
    assert len(durable_records) == 1
    assert interrupted.writeback.store.receipts() == ()

    restarted, fake = owner(tmp_path)
    recovered_state = restarted._state()
    assert len(restarted.writeback.store.records()) == 1
    recovered_receipts = restarted.writeback.store.receipts()
    assert len(recovered_receipts) == 1
    assert recovered_receipts[0].record_id == durable_records[0].record_id
    assert recovered_receipts[0].record_digest == durable_records[0].record_digest
    checkpoint = next(row for row in recovered_state["completed_ticks"]
                      if row["tick_id"] == "tick-before-receipt")
    assert checkpoint["record_id"] == durable_records[0].record_id
    assert checkpoint["receipt_id"] == recovered_receipts[0].receipt_id
    assert not any(row.get("tick_id") == "tick-before-receipt"
                   for row in recovered_state["incomplete_ticks"])
    assert restarted.writeback.recover_completed_records() == (
        (durable_records[0], recovered_receipts[0]),)

    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(), tick_id="tick-before-receipt")
    later = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-after-receipt-recovery")
    assert later.prior_record_ids == (durable_records[0].record_id,)
    assert any(request.purpose == "resident_developmental_retrieval_cognition"
               for request in fake.requests)


def test_verified_model_replacement_run_reaches_recovered_later_cognition(tmp_path) -> None:
    replacement, _model_a, _model_b = experiment(tmp_path / "replacement")
    run = replacement.run()
    source_records = replacement.store.world_state_records(
        run_refs=((run["run_id"], run["run_digest"]),))
    board = WorldStateBoardBuilder().build(source_records)
    experiment_facts = [fact for fact in board.facts
        if fact.subject.subject_kind == "developmental_model_replacement_experiment"]
    assert len(experiment_facts) == 1
    experiment_fact = experiment_facts[0]
    assert experiment_fact.source.kind == "embodiment"
    assert experiment_fact.payload["protocol_digest"] == run["protocol"]["protocol_digest"]
    assert experiment_fact.payload["claims_posture"] == "bounded_digest_level_observed_association_only"
    assert experiment_fact.payload["authority"] is False
    assert experiment_fact.observed_at is None
    assessment = experiment_fact.payload["continuity_assessment"]
    assert assessment["history_identity"]["posture"] == "frozen_context_record_set_bound"
    assert assessment["history_identity"]["cross_process_continuity"] == (
        "not_established_by_this_run_artifact")
    assert assessment["input_delivery"]["posture"] == "condition_request_lineage_verified"
    assert assessment["input_delivery"]["model_internal_use"] == (
        "not_established_by_request_or_receipt_custody")
    assert assessment["output_relation"]["posture"] == (
        "digest_level_observed_association_only")
    assert assessment["output_relation"]["improvement_posture"] == "not_assessed"

    first, _first_fixture = owner(
        tmp_path / "history", allowed_source_kinds=("embodiment",), max_selected_facts=4)
    first_tick = first.run_tick(snapshot=board, tick_id="model-replacement-history-tick-n")
    assert first_tick.status == "completed"
    assert first_tick.written_record_id is not None
    retained = first.writeback.store.get(first_tick.written_record_id)
    selected = next(fact for fact in retained.candidate["selected_facts"]
        if fact["subject"]["subject_kind"] == "developmental_model_replacement_experiment")
    assert selected["source"]["digest"] == experiment_fact.source.digest
    assert selected["subject"]["subject_id"] == run["run_id"]
    assert selected["disposition"] == experiment_fact.disposition
    assert selected["payload"]["protocol_digest"] == run["protocol"]["protocol_digest"]
    assert selected["payload"]["run_digest"] == run["run_digest"]
    assert selected["payload"]["projection_posture"] == "complete"
    assert selected["payload"]["event_time_postures"] == ["unknown"]
    assert selected["payload"]["vector_hash_encoding"] == "sha256_hex"
    assert len(selected["payload"]["conditions"]) == 5
    retained_assessment = selected["payload"]["continuity_assessment"]
    assert retained_assessment["history"] == "bound"
    assert retained_assessment["history_set_digest"] == assessment[
        "history_identity"]["record_set_digest"]
    assert retained_assessment["restart"] == "not_established"
    assert retained_assessment["input"] == "request_lineage_verified"
    assert retained_assessment["model_use"] == "not_established"
    assert retained_assessment["output"] == "digest_association_only"
    assert retained_assessment["improvement"] == "not_assessed"
    assert selected["payload"]["model_lineage"][0][0] == experiment_fact.payload["model_a_id"]
    assert selected["payload"]["model_lineage"][1][0] == experiment_fact.payload["model_b_id"]
    assert retained.current_truth is False and retained.authority is False

    restarted, fixture = owner(
        tmp_path / "history", allowed_source_kinds=("embodiment",),
        max_selected_facts=4, invoker=FakeInvoker())
    later_tick = restarted.run_tick(snapshot=board, tick_id="model-replacement-history-tick-n1")
    assert first_tick.written_record_id in later_tick.prior_record_ids
    retrieval = next(request for request in fixture.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert first_tick.written_record_id in retrieval.upstream_evidence["record_ids"]
    assert retrieval.upstream_evidence["epistemic_projection_id"] is None
