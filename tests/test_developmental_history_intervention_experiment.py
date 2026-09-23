from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore, DevelopmentalHistoryInterventionError,
    make_protocol, summarize, verify_protocol,
)
from sentientos.local_model_authority import digest_payload
from tests.test_resident_developmental_cognition import FakeInvoker, owner, snapshot

pytestmark = pytest.mark.no_legacy_skip


def protocol():
    return make_protocol(snapshot_id="snapshot", snapshot_digest="sha256:snapshot",
        current_projection_id="projection", current_projection_digest="sha256:projection",
        current_fact_ids=("fact",), record_ids=("record",), record_digests=("sha256:record",),
        record_set_digest="sha256:set", model_id="model", model_artifact_digest="sha256:model",
        active_model_identity={"model":"exact"}, active_model_identity_digest="sha256:identity",
        authority_map_digest="sha256:authority", inference_budget={"max_new_tokens":512},
        generation_posture={"temperature":0, "hardware_determinism_claimed":False},
        instruction_template_digest="sha256:template")


def test_protocol_is_deterministic_preregistered_and_tamper_detecting(tmp_path: Path) -> None:
    first = protocol(); assert first == protocol()
    store = DevelopmentalExperimentStore(tmp_path); store.persist_protocol(first)
    assert (store.protocols / f"{first.protocol_id}.json").exists()
    assert first.condition_order == ("history_present", "history_withheld", "history_restored")
    assert first.generation_posture["temperature"] == 0 and not first.grants_authority
    with pytest.raises(DevelopmentalHistoryInterventionError, match="digest_mismatch"):
        verify_protocol(replace(first, snapshot_id="tampered"))


def test_stable_difference_and_no_difference_are_bounded_descriptions() -> None:
    def observation(condition: str, output: str, records: tuple[str, ...]):
        return SimpleNamespace(condition_id=condition, observation_id=condition,
            observation_digest="sha256:" + condition, output_digest=output, retrieved_record_ids=records)
    stable = summarize(protocol(), [observation("history_present", "a", ("record",)),
        observation("history_withheld", "b", ()), observation("history_restored", "a", ("record",))])
    assert stable["classification"] == "history_presence_associated_stable_difference"
    assert stable["claims_posture"] == "bounded_observed_association_only"
    same = summarize(protocol(), [observation("history_present", "a", ("record",)),
        observation("history_withheld", "a", ()), observation("history_restored", "a", ("record",))])
    assert same["classification"] == "no_observable_history_difference"


def test_actual_current_evidence_is_bounded_and_independent_of_writeback_dedup(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-n")
    composition.run_tick(snapshot=snapshot(), tick_id="tick-n-plus-one")
    cognition = next(r for r in fake.requests if r.purpose == "resident_developmental_retrieval_cognition")
    prompt = json.loads(cognition.prompt)
    current = prompt["current_evidence"]
    assert current["facts"] and current["sources"]
    assert current["facts"][0]["payload"] == {"value": 1}
    assert current["read_only"] and current["evidence_only"] and not current["authority"]
    # The fact was processed on tick N but remains visible as current context on tick N+1.
    assert cognition.upstream_evidence["current_fact_ids"] == [current["facts"][0]["fact_id"]]


def test_formal_run_preregisters_then_withholds_without_mutating_and_restores_exactly(tmp_path: Path) -> None:
    first, _ = owner(tmp_path); written = first.run_tick(snapshot=snapshot(), tick_id="tick-n").written_record_id
    record_path = next((tmp_path / "history" / "records").glob("*.json")); before = record_path.read_bytes()
    composition, fake = owner(tmp_path, comparison=True)
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-n-plus-one")
    calls = [r for r in fake.requests if r.purpose == "resident_developmental_history_intervention_experiment" and "history_present" in r.linkage]
    assert [r.linkage["history_present"] for r in calls] == [True, False, True]
    assert calls[0].upstream_evidence["record_ids"] == [written]
    assert calls[1].upstream_evidence["record_ids"] == []
    assert calls[2].upstream_evidence["record_ids"] == [written]
    assert record_path.read_bytes() == before
    run = json.loads((composition.experiments.runs / f"{result.changed_cognition_measurement_id}.json").read_text())
    assert run["validity"] == "valid_controlled_observation"
    assert run["protocol"]["record_digests"] == calls[2].upstream_evidence["record_digests"]
    assert not list((tmp_path / "history" / "records").glob("*withheld*"))


def test_missing_record_is_not_deliberate_withholding(tmp_path: Path) -> None:
    first, _ = owner(tmp_path); first.run_tick(snapshot=snapshot(), tick_id="tick-n")
    next((tmp_path / "history" / "records").glob("*.json")).unlink()
    composition, _ = owner(tmp_path, comparison=True)
    with pytest.raises(Exception, match="record_missing_or_corrupt"):
        composition.run_tick(snapshot=snapshot(2), tick_id="tick-n-plus-one")


def test_same_tick_history_exclusion_remains_explicit(tmp_path: Path) -> None:
    composition, _ = owner(tmp_path, comparison=True)
    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-n")
    assert result.same_tick_history_excluded and not result.prior_record_ids
    assert not list(composition.experiments.protocols.glob("*.json"))


def test_active_model_drift_invalidates_before_later_condition(tmp_path: Path) -> None:
    first, _ = owner(tmp_path); first.run_tick(snapshot=snapshot(), tick_id="tick-n")
    class DriftingInvoker(FakeInvoker):
        def build_request(self, **kwargs):
            request = super().build_request(**kwargs)
            if kwargs["purpose"] == "resident_developmental_history_intervention_experiment" and len(
                [r for r in self.requests if r.purpose == kwargs["purpose"]]
            ) >= 3:
                request.model_id = "model-drifted"
            return request
    composition, _ = owner(tmp_path, comparison=True, invoker=DriftingInvoker())
    with pytest.raises(Exception, match="experiment_control_drift"):
        composition.run_tick(snapshot=snapshot(2), tick_id="tick-n-plus-one")
    assert list(composition.experiments.protocols.glob("*.json"))
    assert len(list(composition.experiments.runs.glob("*.json"))) == 0
