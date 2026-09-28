from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from sentientos.codex_task_authority_admission import (
    RESIDENT_EPISTEMIC_STATE_MUTATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
)
from sentientos.persistent_epistemic_state import PersistentEpistemicStateOwner, make_proposition
from sentientos.resident_epistemic_development import (
    MAX_BINDINGS_PER_TICK, EpistemicDevelopmentConfig, EpistemicDevelopmentError,
    EpistemicDevelopmentRule, ResidentEpistemicDevelopmentRuntime,
)
from sentientos.resident_epistemic_state_mutation import ResidentEpistemicStateMutationController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from sentientos.world_state_board import WorldStateBoardBuilder

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
