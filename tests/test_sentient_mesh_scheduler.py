import json
import os
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
        emotion={"Joy": 0.6},
    )
    mesh.update_node(
        "beta",
        trust=1.1,
        load=0.1,
        capabilities=["sentient_script"],
        emotion={"Calm": 0.4},
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
