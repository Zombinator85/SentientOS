from __future__ import annotations

from dataclasses import replace

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS, RESIDENT_EPISTEMIC_STATE_MUTATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
)
from sentientos.persistent_epistemic_state import (
    FALSE_AUTHORITY, PersistentEpistemicStateOwner, make_epistemic_update_candidate,
    make_evidence_binding, make_proposition,
)
from sentientos.resident_epistemic_state_mutation import (
    EVIDENCE_BINDING_EFFECTS, PRINCIPAL, STATE_UPDATE_EFFECTS,
    EpistemicMutationError, ResidentEpistemicStateMutationController,
    make_epistemic_evidence_source_proof,
)
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier

pytestmark = pytest.mark.no_legacy_skip


def setup(tmp_path):
    owner = PersistentEpistemicStateOwner(tmp_path / "owner", allowed_namespaces=("test",))
    proposition = make_proposition(namespace="test", subject="sky", predicate="color",
        object_value="blue", polarity="positive", qualifiers={}, temporal_scope={},
        context_scope={}, proposition_class="descriptive")
    owner.register_proposition(proposition)
    ledger = AdmissionLedger(tmp_path / "admissions.json")
    authority = RuntimeAdmissionAuthority(definitions=AUTHORITY_DEFINITIONS, ledger=ledger)
    controller = ResidentEpistemicStateMutationController(owner=owner,
        admission_verifier=RuntimeAdmissionVerifier(definitions=AUTHORITY_DEFINITIONS, ledger=ledger),
        current_sequence=lambda: 10, receipt_root=tmp_path / "controller")
    binding = make_evidence_binding(proposition_id=proposition.proposition_id,
        source_artifact_id="observation-1", source_digest="sha256:source", source_schema="sensor:v1",
        source_class="operator_observation", observation_time="2026-01-01T00:00:00Z",
        evidence_relation="supports", dependency_kind="independently_sourced_observation",
        dependency_group="operator-1", upstream_binding_ids=(), freshness="current",
        reliability_posture="supports")
    proof = make_epistemic_evidence_source_proof(source_artifact_id=binding.source_artifact_id,
        source_digest=binding.source_digest, source_schema=binding.source_schema,
        source_class=binding.source_class, recorded_at=binding.observation_time,
        adapter_id="test-adapter:v1", provenance_id="operator-record:1")
    return owner, proposition, authority, controller, binding, proof


def issue(authority, *, admission_id, effects, subject, config, sequence):
    return authority.issue(admission_id=admission_id,
        capability_id=RESIDENT_EPISTEMIC_STATE_MUTATION, definition_version=1,
        subsystem_kind="epistemics", principal_id=PRINCIPAL, principal_kind=PRINCIPAL,
        effects=effects, subject_id=subject, request_configuration_digest=config,
        provenance="operator-issued exact transaction", issued_sequence=sequence,
        valid_through_sequence=20,
        affirmative_preconditions=RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION.approval_requirements)


def test_separate_admissions_append_update_and_prior_only_projection(tmp_path) -> None:
    owner, proposition, authority, controller, binding, proof = setup(tmp_path)
    evidence = issue(authority, admission_id="evidence-E", effects=EVIDENCE_BINDING_EFFECTS,
        subject=binding.binding_id, config=controller.evidence_configuration_digest(
            binding=binding, proposition_digest=proposition.proposition_digest, operation_id="bind-1"), sequence=1)
    evidence_receipt = controller.append_evidence_binding(binding=binding, source_proof=proof,
        admission=evidence, operation_id="bind-1", correlation_id="workflow-1")
    candidate = make_epistemic_update_candidate(proposition_id=proposition.proposition_id,
        predecessor_state_digest=None, proposed_stance="provisionally_supported",
        evidence_binding_ids=(binding.binding_id,), reason="initialization", rationale="Explicit source supports proposal.",
        uncertainty="medium", model_id="explicit-caller")
    state_admission = issue(authority, admission_id="state-S", effects=STATE_UPDATE_EFFECTS,
        subject=candidate.candidate_id, config=controller.state_configuration_digest(
            candidate=candidate, operation_id="state-1"), sequence=2)
    state_receipt = controller.commit_update_candidate(candidate=candidate, admission=state_admission,
        operation_id="state-1", correlation_id="workflow-1", tick=1, recorded_at="2026-01-01T00:01:00Z")
    assert evidence.admission_id != state_admission.admission_id
    assert evidence_receipt.storage_verified and state_receipt.storage_verified
    projection = owner.cognitive_projection(max_states=1)
    assert projection is not None
    assert (projection.prior_position_only, projection.current_truth, projection.authority,
            projection.policy, projection.goal) == (True, False, False, False, False)


def test_cross_stage_broad_revoked_and_tampered_evidence_fail_without_mutation(tmp_path) -> None:
    owner, proposition, authority, controller, binding, proof = setup(tmp_path)
    config = controller.evidence_configuration_digest(binding=binding,
        proposition_digest=proposition.proposition_digest, operation_id="bind-1")
    state_only = issue(authority, admission_id="wrong-stage", effects=STATE_UPDATE_EFFECTS,
        subject=binding.binding_id, config=config, sequence=1)
    before = owner.verify()
    with pytest.raises(EpistemicMutationError):
        controller.append_evidence_binding(binding=binding, source_proof=proof, admission=state_only,
            operation_id="bind-1", correlation_id="c")
    broad = issue(authority, admission_id="broad", effects=tuple(sorted(
        RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION.required_effects)), subject=binding.binding_id,
        config=config, sequence=2)
    with pytest.raises(EpistemicMutationError):
        controller.append_evidence_binding(binding=binding, source_proof=proof, admission=broad,
            operation_id="bind-1", correlation_id="c")
    valid = issue(authority, admission_id="revoked", effects=EVIDENCE_BINDING_EFFECTS,
        subject=binding.binding_id, config=config, sequence=3)
    authority.revoke(valid.admission_id, sequence=4, reason_category="operator", provenance="withdrawn")
    with pytest.raises(EpistemicMutationError):
        controller.append_evidence_binding(binding=binding, source_proof=proof, admission=valid,
            operation_id="bind-1", correlation_id="c")
    with pytest.raises(EpistemicMutationError):
        controller.append_evidence_binding(binding=replace(binding, source_digest="tampered"), source_proof=proof,
            admission=valid, operation_id="bind-1", correlation_id="c")
    assert owner.verify() == before


def test_candidate_tamper_missing_evidence_authority_and_stale_cas_fail(tmp_path) -> None:
    owner, proposition, authority, controller, binding, proof = setup(tmp_path)
    evidence = issue(authority, admission_id="E", effects=EVIDENCE_BINDING_EFFECTS,
        subject=binding.binding_id, config=controller.evidence_configuration_digest(binding=binding,
            proposition_digest=proposition.proposition_digest, operation_id="bind"), sequence=1)
    controller.append_evidence_binding(binding=binding, source_proof=proof, admission=evidence,
        operation_id="bind", correlation_id="c")
    candidate = make_epistemic_update_candidate(proposition_id=proposition.proposition_id,
        predecessor_state_digest=None, proposed_stance="supported", evidence_binding_ids=(binding.binding_id,),
        reason="initialization", rationale="bounded", uncertainty="low", model_id="caller")
    admission = issue(authority, admission_id="S", effects=STATE_UPDATE_EFFECTS,
        subject=candidate.candidate_id, config=controller.state_configuration_digest(candidate=candidate,
            operation_id="state"), sequence=2)
    with pytest.raises(EpistemicMutationError):
        controller.commit_update_candidate(candidate=replace(candidate, rationale="tampered"), admission=admission,
            operation_id="state", correlation_id="c", tick=1, recorded_at="2026-01-01T00:01:00Z")
    with pytest.raises(EpistemicMutationError):
        controller.commit_update_candidate(candidate=replace(candidate, authority={**FALSE_AUTHORITY, "policy": True}),
            admission=admission, operation_id="state", correlation_id="c", tick=1,
            recorded_at="2026-01-01T00:01:00Z")
    controller.commit_update_candidate(candidate=candidate, admission=admission, operation_id="state",
        correlation_id="c", tick=1, recorded_at="2026-01-01T00:01:00Z")
    with pytest.raises(EpistemicMutationError):
        controller.commit_update_candidate(candidate=candidate, admission=admission, operation_id="state",
            correlation_id="c", tick=2, recorded_at="2026-01-01T00:02:00Z")
    missing = replace(make_epistemic_update_candidate(proposition_id=proposition.proposition_id,
        predecessor_state_digest=owner.current_state(proposition.proposition_id).state_digest,
        proposed_stance="contested", evidence_binding_ids=("evidence:missing",), reason="new_evidence",
        rationale="bounded", uncertainty="high", model_id="caller"))
    with pytest.raises(EpistemicMutationError):
        controller.commit_update_candidate(candidate=missing, admission=admission, operation_id="state",
            correlation_id="c", tick=2, recorded_at="2026-01-01T00:02:00Z")
