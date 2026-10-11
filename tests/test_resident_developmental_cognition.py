from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.codex_task_authority_admission import RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION
from sentientos.governed_local_model_invocation import LocalModelInvocationReceipt
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_cognition import (
    CONFIG_SCHEMA, ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionError,
    ResidentDevelopmentalCognitionOwner, load_config, _bind_epistemic_context,
)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from sentientos.world_state_board import WorldStateBoardBuilder
from sentientosd import RuntimeMaintenanceSurfaces, _load_epistemic_state_owner
from sentientos.persistent_epistemic_state import (PersistentEpistemicStateOwner,
    make_proposition, make_evidence_binding, make_cognitive_projection,
    MeaningBearingEpistemicCognitiveProjection)

pytestmark = pytest.mark.no_legacy_skip


def snapshot(value: int = 1):
    return WorldStateBoardBuilder().build([
        {"source_id":"source-b", "source_kind":"audit_trust", "subject_id":"b", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":9}},
        {"source_id":"source-a", "source_kind":"capability_registry", "subject_id":"a", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":value}},
        {"source_id":"source-c", "source_kind":"capability_registry", "subject_id":"c", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":3}},
    ])


class FakeInvoker:
    def __init__(self) -> None:
        self.requests = []

    def build_request(self, **kwargs):
        request = type("Request", (), {})()
        for key, value in kwargs.items(): setattr(request, key, value)
        request.prompt_digest = digest_payload({"prompt": kwargs["prompt"]})
        request.prompt_size = len(kwargs["prompt"].encode("utf-8"))
        request.model_id = "model-a"; request.model_artifact_digest = "sha256:model"
        request.authority_map_digest = "test-authority-map"; request.active_model_identity = {}
        semantic = {"purpose": kwargs["purpose"], "prompt_digest": request.prompt_digest,
                    "prompt_size": request.prompt_size, "correlation_id": kwargs["correlation_id"],
                    "upstream_evidence": kwargs["upstream_evidence"], "linkage": kwargs["linkage"]}
        request.request_digest = digest_payload(semantic); request.request_id = "lmreq-" + request.request_digest[:24]
        request.to_receipt_request_dict = lambda: {**semantic, "request_id":request.request_id,
            "request_digest":request.request_digest, "model_id":"model-a", "model_artifact_digest":"sha256:model"}
        self.requests.append(request)
        return request

    def invoke(self, request, *, persist, include_output_in_receipt):
        if request.purpose == "resident_developmental_interpretation":
            text = json.dumps({"interpretation":"bounded history", "uncertainty":"medium"})
        else:
            text = "cognition-with-history" if request.linkage["history_present"] else "cognition-withheld"
        return LocalModelInvocationReceipt(request=request.to_receipt_request_dict(), status="admitted_completed",
            reason_codes=("completed",), output_text=text, output_digest=digest_payload({"output":text}),
            output_size_bytes=len(text), admission_decision_ref="local",
            purpose=request.purpose, latency_ms=1, output_truncated=False, fallback_occurred=False,
            effects={"local_model_inference":True}, observed_at="2026-01-01T00:00:00+00:00",
            generation_config={"actual_generation_parameters":{"temperature":0}} if request.purpose == "resident_developmental_history_intervention_experiment" else {})


def owner(root: Path, *, comparison: bool = False, invoker: FakeInvoker | None = None):
    ledger = AdmissionLedger(root / "state" / "admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
    def current():
        admissions, _ = ledger.load(); return max((a.issued_sequence for a in admissions), default=1)
    def next_sequence():
        admissions, revocations = ledger.load()
        return max([a.issued_sequence for a in admissions] + [r.sequence for r in revocations], default=0) + 1
    ctrl = ResidentDevelopmentalWritebackController(history_root=root / "history",
        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger), current_sequence=current)
    fake = invoker or FakeInvoker()
    result = ResidentDevelopmentalCognitionOwner(config=ResidentDevelopmentalCognitionConfig(
        root / "history", root / "state", ("capability_registry",), 1, 4, comparison), writeback=ctrl,
        admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
        invoker=fake, current_sequence=next_sequence)
    return result, fake


def epistemic_projection(root: Path):
    epistemic = PersistentEpistemicStateOwner(root, allowed_namespaces=["embodiment"])
    proposition = make_proposition(namespace="embodiment", subject="body:g1", predicate="healthy",
        object_value=True, polarity="positive", qualifiers={}, temporal_scope={"kind":"prior"},
        context_scope={}, proposition_class="descriptive")
    epistemic.register_proposition(proposition)
    state, _ = epistemic.commit_update(proposition_id=proposition.proposition_id,
        expected_predecessor_digest=None, stance="unknown", reason="initialization",
        active_binding_ids=[], correlation_id="prior", tick=1,
        recorded_at="2026-01-01T00:00:00Z")
    projection = epistemic.cognitive_projection(max_states=1)
    assert projection is not None
    return projection, proposition, state


def test_meaning_bearing_epistemic_packets_reach_actual_inference_request(tmp_path: Path):
    epistemic = PersistentEpistemicStateOwner(tmp_path / "epistemic",
        allowed_namespaces=["embodiment"])
    propositions = [make_proposition(namespace="embodiment", subject="sensor:g9",
        predicate="reports_temperature", object_value={"celsius": 20}, polarity="positive",
        qualifiers={"sensor": "exact-a"}, temporal_scope={"window": window},
        context_scope={"room": room}, proposition_class="descriptive",
        statement="canonical temperature proposition")
        for window, room in (("morning", "lab-a"), ("evening", "lab-b"))]
    for index, proposition_value in enumerate(propositions):
        epistemic.register_proposition(proposition_value)
        support = make_evidence_binding(proposition_id=proposition_value.proposition_id,
            source_artifact_id=f"support-{index}", source_digest="sha256:" + str(index + 1) * 64,
            source_schema="sentientos.test_sensor:v1", source_class="fixture",
            observation_time="2026-01-01T00:00:00Z", evidence_relation="supports",
            dependency_kind="independently_sourced_observation", dependency_group=f"group-{index}",
            upstream_binding_ids=(), freshness="current", reliability_posture="verified")
        contradiction = make_evidence_binding(proposition_id=proposition_value.proposition_id,
            source_artifact_id=f"contradiction-{index}", source_digest="sha256:" + str(index + 3) * 64,
            source_schema="sentientos.test_sensor:v1", source_class="fixture",
            observation_time="2025-01-01T00:00:00Z", evidence_relation="contradicts",
            dependency_kind="unknown_dependency", dependency_group=None,
            upstream_binding_ids=(), freshness="stale", reliability_posture="unverified")
        epistemic.bind_evidence(support)
        epistemic.bind_evidence(contradiction)
        state, _ = epistemic.commit_update(proposition_id=proposition_value.proposition_id,
            expected_predecessor_digest=None, stance="contested", reason="initialization",
            active_binding_ids=[support.binding_id, contradiction.binding_id],
            added_binding_ids=[support.binding_id, contradiction.binding_id],
            correlation_id=f"contested-{index}", tick=1,
            recorded_at="2026-01-01T00:00:00Z", confidence={"uncertainty": "high"})
        if index == 1:
            current_contradiction = make_evidence_binding(
                proposition_id=proposition_value.proposition_id,
                source_artifact_id="contradiction-current",
                source_digest="sha256:" + "5" * 64,
                source_schema="sentientos.test_sensor:v1", source_class="fixture",
                observation_time="2026-01-02T00:00:00Z", evidence_relation="contradicts",
                dependency_kind="unknown_dependency", dependency_group=None,
                upstream_binding_ids=(), freshness="current", reliability_posture="unverified")
            epistemic.bind_evidence(current_contradiction)
            changed_state, _ = epistemic.commit_update(proposition_id=proposition_value.proposition_id,
                expected_predecessor_digest=state.state_digest, stance="contested",
                reason="evidence_withdrawal", active_binding_ids=[support.binding_id,
                    current_contradiction.binding_id], added_binding_ids=[current_contradiction.binding_id],
                removed_binding_ids=[contradiction.binding_id], correlation_id="withdraw-stale",
                tick=2, recorded_at="2026-01-02T00:00:00Z")
            epistemic.commit_update(proposition_id=proposition_value.proposition_id,
                expected_predecessor_digest=changed_state.state_digest, stance="contested",
                reason="update_rule_correction", active_binding_ids=[support.binding_id,
                    current_contradiction.binding_id], update_rule_id="fixture-rule:v2",
                correlation_id="after-withdrawal", tick=3,
                recorded_at="2026-01-03T00:00:00Z")
    projection = epistemic.cognitive_projection(max_states=2, current_tick=4)
    assert isinstance(projection, MeaningBearingEpistemicCognitiveProjection)
    composition, fake = owner(tmp_path / "cognition")
    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-2",
        prior_epistemic_state=projection)
    request = next(item for item in fake.requests
        if item.purpose == "resident_developmental_retrieval_cognition")
    consumed = json.loads(request.prompt)["prior_epistemic_state"]
    packets = consumed["semantic_packets"]
    assert len(packets) == 2
    assert {packet["state"]["stance"] for packet in packets} == {"contested"}
    assert {packet["proposition"]["temporal_scope"]["window"] for packet in packets} == {
        "morning", "evening"}
    assert {packet["proposition"]["context_scope"]["room"] for packet in packets} == {
        "lab-a", "lab-b"}
    withdrawn = next(packet for packet in packets if packet["recently_removed_evidence"])
    assert withdrawn["removed_evidence_history"][0]["freshness"] == "stale"
    assert withdrawn["evidence_posture"]["dependency_unresolved"] is True
    assert withdrawn["contradicting_evidence"]
    upstream = request.upstream_evidence
    assert upstream["epistemic_consumed_packet_ids"] == [p["packet_id"] for p in packets]
    assert upstream["epistemic_consumed_packet_digests"] == [p["packet_digest"] for p in packets]
    assert upstream["epistemic_prompt_digest"] == "sha256:" + request.prompt_digest
    observation_id = result.cognition_observation_ids[0]
    recovered, _ = owner(tmp_path / "cognition")
    observation = recovered.verified_cognition_observation(observation_id)
    assert observation["epistemic_consumed_packet_ids"] == upstream["epistemic_consumed_packet_ids"]
    assert observation["epistemic_consumed_content_digest"] == upstream["epistemic_consumed_content_digest"]


def test_legacy_identifier_projection_is_valid_but_not_delivered_as_meaning(tmp_path: Path):
    semantic, proposition_value, state = epistemic_projection(tmp_path / "epistemic")
    legacy = make_cognitive_projection([state], source_tick=1, current_tick=2)
    composition, fake = owner(tmp_path / "cognition")
    composition.run_tick(snapshot=snapshot(), tick_id="tick-2", prior_epistemic_state=legacy)
    request = next(item for item in fake.requests
        if item.purpose == "resident_developmental_retrieval_cognition")
    prior = json.loads(request.prompt)["prior_epistemic_state"]
    assert prior["semantic_status"] == "canonical_definition_unavailable"
    assert prior["semantic_packets"] == []
    assert proposition_value.predicate not in request.prompt
    assert request.upstream_evidence["epistemic_state_ids"] == [state.state_id]


def test_semantic_packets_are_whole_and_omissions_are_bound_under_input_budget(tmp_path: Path):
    epistemic = PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"])
    for index in range(2):
        proposition_value = make_proposition(namespace="embodiment", subject=f"sensor:{index}",
            predicate="long_scoped_measurement", object_value={"value": index}, polarity="positive",
            qualifiers={"canonical_qualifier": "q" * 4500},
            temporal_scope={"window": f"exact-window-{index}"},
            context_scope={"facility": f"facility-{index}"}, proposition_class="descriptive",
            statement="complete statement " + ("s" * 4500))
        epistemic.register_proposition(proposition_value)
        epistemic.commit_update(proposition_id=proposition_value.proposition_id,
            expected_predecessor_digest=None, stance="unknown", reason="initialization",
            active_binding_ids=[], correlation_id=f"long-{index}", tick=index + 1,
            recorded_at="2026-01-01T00:00:00Z")
    projection = epistemic.cognitive_projection(max_states=2, current_tick=3)
    context, metadata, prompt = _bind_epistemic_context(
        context={"instruction": "prior positions are not truth"}, projection=projection)
    assert len(prompt) <= 16_000
    prior = context["prior_epistemic_state"]
    assert len(prior["semantic_packets"]) == 1
    assert len(metadata["epistemic_omitted_packets"]) == 1
    delivered = prior["semantic_packets"][0]
    assert delivered["proposition"]["qualifiers"]["canonical_qualifier"] == "q" * 4500
    assert delivered["proposition"]["context_scope"]["facility"] in {"facility-0", "facility-1"}
    assert prior["omitted_packets_digest"] == metadata["epistemic_omitted_packets_digest"]


def self_model_projection(root: Path):
    from sentientos.longitudinal_self_model import LongitudinalSelfModelOwner
    from tests.test_longitudinal_self_model import record, snapshot as self_model_snapshot

    self_model = LongitudinalSelfModelOwner(root)
    self_model.reconcile(self_model_snapshot(record()), tick_id="tick-1")
    projection = self_model.cognitive_projection(before_tick="tick-2", max_claims=2,
        allowed_predicates=("software_generation", "cognitive_model_identity"))
    assert projection is not None
    return projection


def test_epistemic_only_prior_context_causes_real_owner_cognition(tmp_path: Path) -> None:
    projection, proposition, state = epistemic_projection(tmp_path / "epistemic")
    composition, fake = owner(tmp_path / "cognition")

    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-2",
                                  prior_epistemic_state=projection)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_retrieval_cognition"]
    assert len(cognition) == 1
    assert result.cognition_observation_ids
    request = cognition[0]
    assert request.upstream_evidence["record_ids"] == []
    assert request.upstream_evidence["self_model_projection_present"] is False
    assert request.upstream_evidence["epistemic_projection_id"] == projection.projection_id
    assert request.upstream_evidence["epistemic_projection_digest"] == projection.projection_digest
    assert request.upstream_evidence["epistemic_proposition_ids"] == [proposition.proposition_id]
    assert request.upstream_evidence["epistemic_state_ids"] == [state.state_id]
    assert request.upstream_evidence["epistemic_state_digests"] == [state.state_digest]
    assert request.upstream_evidence["epistemic_generations"] == [state.generation]
    assert request.upstream_evidence["epistemic_evidence_set_digests"] == [state.evidence_set_digest]
    observation = json.loads((composition.observations_root /
                              f"{result.cognition_observation_ids[0]}.json").read_text())
    assert observation["epistemic_projection_present"] is True
    assert observation["epistemic_projection_id"] == projection.projection_id
    assert observation["epistemic_projection_digest"] == projection.projection_digest
    assert observation["epistemic_proposition_ids"] == [proposition.proposition_id]
    assert observation["epistemic_state_ids"] == [state.state_id]
    assert observation["epistemic_state_digests"] == [state.state_digest]
    assert observation["epistemic_generations"] == [state.generation]
    assert observation["epistemic_evidence_set_digests"] == [state.evidence_set_digest]
    assert observation["developmental_projection_present"] is False
    assert observation["self_model_projection_present"] is False
    assert observation["authority"] is False


def test_self_model_and_epistemic_context_run_one_ordinary_condition(tmp_path: Path) -> None:
    epistemic, _, _ = epistemic_projection(tmp_path / "epistemic")
    self_model = self_model_projection(tmp_path / "self-model")
    composition, fake = owner(tmp_path / "cognition", comparison=True)

    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-2",
        prior_self_model=self_model, prior_epistemic_state=epistemic)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_retrieval_cognition"]
    assert len(cognition) == 1
    assert cognition[0].upstream_evidence["record_ids"] == []
    assert cognition[0].upstream_evidence["self_model_projection_id"] == self_model.projection_id
    assert cognition[0].upstream_evidence["epistemic_projection_id"] == epistemic.projection_id
    assert result.changed_cognition_measurement_id is None
    assert not list(composition.experiments.protocols.glob("*.json"))
    assert not list(composition.experiments.runs.glob("*.json"))


def test_all_four_substrates_reach_ordinary_cognition_when_comparison_disabled(tmp_path: Path) -> None:
    first, _ = owner(tmp_path / "cognition")
    written = first.run_tick(snapshot=snapshot(), tick_id="tick-1").written_record_id
    epistemic, _, _ = epistemic_projection(tmp_path / "epistemic")
    self_model = self_model_projection(tmp_path / "self-model")
    restarted, fake = owner(tmp_path / "cognition")

    result = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-2",
        prior_self_model=self_model, prior_epistemic_state=epistemic)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_retrieval_cognition"]
    assert len(cognition) == 1
    assert cognition[0].upstream_evidence["current_fact_ids"]
    assert cognition[0].upstream_evidence["record_ids"] == [written]
    assert cognition[0].upstream_evidence["self_model_projection_id"] == self_model.projection_id
    assert cognition[0].upstream_evidence["epistemic_projection_id"] == epistemic.projection_id
    assert result.changed_cognition_measurement_id is None


def test_history_comparison_keeps_self_model_and_epistemic_bindings_constant(tmp_path: Path) -> None:
    first, _ = owner(tmp_path / "cognition")
    first.run_tick(snapshot=snapshot(), tick_id="tick-1")
    epistemic, _, _ = epistemic_projection(tmp_path / "epistemic")
    self_model = self_model_projection(tmp_path / "self-model")
    restarted, fake = owner(tmp_path / "cognition", comparison=True)

    result = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-2",
        prior_self_model=self_model, prior_epistemic_state=epistemic)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_history_intervention_experiment"
                 and "history_present" in request.linkage]
    assert [request.linkage["history_present"] for request in cognition] == [True, False, True]
    assert {request.upstream_evidence["self_model_projection_digest"] for request in cognition} == {
        self_model.projection_digest}
    assert {request.upstream_evidence["epistemic_projection_digest"] for request in cognition} == {
        epistemic.projection_digest}
    assert result.changed_cognition_measurement_id is not None


def test_tick_n_admitted_developmental_writeback_is_durable_and_bounded(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-n")
    assert result.status == "completed" and result.written_record_id and result.writeback_receipt_id
    assert len(result.selected_fact_ids) == 1
    selected = next(f for f in snapshot().facts if f.fact_id == result.selected_fact_ids[0])
    assert selected.source.kind == "capability_registry"
    assert not result.prior_record_ids and result.same_tick_history_excluded
    assert [r.purpose for r in fake.requests] == ["resident_developmental_interpretation"]
    assert composition.writeback.store.get(result.written_record_id).current_truth is False
    assert composition.writeback.store.get_receipt(result.writeback_receipt_id).storage_verified


def test_restart_recovers_writeback_committed_before_composition_checkpoint(tmp_path: Path) -> None:
    interrupted, _fake = owner(tmp_path)
    save_state = interrupted._save_state

    def interrupt_final_checkpoint(state):
        if state["completed_ticks"]:
            raise ResidentDevelopmentalCognitionError("simulated_after_writeback_before_checkpoint")
        save_state(state)

    interrupted._save_state = interrupt_final_checkpoint
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="simulated_after_writeback_before_checkpoint"):
        interrupted.run_tick(snapshot=snapshot(), tick_id="tick-interrupted")

    durable_records = interrupted.writeback.store.records()
    assert len(durable_records) == 1
    durable_receipts = interrupted.writeback.store.receipts()
    assert len(durable_receipts) == 1

    restarted, fake = owner(tmp_path)
    recovered = restarted._state()
    checkpoint = next(row for row in recovered["completed_ticks"]
                      if row["tick_id"] == "tick-interrupted")
    assert checkpoint["record_id"] == durable_records[0].record_id
    assert checkpoint["receipt_id"] == durable_receipts[0].receipt_id
    assert not any(row.get("tick_id") == "tick-interrupted"
                   for row in recovered["incomplete_ticks"])
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(), tick_id="tick-interrupted")

    later = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-following")
    assert later.prior_record_ids == (durable_records[0].record_id,)
    assert any(request.purpose == "resident_developmental_retrieval_cognition"
               for request in fake.requests)


def test_same_tick_record_is_prohibited_from_retrieval(tmp_path: Path) -> None:
    composition, _ = owner(tmp_path)
    first = composition.run_tick(snapshot=snapshot(), tick_id="tick-n")
    assert first.written_record_id not in first.prior_record_ids
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        composition.run_tick(snapshot=snapshot(), tick_id="tick-n")


def test_restart_tick_n_plus_one_retrieves_prior_history_for_cognition(tmp_path: Path) -> None:
    first, _ = owner(tmp_path)
    written = first.run_tick(snapshot=snapshot(), tick_id="tick-n").written_record_id
    restarted, fake = owner(tmp_path)
    later = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-n-plus-one")
    assert later.prior_record_ids == (written,)
    assert len(later.cognition_observation_ids) == 1
    cognition = [r for r in fake.requests if r.purpose == "resident_developmental_retrieval_cognition"]
    assert cognition[0].upstream_evidence["record_ids"] == [written]
    observation = json.loads(next(restarted.observations_root.glob("*.json")).read_text())
    assert observation["historical_context_only"] and not observation["authority"]
    assert not observation["canonical_explicit_user_retention"]


def test_controlled_with_record_and_withheld_comparison_is_opt_in_and_difference_only(tmp_path: Path) -> None:
    first, _ = owner(tmp_path); first.run_tick(snapshot=snapshot(), tick_id="tick-n")
    restarted, fake = owner(tmp_path, comparison=True)
    later = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-n-plus-one")
    cognition = [r for r in fake.requests if r.purpose == "resident_developmental_history_intervention_experiment" and "history_present" in r.linkage]
    assert [r.linkage["history_present"] for r in cognition] == [True, False, True]
    assert cognition[0].upstream_evidence["snapshot_digest"] == cognition[1].upstream_evidence["snapshot_digest"]
    assert later.changed_cognition_measurement_id
    measured = json.loads((restarted.experiments.runs / f"{later.changed_cognition_measurement_id}.json").read_text())
    assert measured["summary"]["present_vs_withheld_difference_observed"] is True
    assert measured["summary"]["classification"] == "history_presence_associated_stable_difference"


def test_identical_processed_evidence_is_not_reinterpreted(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    composition.run_tick(snapshot=snapshot(), tick_id="tick-2")
    later = composition.run_tick(snapshot=snapshot(), tick_id="tick-3")
    assert later.written_record_id is None
    assert len([r for r in fake.requests if r.purpose == "resident_developmental_interpretation"]) == 2


def test_missing_or_crossed_admission_prevents_history_mutation(tmp_path: Path) -> None:
    composition, _ = owner(tmp_path)
    composition.admission_authority = type("Missing", (), {"issue": lambda *a, **k: None})()
    with pytest.raises((AttributeError, ValueError)):
        composition.run_tick(snapshot=snapshot(), tick_id="tick-missing")
    assert not list((tmp_path / "history" / "records").glob("*.json"))


def test_configuration_is_exact_and_malformed_configuration_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    valid = {"schema":CONFIG_SCHEMA, "enabled":False, "history_root":str(tmp_path / "history"),
             "state_root":str(tmp_path / "state"), "allowed_source_kinds":["capability_registry"],
             "max_selected_facts":1, "max_retrieved_records":2, "comparison_enabled":False}
    path.write_text(json.dumps(valid)); assert load_config(path).enabled is False
    path.write_text(json.dumps({**valid, "personality":"helpful"}))
    with pytest.raises(ResidentDevelopmentalCognitionError, match="shape_invalid"): load_config(path)


def test_sentientosd_preserves_exact_snapshot_and_absent_config_is_inert(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG", raising=False)
    surfaces = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "runtime")
    feedback = surfaces.build_world_state_board(tick_id="2026-01-01T00:00:00+00:00")
    exact = surfaces.current_world_state_snapshot
    assert exact is not None and exact.snapshot_id == feedback["snapshot_id"]
    assert surfaces.run_resident_developmental_cognition(tick_id="2026-01-01T00:00:00+00:00")["status"] == "disabled"

    class Spy:
        seen = None
        def run_tick(self, *, snapshot, tick_id, **_kwargs):
            self.seen = snapshot
            return type("Result", (), {"__dataclass_fields__": {}, "status":"completed"})()
    spy = Spy()
    injected = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "runtime-2",
                                          resident_developmental_owner=spy)  # type: ignore[arg-type]
    injected.build_world_state_board(tick_id="2026-01-02T00:00:00+00:00")
    # The injected owner receives object identity, not a JSON reconstruction.
    try:
        injected.run_resident_developmental_cognition(tick_id="2026-01-02T00:00:00+00:00")
    except TypeError:
        pass
    assert spy.seen is injected.current_world_state_snapshot


def test_sentientosd_composes_explicit_prior_epistemic_projection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SENTIENTOS_EPISTEMIC_STATE_CONFIG", raising=False)
    epistemic=PersistentEpistemicStateOwner(tmp_path/"epistemic",allowed_namespaces=["embodiment"])
    p=make_proposition(namespace="embodiment",subject="body:g1",predicate="healthy",
        object_value=True,polarity="positive",qualifiers={},temporal_scope={"kind":"prior"},
        context_scope={},proposition_class="descriptive")
    epistemic.register_proposition(p)
    epistemic.commit_update(proposition_id=p.proposition_id,expected_predecessor_digest=None,
        stance="unknown",reason="initialization",active_binding_ids=[],correlation_id="prior",tick=1,
        recorded_at="2026-01-01T00:00:00Z")
    class Spy:
        seen = None
        def run_tick(self, **kwargs):
            self.seen = kwargs
            return type("Result", (), {"__dataclass_fields__": {}, "status":"completed"})()
    spy=Spy()
    surfaces=RuntimeMaintenanceSurfaces(tmp_path,runtime_state_root=tmp_path/"runtime-epistemic",
        resident_developmental_owner=spy,epistemic_state_owner=epistemic,
        epistemic_state_config={"status":"configured","max_cognitive_projection_count":1,
                                "cognitive_consumption_enabled":True})  # type: ignore[arg-type]
    tick="2026-01-03T00:00:00+00:00"
    surfaces.build_world_state_board(tick_id=tick)
    feedback=surfaces.run_resident_developmental_cognition(tick_id=tick)
    projection=spy.seen["prior_epistemic_state"]
    assert projection.proposition_ids == (p.proposition_id,)
    assert feedback["epistemic_composition"]["status"] == "composed"
    assert feedback["epistemic_composition"]["authority"] is False


def test_epistemic_runtime_configuration_is_explicit_exact_and_independently_disabled(tmp_path: Path) -> None:
    assert _load_epistemic_state_owner(None) == (None, {"status":"disabled", "cognitive_consumption_enabled":False})
    path=tmp_path/"epistemic-config.json"
    payload={"schema":"sentientos.epistemic_runtime_config:v1","custody_root":str(tmp_path/"custody"),
        "allowed_proposition_namespaces":["embodiment"],"max_cognitive_projection_count":2,
        "cognitive_consumption_enabled":False}
    path.write_text(json.dumps(payload))
    configured, status=_load_epistemic_state_owner(str(path))
    assert configured is not None and status == {"status":"configured","max_cognitive_projection_count":2,
                                                  "cognitive_consumption_enabled":False}
    path.write_text(json.dumps({**payload,"ambient_discovery":True}))
    with pytest.raises(ValueError,match="configuration_invalid"):
        _load_epistemic_state_owner(str(path))



def test_recovered_history_order_uses_intent_not_wall_clock() -> None:
    from types import SimpleNamespace

    first = SimpleNamespace(
        created_at="2026-02-02T00:00:00+00:00",
        correlation_id="tick-first:resident-developmental-writeback",
        record_id="record-first")
    second = SimpleNamespace(
        created_at="2026-01-01T00:00:00+00:00",
        correlation_id="tick-second:resident-developmental-writeback",
        record_id="record-second")
    order = {"tick-first": 0, "tick-second": 1}
    first_key = ResidentDevelopmentalCognitionOwner._recovered_record_order(
        first, completed_order={}, recovery_intent_order=order)
    second_key = ResidentDevelopmentalCognitionOwner._recovered_record_order(
        second, completed_order={}, recovery_intent_order=order)
    assert first_key < second_key


def test_developmental_roots_resolve_aliases_and_exclude_canonical_memory(tmp_path: Path) -> None:
    import os

    from sentientos.canonical_memory import sentientos_memory_dir
    from sentientos.resident_developmental_cognition import _validate_root_separation

    if os.name == "posix":
        history = tmp_path / "history"
        history.mkdir()
        alias = tmp_path / "history-alias"
        alias.symlink_to(history, target_is_directory=True)
        with pytest.raises(ResidentDevelopmentalCognitionError,
                           match="configuration_roots_must_be_separate"):
            _validate_root_separation(history, alias, memory_root=tmp_path / "memory")

    memory = sentientos_memory_dir()
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="configuration_root_overlaps_canonical_memory"):
        _validate_root_separation(memory / "developmental-history", tmp_path / "state",
                                  memory_root=memory)

    # Reject the opposite nesting direction too: a developmental owner must
    # not claim a parent directory that also contains canonical user memory.
    memory_child = tmp_path / "owner-root" / "user-memory"
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="configuration_root_overlaps_canonical_memory"):
        _validate_root_separation(tmp_path / "owner-root", tmp_path / "other-state",
                                  memory_root=memory_child)


def test_cognition_checkpoint_round_trips_through_private_descriptor_custody(tmp_path: Path) -> None:
    import os
    import stat

    if os.name != "posix":
        pytest.skip("cognition checkpoint publication requires POSIX custody")
    cognition, _ = owner(tmp_path)
    state = cognition._state()
    cognition._save_state(state)

    metadata = cognition.state_path.stat()
    root_metadata = cognition.state_path.parent.stat()
    assert stat.S_ISREG(metadata.st_mode)
    assert metadata.st_uid == os.geteuid()
    assert metadata.st_mode & 0o077 == 0
    assert root_metadata.st_uid == os.geteuid()
    assert root_metadata.st_mode & 0o022 == 0
    assert cognition._state() == state


def test_cognition_checkpoint_rejects_replaced_symlink_root(tmp_path: Path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("no-follow checkpoint publication requires POSIX")
    from sentientos.resident_developmental_cognition import _replace_cognition_state

    target = tmp_path / "external"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="composition_state_root_invalid"):
        _replace_cognition_state(alias / "composition_state.json", {"state": "bounded"})
    assert list(target.iterdir()) == []


def test_concurrent_developmental_ticks_cannot_replay_one_tick(tmp_path: Path) -> None:
    import os
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    if os.name != "posix":
        pytest.skip("POSIX cognition tick lock is required")
    first, _ = owner(tmp_path)
    second, _ = owner(tmp_path)
    tick_snapshot = WorldStateBoardBuilder().build([])
    barrier = Barrier(2)

    def run(owner_instance):
        barrier.wait()
        return owner_instance.run_tick(snapshot=tick_snapshot, tick_id="one-shared-tick")

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(run, first)
        right = pool.submit(run, second)
        results = []
        for future in (left, right):
            try:
                results.append(future.result())
            except ResidentDevelopmentalCognitionError as exc:
                results.append(str(exc))

    assert sum(getattr(result, "status", None) == "completed" for result in results) == 1
    assert results.count("tick_already_completed") == 1
