from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import sentientosd
from sentientos.developmental_model_replacement_experiment import (
    CognitiveModelIdentity, FrozenCausalContext, ModelDevelopmentProvenance,
    ModelReplacementArtifactStore, ModelReplacementProtocol, _digest,
)
from sentientos.resident_cognitive_model_transition_experiment import (
    TransitionError, TransitionJournal, TransitionProtocol, history_boundary,
)
from sentientos.resident_cognitive_model_transition_rehearsal import run
from sentientos.resident_cognitive_transition_operator import (
    PROTOCOL_CUSTODY, LiveTransitionOperatorRuntime, load_verified_protocol, persist_protocol,
)

pytestmark = pytest.mark.no_legacy_skip


def _protocol() -> TransitionProtocol:
    identity = {"model_id": "A"}
    return TransitionProtocol.create(installation_identity="installation-1",
        predecessor=identity, successor={"model_id": "B"},
        initial_activation={"state_semantic_digest": "a" * 64, "generation": 1},
        initial_session={"session_id": "session-a"},
        initial_boundary={"boundary_digest": "b" * 64},
        b_operation_id="serve-b", restored_a_operation_id="serve-restored-a")


def test_fixed_protocol_custody_is_immutable_and_exactly_verified(tmp_path: Path) -> None:
    protocol = _protocol()
    assert persist_protocol(tmp_path, protocol) == tmp_path / PROTOCOL_CUSTODY
    loaded = load_verified_protocol(tmp_path, protocol_id=str(protocol.value["protocol_id"]),
                                    protocol_digest=str(protocol.value["protocol_digest"]))
    assert dict(loaded.value) == dict(protocol.value)
    with pytest.raises(FileExistsError):
        persist_protocol(tmp_path, protocol)
    with pytest.raises(TransitionError, match="transition_protocol_config_binding_mismatch"):
        load_verified_protocol(tmp_path, protocol_id="wrong",
                               protocol_digest=str(protocol.value["protocol_digest"]))


def test_run_loop_regression_closes_previous_daemon_composition_gap() -> None:
    source = inspect.getsource(sentientosd.run_loop)
    assert "RESIDENT_COGNITIVE_TRANSITION_LIVE_CONFIG_ENV" in source
    assert "_compose_live_resident_transition" in source
    assert "block_resident_cognition_for_transition_recovery" in source
    assert "_resident_transition_recovery_quarantine_reason" in source
    assert "resident_transition_runtime=resident_transition_runtime" in source
    tail = inspect.getsource(sentientosd._run_resident_cognition_and_transition)
    assert tail.index("run_resident_developmental_cognition") < tail.index(
        "process_resident_cognitive_transition_request")


def test_actual_daemon_composition_helper_rehearsal_uses_same_live_objects(tmp_path: Path) -> None:
    result = run(tmp_path / "actual-daemon", live_operator_ingress=True)
    assert result["status"] == "verified_complete"
    assert result["actual_daemon_composition_helper_exercised"] is True
    assert result["fixed_protocol_custody_loaded"] is True
    assert result["daemon_transition_slot_is_resident_slot"] is True
    assert result["daemon_transition_gate_is_resident_gate"] is True
    assert result["daemon_transition_history_is_resident_history"] is True
    assert result["daemon_transition_kernel_is_resident_kernel"] is True
    assert result["one_request_per_stage"] is True
    assert result["duplicate_request_result"]["status"] == "already_consumed"
    assert result["quiesced_subsequent_tick_result"] == "resident_cognition_quiesced"
    assert result["resume_inference_deltas"] == [0, 0]
    summary = json.loads((tmp_path / "actual-daemon" / "transition.summary.json").read_text())
    assert summary == result


class _CognitionResult:
    def __init__(self, status: str):
        self.status = status


def test_transition_restart_failure_blocks_cognition_while_new_gate_is_open(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Owner:
        def __init__(self):
            self.calls = 0

        def run_tick(self, **kwargs):
            self.calls += 1
            return _CognitionResult("unexpectedly_ran")

    owner = Owner()
    gate = sentientosd.ResidentCognitionQuiescenceGate()
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    surfaces = sentientosd.RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime-state",
        resident_developmental_owner=owner, resident_cognition_gate=gate)
    surfaces._world_state_snapshot = object()
    surfaces._world_state_snapshot_built_for_tick = "restart-tick"

    assert gate.quiesced is False
    surfaces.block_resident_cognition_for_transition_recovery(
        "live_quiescence_custody_mismatch")
    cognition = surfaces.run_resident_developmental_cognition(tick_id="restart-tick")
    transition = surfaces.process_resident_cognitive_transition_request(
        tick_id="restart-tick")

    assert cognition["status"] == "degraded"
    assert cognition["reason"] == (
        "resident_transition_recovery_required:live_quiescence_custody_mismatch")
    assert cognition["write_performed"] is False
    assert owner.calls == 0
    assert transition["status"] == "blocked"
    assert transition["interrupted"] is True



def test_transition_quarantine_reads_canonical_journal_without_reconstructing_gate(tmp_path: Path) -> None:
    journal = TransitionJournal(tmp_path / "transition.journal.jsonl")
    assert sentientosd._resident_transition_recovery_quarantine_reason(
        journal, transition_runtime_available=False) is None
    journal.append("a_quiesced", {"token": "prior-process-only"})
    reason = sentientosd._resident_transition_recovery_quarantine_reason(
        journal, transition_runtime_available=False)
    assert reason == (
        "resident_transition_recovery_required:process_local_quiescence_lost:a_quiesced")

    journal.append("b_activation_committed", {"activation": "committed"})
    assert sentientosd._resident_transition_recovery_quarantine_reason(
        journal, transition_runtime_available=False) == reason
    journal.append("b_epoch_resumed", {"session": "verified"})
    assert sentientosd._resident_transition_recovery_quarantine_reason(
        journal, transition_runtime_available=False) == (
            "resident_transition_recovery_required:runtime_unavailable:b_epoch_resumed")
    assert sentientosd._resident_transition_recovery_quarantine_reason(
        journal, transition_runtime_available=True) is None
    journal.append("experiment_complete", {"completed": True})
    assert sentientosd._resident_transition_recovery_quarantine_reason(
        journal, transition_runtime_available=False) == (
            "resident_transition_recovery_required:runtime_unavailable:experiment_complete")
    assert sentientosd._resident_transition_recovery_quarantine_reason(
        journal, transition_runtime_available=True) is None


def test_transition_quarantine_rejects_unverifiable_journal_custody(tmp_path: Path) -> None:
    path = tmp_path / "transition.journal.jsonl"
    path.write_bytes(b"{\"truncated\":true}")
    reason = sentientosd._resident_transition_recovery_quarantine_reason(
        TransitionJournal(path), transition_runtime_available=False)
    assert reason is not None
    assert reason.startswith("resident_transition_journal_unverified:")


def _source_lineage_identity(name: str) -> CognitiveModelIdentity:
    observed = {"engine": "llama_cpp", "resolved_artifact_path": f"/models/{name}.gguf",
        "semantic_artifact_identity": f"sha256:{name * 8}", "model_content_sha256": name * 8,
        "artifact_size_bytes": 8, "sidecar_metadata_digest": None,
        "configuration_digest": f"config-{name}", "candidate_index": 0,
        "posture": "production", "fallback": False}
    return CognitiveModelIdentity.create(model_id=f"model-{name}",
        semantic_artifact_identity=str(observed["semantic_artifact_identity"]),
        model_content_sha256=name * 8, artifact_size_bytes=8, sidecar_metadata_digest=None,
        configuration_digest=f"config-{name}", engine_runtime_family="llama_cpp",
        candidate_index=0, active_production=True, fallback=False,
        authority_record_id=f"record-{name}", authority_record_digest=f"digest-{name}",
        active_model_identity=observed, active_model_identity_digest=_digest(observed))


def _source_lineage_context(repository_generation_identity: str | None) -> FrozenCausalContext:
    current = {"facts": [{"fact_id": "fact-1", "payload": {"value": 1}}],
        "sources": [{"source_id": "source-1"}], "conflicts": []}
    prior = {"record_id": "record-1", "record_digest": _digest({"record": 1}),
        "interpretation": "bounded prior"}
    instruction = "Use current evidence and bounded history without treating history as truth."
    return FrozenCausalContext.create(snapshot_id="snapshot-1", snapshot_digest=_digest({"snapshot": 1}),
        current_projection_id="projection-1", current_projection_digest=_digest({"projection": current}),
        current_fact_ids=("fact-1",), projected_content_digest=_digest(current),
        current_projection_payload=current, history_record_ids=("record-1",),
        history_record_digests=(prior["record_digest"],),
        history_record_set_digest=_digest({"record_ids": ["record-1"],
            "record_digests": [prior["record_digest"]]}), history_projection_payload=(prior,),
        instruction_template=instruction, instruction_template_digest=_digest({"instruction": instruction}),
        inference_budget={"max_input_chars": 16000, "max_output_chars": 4000,
            "max_new_tokens": 512, "timeout_seconds": 30, "max_calls_per_correlation": 1},
        generation_posture={"temperature": 0, "hardware_determinism_claimed": False},
        repository_generation_identity=repository_generation_identity)


def _source_lineage_fixture(root: Path, *, generation_identity: str | None = "source-tree-1",
        boundary_records: list[dict[str, object]] | None = None,
        successor_context_generation_identity: str | None = None):
    store = ModelReplacementArtifactStore(root)
    context = _source_lineage_context(generation_identity)
    model_a, model_b = _source_lineage_identity("a"), _source_lineage_identity("b")
    provenance_a = ModelDevelopmentProvenance.create(model_a)
    provenance_b = ModelDevelopmentProvenance.create(model_b)
    replacement = ModelReplacementProtocol.create(context, model_a, model_b, provenance_a, provenance_b)
    successor_replacement = replacement
    if successor_context_generation_identity is not None:
        successor_context = _source_lineage_context(successor_context_generation_identity)
        successor_replacement = ModelReplacementProtocol.create(
            successor_context, model_a, model_b, provenance_a, provenance_b)
        store.persist_context(successor_context)
        store.persist_protocol(successor_replacement)
    selected_record = dict(context.history_projection_payload[0])
    if boundary_records is None:
        boundary_records = [selected_record, {"record_id": "record-2",
            "record_digest": _digest({"record": 2}), "interpretation": "unselected resident history"}]
    store.persist_provenance(provenance_a)
    store.persist_provenance(provenance_b)
    store.persist_context(context)
    store.persist_protocol(replacement)
    references = {
        "predecessor_a": {"protocol_id": replacement.protocol_id,
            "protocol_digest": replacement.protocol_digest, "model_role": "model_a"},
        "successor_b": {"protocol_id": replacement.protocol_id,
            "protocol_digest": replacement.protocol_digest, "model_role": "model_b"},
    }
    references["successor_b"] = {"protocol_id": successor_replacement.protocol_id,
        "protocol_digest": successor_replacement.protocol_digest, "model_role": "model_b"}
    transition = TransitionProtocol.create(installation_identity="installation-1",
        predecessor=model_a.active_model_identity, successor=model_b.active_model_identity,
        initial_activation={"state_semantic_digest": "a" * 64, "generation": 1},
        initial_session={"session_id": "session-a"},
        initial_boundary=history_boundary(boundary_records),
        b_operation_id="serve-b", restored_a_operation_id="serve-restored-a",
        model_replacement_protocol_references=references)
    return store, transition


def test_production_transition_requires_verified_frozen_model_generation_lineage(tmp_path: Path) -> None:
    generation_identity = "source-tree-1"
    store, transition = _source_lineage_fixture(tmp_path, generation_identity=generation_identity)
    with pytest.raises(TransitionError, match="transition_model_source_lineage_references_required"):
        sentientosd._verify_live_resident_transition_source_lineage(_protocol(), tmp_path)
    # The daemon configuration carries the artifact store's state root; the
    # store derives its developmental_experiments/model_replacement child.
    bindings = sentientosd._verify_live_resident_transition_source_lineage(transition, tmp_path)
    assert bindings["predecessor_a"]["software_generation_identity"] == generation_identity
    assert bindings["successor_b"]["software_generation_identity"] == generation_identity
    assert bindings["predecessor_a"]["selected_history_record_ids"] == ["record-1"]
    assert bindings["predecessor_a"]["selected_history_record_count"] == 1
    assert bindings["predecessor_a"]["resident_initial_history_record_count"] == 2
    assert bindings["predecessor_a"]["resident_initial_history_boundary_digest"] == (
        transition.value["initial_history_boundary"]["boundary_digest"])
    assert bindings["predecessor_a"]["history_binding_posture"] == (
        "verified_bounded_selection_within_complete_resident_boundary")
    omitted_record = transition.value["initial_history_boundary"]["records"][1]
    assert bindings["predecessor_a"]["omitted_history_record_count"] == 1
    assert bindings["predecessor_a"]["omitted_history_record_set_digest"] == _digest({
        "record_ids": [omitted_record["record_id"]],
        "record_digests": [omitted_record["record_digest"]],
    })
    assert bindings["predecessor_a"]["omission_binding_posture"] == (
        "verified_exact_complement_within_complete_resident_boundary")
    assert bindings["predecessor_a"]["software_generation_posture"] == (
        "frozen_context_declaration_not_running_observation")

    surfaces = object.__new__(sentientosd.RuntimeMaintenanceSurfaces)
    surfaces._resident_developmental_owner = SimpleNamespace(
        config=SimpleNamespace(model_replacement_artifact_root=tmp_path))
    surfaces._resident_developmental_configuration_status = "enabled"
    projected = surfaces._resident_model_provenance_bindings(transition.value)
    assert projected["predecessor_a"]["software_generation_identity"] == generation_identity
    assert projected["predecessor_a"]["selected_history_record_ids"] == ["record-1"]
    assert projected["successor_b"]["resident_initial_history_record_count"] == 2
    assert projected["successor_b"]["software_generation_posture"] == (
        "frozen_context_declaration_not_running_observation")

    status = LiveTransitionOperatorRuntime(
        config=SimpleNamespace(enabled=True, protocol_id=transition.value["protocol_id"],
            protocol_digest=transition.value["protocol_digest"]),
        installation_root=tmp_path,
        controller=SimpleNamespace(protocol=transition, health=lambda: {
            "status": "in_progress", "phase": "predecessor_a_epoch_current",
            "journal_head": "GENESIS", "replay_forbidden": False}),
        slot=SimpleNamespace(current_controller=SimpleNamespace(
            observed_current_session=lambda: None)),
        gate=SimpleNamespace(quiesced=False), source_lineage_bindings=bindings).status()
    assert status["model_source_lineage"] == bindings
    assert status["model_source_lineage_posture"] == (
        "verified_frozen_declarations_not_running_observation")

    composition = inspect.getsource(sentientosd._compose_live_resident_transition)
    assert "if not allow_synthetic_evidence_for_tests" in composition
    assert "_verify_live_resident_transition_source_lineage(protocol, artifact_root)" in composition
    _assert_transition_protocol_pair_and_boundary_integrity(
        tmp_path / "lineage_integrity")

    selected_record = dict(_source_lineage_context(generation_identity).history_projection_payload[0])
    invalid_boundaries = [
        ("absent", [], "transition_model_source_lineage_history_record_absent"),
        ("substituted", [{**selected_record, "record_digest": _digest({"record": "substituted"})}],
            "transition_model_source_lineage_history_record_digest_mismatch"),
        ("duplicate", [selected_record, selected_record],
            "transition_model_source_lineage_history_boundary_invalid"),
    ]
    for name, records, error in invalid_boundaries:
        _store, invalid_transition = _source_lineage_fixture(
            tmp_path / name, generation_identity=generation_identity, boundary_records=records)
        with pytest.raises(TransitionError, match=error):
            sentientosd._verify_live_resident_transition_source_lineage(invalid_transition, tmp_path / name)

    _store, mismatched_context_transition = _source_lineage_fixture(
        tmp_path / "mismatched-context", generation_identity=generation_identity,
        successor_context_generation_identity="different-frozen-context")
    with pytest.raises(TransitionError,
            match="transition_model_source_lineage_protocol_reference_mismatch"):
        sentientosd._verify_live_resident_transition_source_lineage(
            mismatched_context_transition, tmp_path / "mismatched-context")


def _assert_transition_protocol_pair_and_boundary_integrity(tmp_path: Path) -> None:
    generation_identity = "source-tree-1"
    store, transition = _source_lineage_fixture(tmp_path)
    value = transition.value
    references = dict(value["model_replacement_protocol_references"])
    references["successor_b"] = {**references["successor_b"],
        "protocol_id": "model-replacement-protocol-distinct",
        "protocol_digest": "sha256:" + "f" * 64}
    split_pair = TransitionProtocol.create(installation_identity=value["installation_identity"],
        predecessor=value["predecessor_a"], successor=value["successor_b"],
        initial_activation=value["initial_activation"],
        initial_session=value["initial_resident_session"],
        initial_boundary=value["initial_history_boundary"],
        b_operation_id=value["b_serving_operation_id"],
        restored_a_operation_id=value["restored_a_serving_operation_id"],
        model_replacement_protocol_references=references)
    with pytest.raises(TransitionError,
            match="transition_model_source_lineage_protocol_reference_mismatch"):
        sentientosd._verify_live_resident_transition_source_lineage(split_pair, tmp_path)
    surfaces = object.__new__(sentientosd.RuntimeMaintenanceSurfaces)
    surfaces._resident_developmental_owner = SimpleNamespace(
        config=SimpleNamespace(model_replacement_artifact_root=tmp_path))
    surfaces._resident_developmental_configuration_status = "enabled"
    projected = surfaces._resident_model_provenance_bindings(split_pair.value)
    assert projected["predecessor_a"]["finding"] == (
        "transition_model_source_lineage_protocol_reference_mismatch")
    assert projected["successor_b"]["finding"] == (
        "transition_model_source_lineage_protocol_reference_mismatch")

    context = _source_lineage_context("source-tree-1")
    original = dict(value["initial_history_boundary"])
    for key, replacement in (
            ("record_ids", ["substituted-record"]),
            ("record_digests", ["sha256:" + "0" * 64, original["record_digests"][1]]),
            ("record_set_digest", "0" * 64),
            ("boundary_digest", "0" * 64)):
        tampered = {**original, key: replacement}
        with pytest.raises(TransitionError,
                match="transition_model_source_lineage_history_boundary_invalid"):
            sentientosd._verify_transition_context_history_binding(context.__dict__, tampered)

    malformed_context = dict(context.__dict__)
    malformed_context["history_record_ids"] = ["record-1", "record-1"]
    malformed_context["history_record_digests"] = [
        context.history_record_digests[0], context.history_record_digests[0]]
    malformed_context["history_record_set_digest"] = _digest({
        "record_ids": malformed_context["history_record_ids"],
        "record_digests": malformed_context["history_record_digests"]})
    with pytest.raises(TransitionError,
            match="transition_model_source_lineage_history_boundary_invalid"):
        sentientosd._verify_transition_context_history_binding(malformed_context, original)

    for key, replacement in (
            ("schema_version", "sentientos.developmental_history_boundary:v3"),
            ("writeback_receipt_ids", ["receipt-without-digest"]),
    ):
        malformed_boundary = {**original, key: replacement}
        body = {name: item for name, item in malformed_boundary.items()
            if name != "boundary_digest"}
        malformed_boundary["boundary_digest"] = _digest(body)
        with pytest.raises(TransitionError,
                match="transition_model_source_lineage_history_boundary_invalid"):
            sentientosd._verify_transition_context_history_binding(
                context.__dict__, malformed_boundary)


def test_transition_lineage_requires_one_model_pair_protocol_and_integral_boundary(tmp_path: Path) -> None:
    _assert_transition_protocol_pair_and_boundary_integrity(tmp_path)



def test_production_transition_rejects_missing_frozen_generation_declaration(tmp_path: Path) -> None:
    _store, transition = _source_lineage_fixture(tmp_path, generation_identity=None)
    with pytest.raises(TransitionError, match="transition_software_generation_declaration_required"):
        sentientosd._verify_live_resident_transition_source_lineage(transition, tmp_path)
