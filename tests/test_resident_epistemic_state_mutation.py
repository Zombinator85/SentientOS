from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentientos.codex_task_authority_admission import (
    AUTHORITY_DEFINITIONS, RESIDENT_EPISTEMIC_STATE_MUTATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
)
from sentientos.persistent_epistemic_state import (
    FALSE_AUTHORITY, EpistemicStateError, PersistentEpistemicStateOwner,
    make_epistemic_update_candidate,
    make_evidence_binding, make_proposition,
)
import sentientos.resident_epistemic_state_mutation as mutation_module
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


def issue(authority, *, admission_id, effects, subject, config, sequence,
          provenance="operator-issued exact transaction"):
    return authority.issue(admission_id=admission_id,
        capability_id=RESIDENT_EPISTEMIC_STATE_MUTATION, definition_version=1,
        subsystem_kind="epistemics", principal_id=PRINCIPAL, principal_kind=PRINCIPAL,
        effects=effects, subject_id=subject, request_configuration_digest=config,
        provenance=provenance, issued_sequence=sequence,
        valid_through_sequence=20,
        affirmative_preconditions=RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION.approval_requirements)


def test_separate_admissions_append_update_and_prior_only_projection(tmp_path) -> None:
    owner, proposition, authority, controller, binding, proof = setup(tmp_path)
    evidence = issue(authority, admission_id="evidence-E", effects=EVIDENCE_BINDING_EFFECTS,
        subject=binding.binding_id, config=controller.evidence_configuration_digest(
            binding=binding, proposition_digest=proposition.proposition_digest, operation_id="bind-1"), sequence=1,
        provenance=proof.provenance_id)
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


def test_windows_controller_construction_does_not_create_receipt_custody(
        monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "windows-read-only-custody"
    monkeypatch.setattr(mutation_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(ResidentEpistemicStateMutationController, "verify_receipts",
        lambda self: {})
    ResidentEpistemicStateMutationController(owner=object(), admission_verifier=object(),
        current_sequence=lambda: 1, receipt_root=root)
    assert not root.exists()
    assert not (root / "receipts" / "evidence").exists()
    assert not (root / "receipts" / "state").exists()
    assert not (root / "operations").exists()


def test_mutation_bound_state_is_not_cognized_without_verified_intent(tmp_path) -> None:
    owner, proposition, _authority, controller, _binding, _proof = setup(tmp_path)
    candidate = make_epistemic_update_candidate(
        proposition_id=proposition.proposition_id, predecessor_state_digest=None,
        proposed_stance="unknown", evidence_binding_ids=(), reason="initialization",
        rationale="unadmitted storage fixture", uncertainty="unknown", model_id="caller")
    state, _event = owner.commit_update(
        proposition_id=proposition.proposition_id, expected_predecessor_digest=None,
        stance="unknown", reason="initialization", active_binding_ids=(),
        candidate=candidate, correlation_id="unadmitted", tick=1,
        recorded_at="2026-01-01T00:00:00Z", mutation_binding={
            "candidate_id": candidate.candidate_id, "candidate_digest": candidate.candidate_digest,
            "admission_id": "missing-admission", "admission_binding_digest": "sha256:missing",
            "operation_id": "unadmitted-operation", "correlation_id": "unadmitted"})

    with pytest.raises(EpistemicStateError, match="mutation_lineage_unverified"):
        owner.cognitive_projection(max_states=1)
    with pytest.raises(EpistemicMutationError, match="mutation_lineage_intent_missing"):
        ResidentEpistemicStateMutationController(owner=owner,
            admission_verifier=controller.admission_verifier,
            current_sequence=controller.current_sequence,
            receipt_root=tmp_path / "controller")
    assert owner.current_state(proposition.proposition_id) == state


def test_missing_transaction_for_admitted_state_intent_fails_closed(tmp_path) -> None:
    owner, proposition, authority, controller, binding, proof = setup(tmp_path)
    evidence = issue(authority, admission_id="evidence-before-state",
        effects=EVIDENCE_BINDING_EFFECTS, subject=binding.binding_id,
        config=controller.evidence_configuration_digest(binding=binding,
            proposition_digest=proposition.proposition_digest, operation_id="bind-missing-tx"),
        sequence=1, provenance=proof.provenance_id)
    controller.append_evidence_binding(binding=binding, source_proof=proof,
        admission=evidence, operation_id="bind-missing-tx", correlation_id="missing-tx")
    candidate = make_epistemic_update_candidate(
        proposition_id=proposition.proposition_id, predecessor_state_digest=None,
        proposed_stance="provisionally_supported", evidence_binding_ids=(binding.binding_id,),
        reason="initialization", rationale="authenticated evidence", uncertainty="medium",
        model_id="caller")
    admission = issue(authority, admission_id="state-with-missing-transaction",
        effects=STATE_UPDATE_EFFECTS, subject=candidate.candidate_id,
        config=controller.state_configuration_digest(candidate=candidate,
            operation_id="state-missing-tx"), sequence=2)
    controller.commit_update_candidate(candidate=candidate, admission=admission,
        operation_id="state-missing-tx", correlation_id="missing-tx", tick=1,
        recorded_at="2026-01-01T00:01:00Z")
    transaction_paths = tuple((owner.root / "transactions").glob("*.json"))
    assert len(transaction_paths) == 1
    transaction_paths[0].unlink()

    recovered_owner = PersistentEpistemicStateOwner(owner.root, allowed_namespaces=("test",))
    with pytest.raises(EpistemicMutationError, match="mutation_intent_transaction_missing"):
        ResidentEpistemicStateMutationController(owner=recovered_owner,
            admission_verifier=controller.admission_verifier,
            current_sequence=controller.current_sequence,
            receipt_root=tmp_path / "controller")


def test_restart_reports_interrupted_state_intent_without_replaying_it(tmp_path) -> None:
    owner, proposition, authority, controller, _binding, _proof = setup(tmp_path)
    candidate = make_epistemic_update_candidate(
        proposition_id=proposition.proposition_id, predecessor_state_digest=None,
        proposed_stance="unknown", evidence_binding_ids=(), reason="initialization",
        rationale="bounded recovery fixture", uncertainty="unknown", model_id="caller")
    operation_id = "state-interrupted"
    admission = issue(authority, admission_id="state-interrupted-admission",
        effects=STATE_UPDATE_EFFECTS, subject=candidate.candidate_id,
        config=controller.state_configuration_digest(candidate=candidate, operation_id=operation_id),
        sequence=1)
    controller._write_state_intent(candidate=candidate, admission=admission,
        operation_id=operation_id, correlation_id="interrupted-workflow")

    recovered = ResidentEpistemicStateMutationController(owner=owner,
        admission_verifier=RuntimeAdmissionVerifier(definitions=AUTHORITY_DEFINITIONS,
            ledger=AdmissionLedger(tmp_path / "admissions.json")),
        current_sequence=lambda: 10, receipt_root=tmp_path / "controller")
    assert recovered.recovery_status["status"] == "incomplete"
    assert recovered.recovery_status["pending_state_intent_count"] == 1
    assert recovered.verify_receipts()["pending_state_intent_count"] == 1
    assert owner.current_state(proposition.proposition_id) is None


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
            proposition_digest=proposition.proposition_digest, operation_id="bind"), sequence=1,
        provenance=proof.provenance_id)
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


def test_evidence_admission_must_bind_exact_source_proof_provenance(tmp_path) -> None:
    owner, proposition, authority, controller, binding, proof = setup(tmp_path)
    config = controller.evidence_configuration_digest(binding=binding,
        proposition_digest=proposition.proposition_digest, operation_id="bind-1")
    mismatched = issue(authority, admission_id="mismatched-source-proof",
        effects=EVIDENCE_BINDING_EFFECTS, subject=binding.binding_id,
        config=config, sequence=1, provenance="different-source-proof")
    before = owner.verify()

    with pytest.raises(EpistemicMutationError,
            match="source_proof_admission_provenance_mismatch"):
        controller.append_evidence_binding(binding=binding, source_proof=proof,
            admission=mismatched, operation_id="bind-1", correlation_id="mismatch")

    assert owner.verify() == before
    assert owner.bindings(proposition.proposition_id) == ()


def test_invalid_update_tick_is_rejected_before_state_intent(tmp_path) -> None:
    owner, proposition, authority, controller, _binding, _proof = setup(tmp_path)
    candidate = make_epistemic_update_candidate(
        proposition_id=proposition.proposition_id, predecessor_state_digest=None,
        proposed_stance="unknown", evidence_binding_ids=(), reason="initialization",
        rationale="valid candidate with invalid chronology", uncertainty="unknown",
        model_id="caller")
    operation_id = "invalid-tick-operation"
    admission = issue(authority, admission_id="invalid-tick-admission",
        effects=STATE_UPDATE_EFFECTS, subject=candidate.candidate_id,
        config=controller.state_configuration_digest(candidate=candidate, operation_id=operation_id),
        sequence=1)
    with pytest.raises(EpistemicMutationError, match="epistemic_update_tick_invalid"):
        controller.commit_update_candidate(candidate=candidate, admission=admission,
            operation_id=operation_id, correlation_id="invalid-tick", tick=-1,
            recorded_at="2026-01-01T00:00:00Z")
    assert list(controller.intent_root.glob("*.json")) == []
    assert list((owner.root / "transactions").glob("*.json")) == []
    assert owner.current_state(proposition.proposition_id) is None


def test_naive_evidence_source_time_is_rejected_before_intent(tmp_path) -> None:
    owner, proposition, _authority, controller, _binding, _proof = setup(tmp_path)
    naive_time = "2026-01-01T00:00:00"
    binding = make_evidence_binding(
        proposition_id=proposition.proposition_id, source_artifact_id="naive-time-observation",
        source_digest="sha256:source", source_schema="sensor:v1",
        source_class="operator_observation", observation_time=naive_time,
        evidence_relation="supports", dependency_kind="independently_sourced_observation",
        dependency_group="operator-naive-time", upstream_binding_ids=(), freshness="current",
        reliability_posture="supports")
    proof = make_epistemic_evidence_source_proof(
        source_artifact_id=binding.source_artifact_id, source_digest=binding.source_digest,
        source_schema=binding.source_schema, source_class=binding.source_class,
        recorded_at=naive_time, adapter_id="test-adapter:v1", provenance_id="operator:naive-time")
    with pytest.raises(EpistemicMutationError, match="source_proof_recorded_at_invalid"):
        controller.append_evidence_binding(
            binding=binding, source_proof=proof, admission=None,  # type: ignore[arg-type]
            operation_id="naive-time-operation", correlation_id="naive-time")
    assert list(controller.intent_root.glob("*.json")) == []
    assert list((owner.root / "bindings").glob("*.json")) == []


def test_explicit_undated_evidence_time_remains_unknown_without_failure() -> None:
    ResidentEpistemicStateMutationController._validate_source_event_time("undated")


def test_orphan_mutation_receipt_is_not_reported_verified(tmp_path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("receipt publication fixture requires POSIX semantics")
    owner, proposition, authority, controller, binding, proof = setup(tmp_path)
    operation_id = "receipt-orphan-operation"
    admission = issue(authority, admission_id="receipt-orphan-admission",
        effects=EVIDENCE_BINDING_EFFECTS, subject=binding.binding_id,
        config=controller.evidence_configuration_digest(
            binding=binding, proposition_digest=proposition.proposition_digest,
            operation_id=operation_id), sequence=1, provenance=proof.provenance_id)
    controller.append_evidence_binding(
        binding=binding, source_proof=proof, admission=admission,
        operation_id=operation_id, correlation_id="receipt-orphan")
    for intent in controller.intent_root.glob("*.json"):
        intent.unlink()

    with pytest.raises(EpistemicMutationError, match="mutation_receipt_without_verified_intent"):
        ResidentEpistemicStateMutationController(
            owner=owner, admission_verifier=controller.admission_verifier,
            current_sequence=controller.current_sequence, receipt_root=tmp_path / "controller")


def test_evidence_intent_recovers_exact_source_proof_and_rejects_substitution(tmp_path) -> None:
    owner, proposition, authority, controller, binding, proof = setup(tmp_path)
    admission = issue(authority, admission_id="evidence-proof", effects=EVIDENCE_BINDING_EFFECTS,
        subject=binding.binding_id, config=controller.evidence_configuration_digest(
            binding=binding, proposition_digest=proposition.proposition_digest,
            operation_id="proof-operation"), sequence=1, provenance=proof.provenance_id)
    controller.append_evidence_binding(binding=binding, source_proof=proof, admission=admission,
        operation_id="proof-operation", correlation_id="proof-correlation")
    intent_path = next(controller.intent_root.glob("*.json"))
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    assert intent["source_proof"] == asdict(proof)

    # Recovery verifies the exact source proof retained in the v2 intent.
    controller.verify_receipts()
    intent["source_proof"]["adapter_id"] = "substituted-adapter"
    intent_path.write_bytes(mutation_module.canonical_bytes(intent) + b"\n")
    with pytest.raises(EpistemicMutationError, match="mutation_intent_identity_mismatch"):
        controller.verify_receipts()


def test_authorized_local_commit_orders_revocation_after_mutation_boundary(tmp_path) -> None:
    import os
    import threading

    if os.name != "posix":
        pytest.skip("POSIX ledger transaction lock is required")
    _owner, proposition, authority, controller, binding, _proof = setup(tmp_path)
    admission = issue(authority, admission_id="lease-E", effects=EVIDENCE_BINDING_EFFECTS,
        subject=binding.binding_id, config=controller.evidence_configuration_digest(
            binding=binding, proposition_digest=proposition.proposition_digest,
            operation_id="lease-operation"), sequence=1)
    started = threading.Event()
    finished = threading.Event()

    def revoke() -> None:
        started.set()
        authority.revoke(admission.admission_id, sequence=11,
            reason_category="explicit_test_revocation", provenance="fixture")
        finished.set()

    with controller.admission_verifier.authorized_local_commit():
        thread = threading.Thread(target=revoke)
        thread.start()
        assert started.wait(timeout=1)
        assert not finished.wait(timeout=0.05)
    thread.join(timeout=1)
    assert finished.is_set()
