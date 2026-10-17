from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import sentientosd
from sentientos.resident_cognitive_model_transition_experiment import (
    TransitionError, TransitionJournal, TransitionProtocol,
)
from sentientos.resident_cognitive_model_transition_rehearsal import run
from sentientos.resident_cognitive_transition_operator import (
    PROTOCOL_CUSTODY, load_verified_protocol, persist_protocol,
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
        journal, transition_runtime_available=False) is None


def test_transition_quarantine_rejects_unverifiable_journal_custody(tmp_path: Path) -> None:
    path = tmp_path / "transition.journal.jsonl"
    path.write_bytes(b"{\"truncated\":true}")
    reason = sentientosd._resident_transition_recovery_quarantine_reason(
        TransitionJournal(path), transition_runtime_available=False)
    assert reason is not None
    assert reason.startswith("resident_transition_journal_unverified:")
