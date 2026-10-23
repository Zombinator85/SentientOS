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
from sentientos.integrity_incident import build_incident, write_incident
from sentientos.integrity_quarantine import QuarantineState, save_state
from sentientosd import (
    _integrity_controller_world_state_record,
    _quarantine_custody_world_state_record,
    _quarantine_incident_custody_world_state_record,
)

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


def snapshot(disposition="nominal", *, source_id="supervisor-a", observed_at=NOW):
    return WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([{
        "source_kind": "runtime_supervisor", "source_id": source_id,
        "subject_kind": "service", "subject_id": "service-a", "stage": "observation",
        "disposition": disposition, "observed_at": observed_at,
        "payload": {"check": disposition},
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


def test_existing_bindings_do_not_starve_new_evidence_and_omissions_are_stable(tmp_path):
    owner, proposition, _ledger, runtime = fixture(tmp_path)
    runtime.config = replace(runtime.config, max_new_bindings_per_tick=1)
    records = [{
        "source_kind": "runtime_supervisor", "source_id": source_id,
        "subject_kind": "service", "subject_id": "service-a",
        "stage": "observation", "disposition": "nominal",
        "observed_at": NOW, "payload": {"check": "nominal"},
    } for source_id in ("supervisor-a", "supervisor-b", "supervisor-c", "supervisor-d")]
    builder = WorldStateBoardBuilder(
        clock=lambda: datetime.fromisoformat(NOW))
    combined = builder.build(records)
    first_fact = min(combined.facts, key=lambda fact: fact.fact_id)
    initial_record = next(record for record in records
        if record["source_id"] == first_fact.source.source_id)
    initial = builder.build([initial_record])
    first = runtime.process_snapshot(initial, tick=10, recorded_at=NOW)
    assert first.new_binding_count == 1
    first_binding = owner.bindings(proposition.proposition_id)[0]

    second = runtime.process_snapshot(combined, tick=11, recorded_at=NOW)
    assert second.status == "bounded_partial"
    assert second.new_binding_count == 1
    assert len(second.omitted_binding_ids) == 2
    assert second.omitted_binding_ids == tuple(sorted(second.omitted_binding_ids))
    assert len(owner.bindings(proposition.proposition_id)) == 2
    assert first_binding.binding_id not in second.omitted_binding_ids

    third = runtime.process_snapshot(combined, tick=12, recorded_at=NOW)
    assert third.new_binding_count == 1
    assert len(third.omitted_binding_ids) == 1
    assert len(owner.bindings(proposition.proposition_id)) == 3

    fourth = runtime.process_snapshot(combined, tick=13, recorded_at=NOW)
    assert fourth.new_binding_count == 1
    assert fourth.omitted_binding_ids == ()
    assert fourth.status == "state_advanced"
    assert len(owner.bindings(proposition.proposition_id)) == 4


def test_settled_propositions_do_not_starve_pending_state_updates(tmp_path):
    owner, first_proposition, _ledger, runtime = fixture(tmp_path)
    additional = []
    for subject in ("service-b", "service-c"):
        proposition = make_proposition(namespace="operator", subject=subject,
            predicate="is_nominal", object_value=True, polarity="positive",
            qualifiers={}, temporal_scope={}, context_scope={},
            proposition_class="environmental")
        owner.register_proposition(proposition)
        additional.append(proposition)
    propositions = sorted((first_proposition, *additional),
        key=lambda item: item.proposition_id)
    rules = tuple(EpistemicDevelopmentRule(
        f"rule-{index}", proposition.proposition_id,
        proposition.proposition_digest, {
            "source_kind": "runtime_supervisor",
            "source_id": f"supervisor-{index}",
            "stage": "observation", "disposition": "nominal",
        }, "supports", "unknown_dependency", "recorded")
        for index, proposition in enumerate(propositions))
    runtime.config = replace(runtime.config, rules=rules,
        max_new_bindings_per_tick=8, max_updated_propositions_per_tick=1)
    records = [{
        "source_kind": "runtime_supervisor",
        "source_id": f"supervisor-{index}",
        "subject_kind": "service", "subject_id": proposition.subject,
        "stage": "observation", "disposition": "nominal",
        "observed_at": NOW, "payload": {"check": "nominal"},
    } for index, proposition in enumerate(propositions)]
    builder = WorldStateBoardBuilder(
        clock=lambda: datetime.fromisoformat(NOW))
    first = runtime.process_snapshot(builder.build(records[:1]),
        tick=20, recorded_at=NOW)
    assert first.updated_proposition_count == 1

    second = runtime.process_snapshot(builder.build(records),
        tick=21, recorded_at=NOW)
    assert second.updated_proposition_count == 1
    assert len(second.omitted_proposition_ids) == 1
    settled_id = propositions[0].proposition_id
    assert settled_id not in second.omitted_proposition_ids
    assert owner.current_state(propositions[1].proposition_id) is not None
    assert owner.current_state(propositions[2].proposition_id) is None

    third = runtime.process_snapshot(builder.build(records),
        tick=22, recorded_at=NOW)
    assert third.updated_proposition_count == 1
    assert third.omitted_proposition_ids == ()
    assert owner.current_state(propositions[2].proposition_id) is not None


def test_equal_tick_updates_remain_fair_after_owner_restart(tmp_path):
    owner, initial, ledger, runtime = fixture(tmp_path)
    other = make_proposition(namespace="operator", subject="service-b",
        predicate="is_nominal", object_value=True, polarity="positive",
        qualifiers={}, temporal_scope={}, context_scope={},
        proposition_class="environmental")
    owner.register_proposition(other)
    early, later = sorted((initial, other), key=lambda item: item.proposition_id)
    rules = tuple(EpistemicDevelopmentRule(
        f"rule-{proposition.subject}", proposition.proposition_id,
        proposition.proposition_digest, {
            "source_kind": "runtime_supervisor",
            "subject_id": proposition.subject,
            "stage": "observation", "disposition": "nominal",
        }, "supports", "unknown_dependency", "recorded")
        for proposition in (early, later))
    runtime.config = replace(runtime.config, rules=rules,
        max_new_bindings_per_tick=8, max_updated_propositions_per_tick=2)

    def record(proposition, source_id, sample):
        return {
            "source_kind": "runtime_supervisor", "source_id": source_id,
            "subject_kind": "service", "subject_id": proposition.subject,
            "stage": "observation", "disposition": "nominal",
            "observed_at": NOW, "payload": {"check": "nominal", "sample": sample},
        }

    early_seed_records = [
        record(early, f"early-seed-{sample}", sample)
        for sample in range(5)]
    early_first = record(early, "early-1", 10)
    later_first = record(later, "later-1", 1)
    early_second = record(early, "early-2", 2)
    later_second = record(later, "later-2", 2)
    builder = WorldStateBoardBuilder(
        clock=lambda: datetime.fromisoformat(NOW))
    first = runtime.process_snapshot(
        builder.build([*early_seed_records, early_first, later_first]),
        tick=10, recorded_at=NOW)
    assert first.updated_proposition_count == 2
    assert first.omitted_proposition_ids == ()
    assert len(owner.active_binding_ids(early.proposition_id)) == 6
    assert len(owner.active_binding_ids(later.proposition_id)) == 1
    later_bindings_before_omission = set(
        owner.active_binding_ids(later.proposition_id))

    runtime.config = replace(runtime.config,
        max_updated_propositions_per_tick=1)
    second = runtime.process_snapshot(
        builder.build([
            *early_seed_records, early_first, early_second,
            later_first, later_second]),
        tick=10, recorded_at=NOW)
    assert second.status == "bounded_partial"
    assert second.omitted_proposition_ids == (later.proposition_id,)
    early_state = owner.current_state(early.proposition_id)
    later_state = owner.current_state(later.proposition_id)
    assert early_state is not None and early_state.generation == 1
    assert later_state is not None and later_state.generation == 0
    assert len(owner.active_binding_ids(early.proposition_id)) == 7
    assert set(owner.active_binding_ids(later.proposition_id)) == later_bindings_before_omission

    recovered_owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemics", allowed_namespaces=("operator",))
    recovered_controller = ResidentEpistemicStateMutationController(
        owner=recovered_owner,
        admission_verifier=runtime.controller.admission_verifier,
        current_sequence=runtime.controller.current_sequence,
        receipt_root=runtime.controller.receipt_root)
    recovered_runtime = ResidentEpistemicDevelopmentRuntime(
        config=runtime.config, owner=recovered_owner,
        mutation_controller=recovered_controller,
        admission_authority=runtime.authority, admission_ledger=ledger)
    assert len(recovered_owner.active_binding_ids(early.proposition_id)) == 7
    assert set(recovered_owner.active_binding_ids(later.proposition_id)) == later_bindings_before_omission
    third = recovered_runtime.process_snapshot(
        builder.build([
            *early_seed_records, early_first, early_second,
            record(early, "early-3", 30), later_first, later_second,
            record(later, "later-3", 3),
        ]), tick=10, recorded_at=NOW)
    assert third.status == "bounded_partial"
    assert third.updated_proposition_count == 1
    assert third.omitted_proposition_ids == (early.proposition_id,)
    early_state = recovered_owner.current_state(early.proposition_id)
    later_state = recovered_owner.current_state(later.proposition_id)
    assert early_state is not None and early_state.generation == 1
    assert later_state is not None and later_state.generation == 1



def test_generation_is_not_served_until_committed_receipt_recovers(tmp_path, monkeypatch):
    owner, proposition, ledger, runtime = fixture(tmp_path)
    original_write = runtime.controller._write_receipt

    def interrupt_state_receipt(stage, receipt):
        if stage == "state":
            raise OSError("simulated state receipt interruption")
        return original_write(stage, receipt)

    monkeypatch.setattr(runtime.controller, "_write_receipt", interrupt_state_receipt)
    with pytest.raises(OSError, match="simulated state receipt interruption"):
        runtime.process_snapshot(snapshot(), tick=10, recorded_at=NOW)

    committed_state = owner.current_state(proposition.proposition_id)
    assert committed_state is not None and committed_state.generation == 0
    state_receipt_dir = runtime.controller.receipt_root / "receipts" / "state"
    assert list(state_receipt_dir.glob("*.json")) == []
    admissions_before_recovery, _ = ledger.load()
    assert len(admissions_before_recovery) == 2

    recovered_owner = PersistentEpistemicStateOwner(
        tmp_path / "epistemics", allowed_namespaces=("operator",))
    recovered_controller = ResidentEpistemicStateMutationController(
        owner=recovered_owner,
        admission_verifier=runtime.controller.admission_verifier,
        current_sequence=runtime.controller.current_sequence,
        receipt_root=runtime.controller.receipt_root)
    assert recovered_controller.recovery_status["status"] == "verified"
    assert recovered_controller.recovery_status["pending_state_intent_count"] == 0
    assert recovered_controller.recovery_status["recovered_receipt_count"] == 2
    assert len(list(state_receipt_dir.glob("*.json"))) == 1

    recovered_runtime = ResidentEpistemicDevelopmentRuntime(
        config=runtime.config, owner=recovered_owner,
        mutation_controller=recovered_controller,
        admission_authority=runtime.authority, admission_ledger=ledger)
    retry = recovered_runtime.process_snapshot(snapshot(), tick=10, recorded_at=NOW)

    assert retry.recovery_status == "verified"
    assert retry.recovered_receipt_count == 2
    assert retry.status == "no_matching_evidence"
    assert retry.state_receipt_ids == ()
    assert retry.generations == ()
    assert recovered_owner.current_state(proposition.proposition_id).generation == 0
    admissions_after_recovery, _ = ledger.load()
    assert len(admissions_after_recovery) == 2



def test_unknown_offset_historical_event_time_stays_unresolved():
    from sentientos.resident_epistemic_development import _latest_historical_event_time

    assert _latest_historical_event_time([
        "2026-01-01T00:00:00-00:00", "2026-01-01T00:00:01+00:00"]) is None


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


def test_attestation_verifier_failure_cannot_become_epistemic_support(tmp_path):
    record = {
        "source_kind": "audit_trust",
        "source_id": "attestation-snapshot-verification:resident-daemon",
        "schema_version": "sentientos.attestation_snapshot_verification_observation:v1",
        "subject_id": "configured-attestation-snapshot-signature-chain",
        "subject_kind": "attestation_snapshot_verification_observation",
        "stage": "observation", "disposition": "degraded",
        "evidence_strength": "owner_observed_signature_chain_verification_failure",
        "observed_at": NOW, "effect_claimed": False, "effect_proven": False,
        "payload": {
            "observation_schema": "sentientos.attestation_snapshot_verification_observation:v1",
            "source_owner": "sentientos.attestation_snapshot.verify_recent_snapshots",
            "event_time_posture": "daemon_tick_point_observation_of_bounded_verifier",
            "verification_result": "fail", "verification_ok": False,
            "verification_reason": "signature_invalid", "checked_signature_count": 0,
            "cause_unknown": True,
            "attack_established": False, "hostile_activity_established": False,
            "compromise_established": False, "independent_signature": False,
            "effect_proven": False, "effect_authority": False,
            "authority": False, "current_truth": False, "read_only": True,
        },
    }
    board = WorldStateBoardBuilder(
        clock=lambda: datetime.fromisoformat(NOW)).build([record])
    _, proposition, _, runtime = fixture(tmp_path)
    configured = replace(runtime.config.rules[0], selector={
        "source_kind": "audit_trust",
        "subject_kind": "attestation_snapshot_verification_observation",
        "stage": "observation", "disposition": "degraded",
    }, evidence_relation="supports", dependency_kind="independently_sourced_observation",
       reliability_posture="verified", independence_basis="configured-test-source")
    assert configured.proposition_id == proposition.proposition_id
    _proof, binding = ResidentEpistemicDevelopmentRuntime._adapt(
        board, board.facts[0], configured)
    assert binding.evidence_relation == "contextualizes"
    assert binding.dependency_kind == "unknown_dependency"
    assert binding.dependency_group is None
    assert binding.reliability_posture == "attestation_signature_verifier_result_context_only"


def test_integrity_controller_observation_cannot_become_epistemic_support(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("SENTIENTOS_INTEGRITY_CONTROLLER_OBSERVATION", "1")
    monkeypatch.setenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "0")
    record = _integrity_controller_world_state_record(tmp_path, observed_at=NOW)
    assert record is not None
    board = WorldStateBoardBuilder(
        clock=lambda: datetime.fromisoformat(NOW)).build([record])
    _, proposition, _, runtime = fixture(tmp_path)
    configured = replace(runtime.config.rules[0], selector={
        "source_kind": "audit_trust",
        "subject_kind": "integrity_controller_observation",
        "stage": "observation",
    }, evidence_relation="supports", dependency_kind="independently_sourced_observation",
       reliability_posture="verified", independence_basis="configured-test-source")
    assert configured.proposition_id == proposition.proposition_id
    _proof, binding = ResidentEpistemicDevelopmentRuntime._adapt(
        board, board.facts[0], configured)
    assert binding.evidence_relation == "contextualizes"
    assert binding.dependency_kind == "unknown_dependency"
    assert binding.dependency_group is None
    assert binding.reliability_posture == "integrity_controller_verification_context_only"


def test_incident_restart_custody_is_epistemic_context_not_support(tmp_path):
    incident_at = "2026-09-28T11:59:00+00:00"
    incident = build_incident(triggers=["verified_integrity_mismatch"],
        enforcement_mode="enforce", severity="warning", created_at=incident_at)
    write_incident(tmp_path, incident, quarantine_activated=True)
    save_state(tmp_path, QuarantineState(active=True, activated_at=incident_at,
        activated_by="auto", last_incident_id=incident.incident_id,
        freeze_forge=True, allow_automerge=False, allow_publish=False,
        allow_federation_sync=False, notes=[]))
    record = _quarantine_incident_custody_world_state_record(
        tmp_path, observed_at=NOW, expected_incident_id=incident.incident_id,
        expected_activated_at=incident_at)
    assert record is not None
    assert record["payload"]["incident_activated_at"] == incident_at
    board = WorldStateBoardBuilder(
        clock=lambda: datetime.fromisoformat(NOW)).build([record])
    _, proposition, _, runtime = fixture(tmp_path)
    configured = replace(runtime.config.rules[0], selector={
        "source_kind": "quarantine",
        "subject_kind": "quarantine_incident_custody_observation",
        "stage": "observation",
    }, evidence_relation="supports", dependency_kind="independently_sourced_observation",
       reliability_posture="verified", independence_basis="configured-test-source")
    assert configured.proposition_id == proposition.proposition_id
    _proof, binding = ResidentEpistemicDevelopmentRuntime._adapt(
        board, board.facts[0], configured)
    assert binding.evidence_relation == "contextualizes"
    assert binding.dependency_kind == "unknown_dependency"
    assert binding.dependency_group is None
    assert binding.reliability_posture == "quarantine_incident_custody_context_only"


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


def test_stale_observation_cannot_become_current_by_declaring_freshness() -> None:
    observed_at = "2026-09-25T12:00:00+00:00"
    record = {
        "source_kind": "runtime_supervisor", "source_id": "resident-serving:session-old",
        "schema_version": "runtime.test.v1", "subject_id": "session-old",
        "subject_kind": "observed_running_model", "stage": "observation",
        "disposition": "observed", "evidence_strength": "serving_session_observation",
        "observed_at": observed_at,
        "staleness": "fresh",
        "payload": {
            "running_model_identity_observed": {"model_id": "model-a"},
            "serving_session_id": "session-old",
            "event_time_posture": "serving_session_observation_time_not_model_load_time",
            "authority": False, "effect_proven": False,
        },
    }
    snapshot = WorldStateBoardBuilder(
        clock=lambda: datetime.fromisoformat(NOW)).build([record])
    fact = snapshot.facts[0]
    assert fact.source.staleness == "stale"

    rule = EpistemicDevelopmentRule(
        "rule-model", "proposition-model", "a" * 64, {}, "supports",
        "independently_sourced_observation", "serving_owner_observation")
    proof, binding = ResidentEpistemicDevelopmentRuntime._adapt(snapshot, fact, rule)
    assert proof.recorded_at == observed_at
    assert binding.source_digest == fact.source.digest
    assert binding.observation_time == observed_at
    assert binding.freshness == "stale"


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


def test_introspection_snapshot_diagnostics_remain_historical_context(tmp_path):
    _owner, proposition, _ledger, runtime = fixture(tmp_path)
    record = {
        "source_kind": "owner_introspection",
        "source_id": "introspection-diagnostics:causal-introspection-fixture",
        "schema_version": "sentientos.causal_introspection:v1",
        "subject_kind": "snapshot_diagnostics",
        "subject_id": "causal-introspection-snapshot",
        "stage": "observation",
        "disposition": "incomplete",
        "evidence_strength": "snapshot_integrity_metadata",
        "observed_at": NOW,
        "payload": {
            "introspection_snapshot_id": "causal-introspection-fixture",
            "introspection_snapshot_digest": "a" * 64,
            "introspection_snapshot_generation": 7,
            "introspection_snapshot_predecessor_digest": "b" * 64,
            "introspection_capture_tick": NOW,
            "introspection_snapshot_completion_posture": "partial",
            "snapshot_completion_posture": "partial",
            "conflict_count": 1,
            "conflict_posture": "unresolved_no_winner_selected",
            "omitted_conflict_count": 0,
            "omitted_capture_finding_count": 0,
            "capture_findings": [{"owner_id": "serving", "domain": "model_serving",
                "error_code": "provider_projection_failed", "error_class": "RuntimeError"}],
            "conflicts": [{"observation_key": "shared.status",
                "projection_ids": ["projection-a", "projection-b"]}],
            "authority": False, "current_truth": False,
        },
        "effect_claimed": False, "effect_proven": False,
    }
    board = WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([record])
    rule = EpistemicDevelopmentRule("introspection-diagnostics", proposition.proposition_id,
        proposition.proposition_digest, {}, "supports", "unknown_dependency",
        "historical_owner_introspection_diagnostics")

    proof, binding = runtime._adapt(board, board.facts[0], rule)
    provenance = json.loads(proof.provenance_id)

    assert provenance["event_time_posture"] == "historical_or_unknown"
    assert provenance["causal_introspection_snapshot_lineage"]["introspection_snapshot_id"] == (
        "causal-introspection-fixture")
    diagnostic = provenance["causal_introspection_snapshot_diagnostics"]
    assert diagnostic["snapshot_completion_posture"] == "partial"
    assert diagnostic["conflict_posture"] == "unresolved_no_winner_selected"
    assert diagnostic["conflicts"] == [{"observation_key": "shared.status",
        "projection_ids": ["projection-a", "projection-b"]}]
    assert diagnostic["capture_findings"][0]["error_class"] == "RuntimeError"
    assert binding.freshness == "unknown"
    assert binding.evidence_relation == "contextualizes"
    assert binding.dependency_kind == "unknown_dependency"


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


def test_post_adoption_campaign_retrieval_time_is_not_outcome_time(tmp_path):
    _owner, proposition, _ledger, runtime = fixture(tmp_path)
    declared_time = "2026-01-10T00:00:00Z"
    record = {
        "source_kind": "owner_introspection",
        "source_id": "post-adoption-attribution:campaign-result-1",
        "schema_version": "sentientos.maintenance_post_adoption_attribution_campaign_result:v1",
        "subject_kind": "post_adoption_attribution_campaign",
        "subject_id": "campaign-result-1",
        "stage": "observation",
        "disposition": "repeated_target_contradiction_under_matched_controls",
        "evidence_strength": "digest_verified_campaign_custody_unverified_sources",
        "observed_at": NOW,
        "payload": {
            "campaign_id": "attribution-campaign:0123456789abcdef01234567",
            "result_id": "campaign-result-1", "result_digest": "a" * 64,
            "declared_completed_at": declared_time,
            "event_time_posture": "caller_declared_campaign_completion_time",
            "source_issuer_posture": "unverified_caller_supplied_sources",
            "production_ready": False, "current_truth": False,
            "authority": {"effect_authority": False, "adoption_authority": False,
                "observation_authority": False, "goal_authority": False,
                "authoring_authority": False, "execution_authority": False},
        },
        "effect_claimed": False, "effect_proven": False,
    }
    board = WorldStateBoardBuilder(clock=lambda: datetime.fromisoformat(NOW)).build([record])
    rule = EpistemicDevelopmentRule("post-adoption-history", proposition.proposition_id,
        proposition.proposition_digest, {}, "supports", "unknown_dependency", "campaign_history")

    proof, binding = runtime._adapt(board, board.facts[0], rule)
    provenance = json.loads(proof.provenance_id)

    assert provenance["post_adoption_campaign_time_claim"] == {
        "declared_completed_at": declared_time,
        "event_time_posture": "caller_declared_campaign_completion_time",
        "source_issuer_posture": "unverified_caller_supplied_sources",
    }
    assert proof.recorded_at == "undated"
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


def test_conflicting_epistemic_revision_reaches_later_cognition_after_restart(
        tmp_path):
    """Persistent independent evidence survives reconstruction into real cognition."""
    owner, proposition, _ledger, runtime = fixture(tmp_path)
    first = runtime.process_snapshot(snapshot(), tick=10, recorded_at=NOW)
    support_state = owner.current_state(proposition.proposition_id)
    assert support_state is not None and first.new_binding_count == 1

    support_rule = runtime.config.rules[0]
    contradiction_rule = replace(support_rule, rule_id="service-failed",
        evidence_relation="contradicts",
        selector={**support_rule.selector, "disposition": "failed"})
    runtime.config = replace(runtime.config, rules=(support_rule, contradiction_rule))
    correction_time = "2026-09-28T12:01:00+00:00"
    correction = runtime.process_snapshot(snapshot("failed",
        source_id="independent-supervisor-b", observed_at=correction_time),
        tick=11, recorded_at=correction_time)
    contested = owner.current_state(proposition.proposition_id)
    assert correction.new_binding_count == 1
    assert contested is not None and contested.stance == "contested"

    # Reopen the durable owner and compose its prior-tick semantic projection
    # through the normal cognition owner. Neither observation is promoted to
    # current truth or authority.
    recovered = PersistentEpistemicStateOwner(tmp_path / "epistemics",
        allowed_namespaces=("operator",))
    definitions = {RESIDENT_EPISTEMIC_STATE_MUTATION:
        RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION}
    def recovered_sequence():
        admissions, revocations = _ledger.load()
        return max([item.issued_sequence for item in admissions]
            + [item.sequence for item in revocations], default=1)
    recovered_controller = ResidentEpistemicStateMutationController(
        owner=recovered,
        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=_ledger),
        current_sequence=recovered_sequence,
        receipt_root=tmp_path / "receipts")
    assert recovered_controller.verify_receipts()["status"] == "verified"
    projection = recovered.cognitive_projection(max_states=4, current_tick=12)
    assert projection is not None

    from tests.test_resident_developmental_cognition import (
        owner as cognition_owner, snapshot as cognition_snapshot,
    )
    cognition, model = cognition_owner(tmp_path / "cognition")
    result = cognition.run_tick(snapshot=cognition_snapshot(),
        tick_id="epistemic-conflict-after-restart", prior_epistemic_state=projection)
    request = next(item for item in model.requests
        if item.purpose == "resident_developmental_retrieval_cognition")
    consumed = json.loads(request.prompt)["prior_epistemic_state"]
    [packet] = consumed["semantic_packets"]
    assert packet["state"]["stance"] == "contested"
    assert len(packet["supporting_evidence"]) == 1
    assert len(packet["contradicting_evidence"]) == 1
    binding_by_id = {item["binding_id"]: item
        for item in packet["active_evidence_bindings"]}
    support = binding_by_id[packet["supporting_evidence"][0]]
    contradiction = binding_by_id[packet["contradicting_evidence"][0]]
    assert support["observation_time"] == NOW
    assert contradiction["observation_time"] == correction_time
    assert support["source_artifact_id"] != contradiction["source_artifact_id"]
    assert request.upstream_evidence["epistemic_projection_id"] == projection.projection_id
    assert request.upstream_evidence["epistemic_state_digests"] == [contested.state_digest]
    assert result.cognition_observation_ids
    observation = cognition.verified_cognition_observation(result.cognition_observation_ids[0])
    assert observation["epistemic_state_digests"] == [contested.state_digest]
    assert observation["authority"] is False
