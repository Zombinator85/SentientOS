from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import sentientosd
from sentientos.resident_cognitive_model_transition_experiment import TransitionError, TransitionProtocol
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
