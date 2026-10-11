from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from sentientos.codex_task_authority_admission import (
    RESIDENT_EPISTEMIC_STATE_MUTATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
)
from sentientos.persistent_epistemic_state import (
    PersistentEpistemicStateOwner, make_epistemic_update_candidate, make_proposition,
)
from sentientos.embodiment_self_observation import EmbodimentEvidenceOwner, EmbodimentObservation
from sentientos.resident_epistemic_development import (
    MAX_BINDINGS_PER_TICK, EpistemicDevelopmentConfig, EpistemicDevelopmentError,
    EpistemicDevelopmentRule, ResidentEpistemicDevelopmentRuntime,
)
from sentientos.resident_epistemic_state_mutation import (
    STATE_UPDATE_EFFECTS, ResidentEpistemicStateMutationController,
)
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from sentientos.world_state_board import WorldStateBoardBuilder
from sentientosd import _quarantine_custody_world_state_record

pytestmark = pytest.mark.no_legacy_skip


NOW = "2026-09-28T12:00:00+00:00"


def fixture(tmp_path, *, relation="supports", disposition="nominal"):
    owner = PersistentEpistemicStateOwner(tmp_path / "epistemics", allowed_namespaces=("operator",))
    proposition = make_proposition(namespace="operator", subject="service-a", predicate="is_nominal",
        object_value=True, polarity="positive", qualifiers={}, temporal_scope={}, context_scope={},
        proposition_class="environmental")
    owner.register_proposition(proposition)
    ledger = AdmissionLedger(tmp_path / "admissions.json")
    definitions = {RESIDENT_EPISTEMIC_STATE_MUTATION: RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION}
    def current():
        admissions, revocations = ledger.load()
        return max([x.issued_sequence for x in admissions] + [x.sequence for x in revocations], default=1)
    controller = ResidentEpistemicStateMutationController(owner=owner,
        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
        current_sequence=current, receipt_root=tmp_path / "receipts")
    rule = EpistemicDevelopmentRule("service-nominal", proposition.proposition_id,
        proposition.proposition_digest, {"source_kind": "runtime_supervisor", "subject_id": "service-a",
        "stage": "observation", "disposition": disposition}, relation, "unknown_dependency", "recorded")
    config = EpistemicDevelopmentConfig(True, 8, 4, (rule,), ("operator",))
    runtime = ResidentEpistemicDevelopmentRuntime(config=config, owner=owner,
        mutation_controller=controller,
        admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
        admission_ledger=ledger)
    return owner, proposition, ledger, runtime


def snapshot(disposition="nominal", *, source_id="supervisor-a"):
    return WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([{
        "source_kind": "runtime_supervisor", "source_id": source_id,
        "subject_kind": "service", "subject_id": "service-a", "stage": "observation",
        "disposition": disposition, "observed_at": NOW, "payload": {"check": disposition},
    }])


def test_one_tick_evidence_and_state_mutation_uses_distinct_admissions(tmp_path):
    owner, proposition, ledger, runtime = fixture(tmp_path)
    result = runtime.process_snapshot(snapshot(), tick=10, recorded_at=NOW)
    state = owner.current_state(proposition.proposition_id)
    admissions, _ = ledger.load()
    assert result.status == "state_advanced" and result.next_tick_only and not result.authority
    assert state is not None and state.stance == "provisionally_supported" and state.generation == 0
    assert len(admissions) == 2 and admissions[0].admission_id != admissions[1].admission_id
    assert set(admissions[0].effects).isdisjoint(set(admissions[1].effects) - {"exact_epistemic_proposition_read", "epistemic_mutation_receipt_write", "read_only_epistemic_post_mutation_verification"})
    assert state.evidence_set_digest


def test_quarantine_custody_status_cannot_become_epistemic_support(tmp_path):
    from sentientos.integrity_quarantine import QUARANTINE_PATH

    target = tmp_path / QUARANTINE_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"not-json")
    record = _quarantine_custody_world_state_record(tmp_path, observed_at=NOW)
    board = WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([record])
    _, proposition, _, runtime = fixture(tmp_path)
    configured = replace(runtime.config.rules[0], selector={
        "source_kind": "quarantine",
        "subject_kind": "quarantine_custody_observation",
        "stage": "observation",
        "disposition": "custody_invalid",
    }, evidence_relation="supports", dependency_kind="independently_sourced_observation",
       reliability_posture="verified", independence_basis="configured-test-source")
    assert configured.proposition_id == proposition.proposition_id
    _proof, binding = ResidentEpistemicDevelopmentRuntime._adapt(
        board, board.facts[0], configured)
    assert binding.evidence_relation == "contextualizes"
    assert binding.dependency_kind == "unknown_dependency"
    assert binding.dependency_group is None
    assert binding.freshness == "unknown"
    assert binding.reliability_posture == "quarantine_custody_status_context_only"


def test_incomplete_mutation_recovery_is_reported_without_new_admission(tmp_path):
    owner, proposition, ledger, runtime = fixture(tmp_path)
    candidate = make_epistemic_update_candidate(
        proposition_id=proposition.proposition_id, predecessor_state_digest=None,
        proposed_stance="unknown", evidence_binding_ids=(), reason="initialization",
        rationale="interrupted state intent", uncertainty="unknown", model_id="fixture")
    operation_id = "interrupted-state-update"
    admission = runtime._issue(admission_id="interrupted-state-admission",
        effects=STATE_UPDATE_EFFECTS, subject_id=candidate.candidate_id,
        configuration_digest=runtime.controller.state_configuration_digest(
            candidate=candidate, operation_id=operation_id),
        provenance="unexecuted recovery fixture")
    runtime.controller._write_state_intent(candidate=candidate, admission=admission,
        operation_id=operation_id, correlation_id="interrupted-state-workflow")

    result = runtime.process_snapshot(snapshot(), tick=11, recorded_at=NOW)

    admissions, _ = ledger.load()
    assert result.status == "degraded"
    assert result.recovery_status == "incomplete"
    assert result.pending_state_intent_count == 1
    assert len(admissions) == 1
    assert owner.current_state(proposition.proposition_id) is None


def test_two_tick_prior_firewall_and_contradiction_progression(tmp_path):
    owner, proposition, _, runtime = fixture(tmp_path)
    assert owner.cognitive_projection(max_states=4) is None  # cognition slot for tick N
    first = runtime.process_snapshot(snapshot(), tick=10, recorded_at=NOW)
    projected = owner.cognitive_projection(max_states=4)  # captured at tick N+1
    assert projected is not None and projected.source_tick == 10
    assert projected.state_ids == first.successor_state_ids and projected.generations == (0,)
    # A second exact configured rule supplies contradiction; no prose is interpreted.
    old = runtime.config.rules[0]
    contradict = replace(old, rule_id="service-failed", evidence_relation="contradicts",
        selector={**old.selector, "disposition": "failed"})
    runtime.config = replace(runtime.config, rules=(old, contradict))
    second = runtime.process_snapshot(snapshot("failed", source_id="supervisor-b"), tick=11, recorded_at="2026-09-28T12:01:00+00:00")
    state = owner.current_state(proposition.proposition_id)
    assert second.status == "state_advanced" and state is not None
    assert state.stance == "contested" and state.generation == 1
    later = owner.cognitive_projection(max_states=4)
    assert later is not None and later.source_tick == 11 and later.generations == (1,)


def test_restart_between_evidence_and_state_deduplicates_and_continues(tmp_path, monkeypatch):
    owner, proposition, ledger, runtime = fixture(tmp_path)
    original = runtime.controller.commit_update_candidate
    monkeypatch.setattr(runtime.controller, "commit_update_candidate", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("stop")))
    with pytest.raises(RuntimeError, match="stop"):
        runtime.process_snapshot(snapshot(), tick=10, recorded_at=NOW)
    assert len(owner.bindings(proposition.proposition_id)) == 1 and owner.current_state(proposition.proposition_id) is None
    monkeypatch.setattr(runtime.controller, "commit_update_candidate", original)
    result = runtime.process_snapshot(snapshot(), tick=11, recorded_at="2026-09-28T12:01:00+00:00")
    admissions, _ = ledger.load()
    assert len(owner.bindings(proposition.proposition_id)) == 1
    assert result.new_binding_count == 0 and result.updated_proposition_count == 1
    assert len(admissions) == 3  # old E, unconsumed old S, fresh S; E is not replayed


def test_configuration_identity_and_bounds_fail_before_mutation(tmp_path):
    owner, proposition, ledger, runtime = fixture(tmp_path)
    with pytest.raises(EpistemicDevelopmentError, match="digest"):
        ResidentEpistemicDevelopmentRuntime(config=replace(runtime.config,
            rules=(replace(runtime.config.rules[0], proposition_digest="sha256:wrong"),)), owner=owner,
            mutation_controller=runtime.controller, admission_authority=runtime.authority, admission_ledger=ledger)
    with pytest.raises(EpistemicDevelopmentError, match="bound"):
        ResidentEpistemicDevelopmentRuntime(config=replace(runtime.config,
            max_new_bindings_per_tick=MAX_BINDINGS_PER_TICK + 1), owner=owner,
            mutation_controller=runtime.controller, admission_authority=runtime.authority, admission_ledger=ledger)
    assert owner.current_state(proposition.proposition_id) is None and not owner.bindings(proposition.proposition_id)


def test_snapshot_tamper_fails_before_admission(tmp_path):
    owner, proposition, ledger, runtime = fixture(tmp_path)
    bad = replace(snapshot(), digest="tampered")
    with pytest.raises(EpistemicDevelopmentError, match="snapshot"):
        runtime.process_snapshot(bad, tick=10, recorded_at=NOW)
    assert not ledger.load()[0] and not owner.bindings(proposition.proposition_id)


def test_unverified_embodiment_assertion_stays_contextual_and_unknown(tmp_path):
    owner, proposition, _, runtime = fixture(tmp_path)
    item = EmbodimentObservation(
        "caller:sensor", "fixture:v1", "sha256:" + "e" * 64, NOW,
        "production", "fresh", "production", "sensor_observation", "camera", "sensor",
        {"present": True, "healthy": True},
    )
    board = WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build(
        EmbodimentEvidenceOwner((item,)).world_state_records())
    fact = board.facts[0]
    assert fact.observed_at is None and fact.source.staleness == "unknown"
    rule = replace(runtime.config.rules[0], selector={
        "source_kind": "embodiment", "subject_kind": "sensor_observation",
        "subject_id": "camera", "stage": "observation", "disposition": "recorded",
    }, evidence_relation="supports", dependency_kind="independently_sourced_observation",
       independence_basis="sensor-owner")
    _, binding = runtime._adapt(board, fact, rule)
    assert binding.evidence_relation == "contextualizes"
    assert binding.dependency_kind == "unknown_dependency"
    assert binding.dependency_group is None
    assert binding.freshness == "unknown"



def test_recent_software_launch_is_historical_context_not_current_evidence() -> None:
    record = {
        "source_kind": "runtime_supervisor",
        "source_id": "resident-running-software:launch",
        "schema_version": "runtime.test.v1",
        "subject_id": "process-1",
        "subject_kind": "observed_running_software_generation",
        "stage": "observation",
        "disposition": "observed",
        "evidence_strength": "resident_launch_provenance",
        "observed_at": NOW,
        "payload": {
            "running_software_generation_observed": "sha256:" + "a" * 64,
            "software_generation": "sha256:" + "a" * 64,
            "startup_timestamp": NOW,
            "loaded_code_identity_posture": "not_independently_attested",
            "authority": False,
            "effect_proven": False,
        },
    }
    snapshot = WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([record])
    fact = snapshot.facts[0]
    rule = EpistemicDevelopmentRule(
        "rule-launch", "proposition-launch", "a" * 64, {}, "supports",
        "independently_sourced_observation", "source_observation")

    _proof, binding = ResidentEpistemicDevelopmentRuntime._adapt(snapshot, fact, rule)

    assert binding.observation_time == NOW
    assert binding.freshness == "unknown"
    assert binding.evidence_relation == "contextualizes"
    assert binding.dependency_kind == "unknown_dependency"



def test_running_model_observation_preserves_observation_time_not_load_time() -> None:
    record = {
        "source_kind": "runtime_supervisor", "source_id": "resident-serving:session-a:tick-N",
        "schema_version": "runtime.test.v1", "subject_id": "session-a",
        "subject_kind": "observed_running_model", "stage": "observation",
        "disposition": "observed", "evidence_strength": "serving_session_observation",
        "observed_at": NOW,
        "payload": {
            "running_model_identity_observed": {"model_id": "model-a"},
            "serving_session_id": "session-a",
            "event_time_posture": "serving_session_observation_time_not_model_load_time",
            "authority": False, "effect_proven": False,
        },
    }
    snapshot = WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([record])
    rule = EpistemicDevelopmentRule(
        "rule-model", "proposition-model", "a" * 64, {}, "supports",
        "independently_sourced_observation", "serving_owner_observation")
    _proof, binding = ResidentEpistemicDevelopmentRuntime._adapt(snapshot, snapshot.facts[0], rule)
    assert binding.observation_time == NOW
    assert binding.freshness == "current"
    assert binding.evidence_relation == "supports"


def test_running_model_without_recorded_observation_time_is_not_current() -> None:
    record = {
        "source_kind": "runtime_supervisor", "source_id": "resident-serving:session-a:unknown",
        "schema_version": "runtime.test.v1", "subject_id": "session-a",
        "subject_kind": "observed_running_model", "stage": "observation",
        "disposition": "observed", "evidence_strength": "serving_session_observation",
        "observed_at": None,
        "payload": {
            "running_model_identity_observed": {"model_id": "model-a"},
            "serving_session_id": "session-a",
            "event_time_posture": "serving_session_time_not_retained",
            "authority": False, "effect_proven": False,
        },
    }
    snapshot = WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([record])
    rule = EpistemicDevelopmentRule(
        "rule-model", "proposition-model", "a" * 64, {}, "supports",
        "independently_sourced_observation", "serving_owner_observation")
    _proof, binding = ResidentEpistemicDevelopmentRuntime._adapt(snapshot, snapshot.facts[0], rule)
    assert binding.observation_time == "undated"
    assert binding.freshness == "unknown"
    assert binding.evidence_relation == "contextualizes"


def test_transition_retention_marker_is_undated_context_not_current_support() -> None:
    record = {
        "source_kind": "runtime_supervisor", "source_id": "software-transition-retention:head",
        "schema_version": "runtime.test.v1", "subject_id": "transition-a",
        "subject_kind": "software_generation_transition_history_retention",
        "stage": "observation", "disposition": "bounded_tail",
        "evidence_strength": "verified_journal_tail_with_omitted_prefix",
        "observed_at": None,
        "payload": {
            "omitted_event_count": 12, "journal_head_digest": "head",
            "event_time_posture": "journal_retention_is_not_a_transition_event",
            "authority": False, "effect_proven": False,
        },
    }
    snapshot = WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([record])
    rule = EpistemicDevelopmentRule(
        "rule-retention", "proposition-retention", "a" * 64, {}, "supports",
        "independently_sourced_observation", "software_transition_owner")
    _proof, binding = ResidentEpistemicDevelopmentRuntime._adapt(snapshot, snapshot.facts[0], rule)
    assert binding.observation_time == "undated"
    assert binding.freshness == "unknown"
    assert binding.evidence_relation == "contextualizes"
    assert binding.dependency_kind == "unknown_dependency"


def test_owner_introspection_snapshot_chain_survives_epistemic_binding(tmp_path):
    owner, proposition, _ledger, runtime = fixture(tmp_path)
    record = {
        "source_kind": "owner_introspection",
        "source_id": "owner-projection-fixture",
        "subject_kind": "model_serving",
        "subject_id": "serving-owner",
        "stage": "observation",
        "disposition": "owner_reported",
        "observed_at": NOW,
        "payload": {
            "introspection_snapshot_id": "causal-introspection-fixture",
            "introspection_snapshot_digest": "a" * 64,
            "introspection_snapshot_generation": 7,
            "introspection_snapshot_predecessor_digest": "b" * 64,
            "introspection_capture_tick": NOW,
            "introspection_snapshot_completion_posture": "complete",
        },
    }
    board = WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([record])
    rule = EpistemicDevelopmentRule("introspection-lineage", proposition.proposition_id,
        proposition.proposition_digest, {}, "contextualizes", "unknown_dependency",
        "historical_owner_introspection")
    proof, binding = runtime._adapt(board, board.facts[0], rule)
    provenance = json.loads(proof.provenance_id)
    assert provenance["causal_introspection_snapshot_lineage"] == {
        "introspection_snapshot_id": "causal-introspection-fixture",
        "introspection_snapshot_digest": "a" * 64,
        "introspection_snapshot_generation": 7,
        "introspection_snapshot_predecessor_digest": "b" * 64,
        "introspection_capture_tick": NOW,
        "introspection_snapshot_completion_posture": "complete",
    }
    assert binding.source_digest == board.facts[0].source.digest
    assert binding.freshness == "current"


def test_introspection_recovery_failure_is_contextual_and_undated(tmp_path):
    _owner, proposition, _ledger, runtime = fixture(tmp_path)
    record = {
        "source_kind": "owner_introspection",
        "source_id": "causal-introspection:recovery-unavailable:RuntimeError",
        "subject_kind": "causal_introspection_recovery",
        "subject_id": "causal-introspection-runtime",
        "stage": "observation",
        "disposition": "incomplete",
        "evidence_strength": "recovery_error_class_only",
        "payload": {"recovery_posture": "committed_snapshot_history_unavailable",
            "error_class": "RuntimeError", "authority": False, "current_truth": False},
        "observed_at": None, "retrieved_at": NOW, "staleness": "unknown",
        "effect_claimed": False, "effect_proven": False,
    }
    board = WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([record])
    rule = EpistemicDevelopmentRule("introspection-recovery", proposition.proposition_id,
        proposition.proposition_digest, {}, "supports", "unknown_dependency", "owner_failure")
    proof, binding = runtime._adapt(board, board.facts[0], rule)
    provenance = json.loads(proof.provenance_id)

    assert provenance["event_time_posture"] == "historical_or_unknown"
    assert binding.observation_time == "undated"
    assert binding.freshness == "unknown"
    assert binding.evidence_relation == "contextualizes"
    assert binding.dependency_kind == "unknown_dependency"
    assert binding.dependency_group is None


def test_introspection_provenance_survives_epistemic_receipt_recovery(tmp_path):
    owner, proposition, ledger, runtime = fixture(tmp_path)
    rule = EpistemicDevelopmentRule("introspection-chain", proposition.proposition_id,
        proposition.proposition_digest, {
            "source_kind": "owner_introspection",
            "subject_kind": "model_serving",
            "stage": "observation",
            "disposition": "owner_reported",
        }, "supports", "unknown_dependency", "owner_introspection")
    runtime.config = replace(runtime.config, rules=(rule,))
    record = {
        "source_kind": "owner_introspection", "source_id": "owner-projection-restart",
        "subject_kind": "model_serving", "subject_id": "serving-owner",
        "stage": "observation", "disposition": "owner_reported", "observed_at": NOW,
        "payload": {
            "introspection_snapshot_id": "causal-introspection-restart",
            "introspection_snapshot_digest": "a" * 64,
            "introspection_snapshot_generation": 3,
            "introspection_snapshot_predecessor_digest": "b" * 64,
            "introspection_capture_tick": NOW,
            "introspection_snapshot_completion_posture": "complete",
        },
    }
    board = WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([record])
    feedback = runtime.process_snapshot(board, tick=21, recorded_at=NOW)
    assert feedback.new_binding_count == 1
    assert feedback.state_receipt_ids

    admissions, _revocations = ledger.load()
    evidence_admission = next(item for item in admissions
        if item.admission_id.startswith("epistemic-E-21-"))
    admission_provenance = json.loads(evidence_admission.provenance)
    expected_lineage = admission_provenance["causal_introspection_snapshot_lineage"]

    recovered_owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemics", allowed_namespaces=("operator",))
    definitions = {RESIDENT_EPISTEMIC_STATE_MUTATION:
        RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION}
    def current():
        stored_admissions, stored_revocations = ledger.load()
        return max([item.issued_sequence for item in stored_admissions]
            + [item.sequence for item in stored_revocations], default=1)
    recovered_controller = ResidentEpistemicStateMutationController(
        owner=recovered_owner,
        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
        current_sequence=current, receipt_root=tmp_path / "receipts")
    recovered_runtime = ResidentEpistemicDevelopmentRuntime(
        config=replace(runtime.config, rules=(rule,)), owner=recovered_owner,
        mutation_controller=recovered_controller,
        admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
        admission_ledger=ledger)
    recovered = recovered_controller.verify_receipts()

    assert recovered["status"] == "verified"
    assert len(recovered_owner.bindings(proposition.proposition_id)) == 1
    recovered_admissions, _ = ledger.load()
    recovered_evidence_admission = next(item for item in recovered_admissions
        if item.admission_id == evidence_admission.admission_id)
    assert json.loads(recovered_evidence_admission.provenance)[
        "causal_introspection_snapshot_lineage"] == expected_lineage


def test_parent_lifecycle_receipt_time_stays_historical_context(tmp_path):
    owner, proposition, ledger, runtime = fixture(tmp_path)
    event_time = "2026-09-20T09:30:00+00:00"
    parent_payload = {
        "schema_version": "sentientos.parent_lifecycle_observation:v1",
        "event_time": event_time,
        "event_time_posture": "verified_historical_receipt_time",
        "freshness": "unknown",
        "historical_only": True,
        "current_truth": False,
        "effect_authority": False,
        "effect_proven": False,
        "current_running_generation_proven": False,
    }
    world = WorldStateBoardBuilder(
        clock=lambda: datetime.fromisoformat(NOW)).build([{
            "source_kind": "runtime_supervisor",
            "source_id": "resident-parent:fixture",
            "subject_id": "service-a",
            "subject_kind": "resident_parent_lifecycle_history",
            "stage": "observation",
            "disposition": "nominal",
            "observed_at": NOW,
            "staleness": "unknown",
            "payload": parent_payload,
        }])
    proof, binding = runtime._adapt(world, world.facts[0], runtime.config.rules[0])
    assert proof.recorded_at == event_time
    assert binding.observation_time == event_time
    assert binding.evidence_relation == "contextualizes"
    assert binding.dependency_kind == "unknown_dependency"
    assert binding.freshness == "unknown"
