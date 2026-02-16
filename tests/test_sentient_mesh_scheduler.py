import json
import os
import threading
import time
from pathlib import Path

import pytest

from council_adapters import DeepSeekVoice, LocalVoice
from sentient_mesh import MeshJob, SentientMesh


@pytest.fixture(autouse=True)
def _ensure_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")


def test_mesh_scheduler_cycle_generates_transcripts(tmp_path, monkeypatch):
    mesh = SentientMesh(transcripts_dir=tmp_path)
    mesh.register_voice(LocalVoice("local-test"))
    mesh.register_voice(DeepSeekVoice("deepseek-test"))

    mesh.update_node(
        "alpha",
        trust=2.5,
        load=0.2,
        capabilities=["sentient_script", "council"],
        affect={"Joy": 0.6},
    )
    mesh.update_node(
        "beta",
        trust=1.1,
        load=0.1,
        capabilities=["sentient_script"],
        affect={"Calm": 0.4},
    )

    job = MeshJob(
        job_id="job-001",
        script={"prompt": "Draft a cooperative plan."},
        prompt="Draft a cooperative plan",
        priority=2,
        requirements=["sentient_script"],
        metadata={"origin": "test"},
    )

    snapshot = mesh.cycle([job])
    assert snapshot.assignments["job-001"] in {"alpha", "beta"}

    transcript_path = tmp_path / "job-001.jsonl"
    assert transcript_path.exists()
    lines = transcript_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 3
    first_record = json.loads(lines[0])
    assert set(first_record).issuperset({"voice", "role", "content", "signature"})
    assert json.dumps(first_record, sort_keys=True) == json.dumps(first_record)

    sessions = mesh.sessions("job-001")
    assert "job-001" in sessions
    assert sessions["job-001"], "sessions should include council exchanges"

    metrics = mesh.metrics()
    assert metrics["active_council_sessions"] >= 1
    status = mesh.status()
    assert "trust_vector" in status and "emotion_matrix" in status

    voices = mesh.voices_status()
    advisory_flags = {entry["config"]["advisory"] for entry in voices}
    assert advisory_flags == {True, False}


def test_mesh_scheduler_rejects_gradient_bearing_metadata(tmp_path):
    mesh = SentientMesh(transcripts_dir=tmp_path)
    mesh.update_node("alpha", trust=1.0, load=0.1, capabilities=["sentient_script"])

    job = MeshJob(
        job_id="rewarded",
        script={"prompt": "Do nothing"},
        metadata={"reward_signal": 0.8},
    )

    with pytest.raises(RuntimeError, match="NO_GRADIENT_INVARIANT"):
        mesh.cycle([job])


def test_trust_decay_preserves_ordering(tmp_path):
    mesh = SentientMesh(transcripts_dir=tmp_path)
    mesh.update_node("alpha", trust=2.0, load=0.1, capabilities=["sentient_script"])
    mesh.update_node("beta", trust=1.5, load=0.05, capabilities=["sentient_script"])
    mesh.update_node("gamma", trust=1.1, load=0.0, capabilities=["sentient_script"])

    pre_decay_order = sorted(
        mesh._nodes.values(), key=lambda state: (state.trust - state.load, -state.last_updated), reverse=True
    )

    mesh.cycle([])

    post_decay_order = sorted(
        mesh._nodes.values(), key=lambda state: (state.trust - state.load, -state.last_updated), reverse=True
    )

    assert [state.node_id for state in post_decay_order] == [state.node_id for state in pre_decay_order]


def test_cycle_determinism_with_identical_inputs(tmp_path):
    def build_mesh() -> SentientMesh:
        mesh = SentientMesh(transcripts_dir=tmp_path)
        mesh.update_node("alpha", trust=1.2, load=0.05, capabilities=["sentient_script"])
        mesh.update_node("beta", trust=1.2, load=0.05, capabilities=["sentient_script"])
        mesh._nodes["alpha"].last_updated = 1000.0
        mesh._nodes["beta"].last_updated = 500.0
        return mesh

    mesh_one = build_mesh()
    mesh_two = build_mesh()

    job = MeshJob(job_id="deterministic", script={"prompt": "Stay neutral"})

    first_snapshot = mesh_one.cycle([job])
    second_snapshot = mesh_two.cycle([job])

    assert first_snapshot.assignments == second_snapshot.assignments


def test_weight_freeze_rejects_midcycle_trust_mutation(tmp_path):
    mesh = SentientMesh(transcripts_dir=tmp_path)
    mesh.update_node("alpha", trust=1.0, load=0.1, capabilities=["sentient_script"])

    job = MeshJob(job_id="freeze", script={"prompt": "stabilize"})

    original_select = mesh._select_node

    def delayed_select(j: MeshJob):
        time.sleep(0.05)
        return original_select(j)

    mesh._select_node = delayed_select  # type: ignore[assignment]

    def mutate_trust():
        time.sleep(0.01)
        mesh._nodes["alpha"].trust = 5.0

    mutator = threading.Thread(target=mutate_trust)
    mutator.start()

    with pytest.raises(RuntimeError, match="INVARIANT"):
        mesh.cycle([job])

    mutator.join()



def test_mesh_node_state_aliases_legacy_emotion_field() -> None:
    from sentient_mesh import MeshNodeState

    legacy_payload = {
        "node_id": "legacy",
        "capabilities": ["sentient_script"],
        "emotion": {"Calm": 0.8},
    }

    state = MeshNodeState.from_dict(legacy_payload)

    assert state.affect == {"Calm": 0.8}
    serialized = state.to_dict()
    assert serialized["affect"] == {"Calm": 0.8}
    assert serialized["emotion"] == {"Calm": 0.8}
