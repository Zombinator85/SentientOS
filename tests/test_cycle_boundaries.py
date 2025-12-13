import time

import pytest

import memory_governor
import sentient_mesh as mesh_module
from sentient_autonomy import SentientAutonomyEngine
from sentient_mesh import MeshJob, MeshSnapshot, SentientMesh


def _deterministic_metrics():
    return {
        "nodes": 1,
        "trust_histogram": {"alpha": 1.0},
        "active_council_sessions": 0,
        "emotion_consensus": {},
    }


def test_cycle_boundary_clean_to_clean_has_identical_inputs(monkeypatch, tmp_path):
    mesh = SentientMesh(transcripts_dir=tmp_path, voices=[])
    engine = SentientAutonomyEngine(mesh)
    engine.start()

    monkeypatch.setattr(memory_governor, "mesh_metrics", _deterministic_metrics)

    job_inputs: list[list[dict[str, object]]] = []

    def record_cycle(jobs):
        payload = [job.describe() for job in jobs]
        job_inputs.append(payload)
        return MeshSnapshot(
            timestamp=time.time(),
            assignments={job.job_id: None for job in jobs},
            trust_vector={},
            emotion_matrix={},
            council_sessions={},
            jobs=payload,
        )

    monkeypatch.setattr(mesh, "cycle", record_cycle)

    for _ in range(2):
        engine.queue_goal("Balance trust across nodes", priority=2)
        engine.queue_goal("Synchronise council insights", priority=2)
        engine.reflective_cycle(force=True)

    assert len(job_inputs) == 2
    assert job_inputs[0] == job_inputs[1]


def test_cycle_boundary_failure_does_not_decay_twice(monkeypatch, tmp_path):
    mesh = SentientMesh(transcripts_dir=tmp_path, voices=[])
    mesh.update_node("alpha", trust=1.0, load=0.0, capabilities=["sentient_script"])

    engine = SentientAutonomyEngine(mesh)
    engine.start()

    monkeypatch.setattr(memory_governor, "mesh_metrics", _deterministic_metrics)

    engine.queue_goal("stabilise trust")
    engine.reflective_cycle(force=True)

    trust_after_clean = mesh._nodes["alpha"].trust
    assert trust_after_clean < 1.0

    engine.queue_goal("stabilise trust")

    def fail_once(context, payload, _called={"value": False}):
        if context == "sentient_mesh.cycle" and not _called["value"]:
            _called["value"] = True
            return {"mode": "boundary_failure", "job_ids": payload.get("job_ids", [])}
        return None

    monkeypatch.setattr(mesh_module, "_TEST_FAILURE_INJECTOR", fail_once)

    plans = engine.reflective_cycle(force=True)
    assert plans == []
    assert engine._goal_queue, "goals should persist after a failed cycle"
    assert mesh._nodes["alpha"].trust == trust_after_clean

    monkeypatch.setattr(mesh_module, "_TEST_FAILURE_INJECTOR", None)
    engine.reflective_cycle(force=True)

    assert mesh._nodes["alpha"].trust == pytest.approx(trust_after_clean * 0.9, rel=1e-6)
    assert not engine._goal_queue


def test_cycle_boundary_repeated_failures_leave_state_unchanged(monkeypatch, tmp_path):
    mesh = SentientMesh(transcripts_dir=tmp_path, voices=[])
    mesh.update_node("alpha", trust=1.0, load=0.0, capabilities=["sentient_script"])

    job = MeshJob(job_id="job-boundary", script={"goal": "stabilise"})

    def always_fail(context, payload):
        if context == "sentient_mesh.cycle":
            return {"mode": "boundary_failure", "job_ids": payload.get("job_ids", [])}
        return None

    monkeypatch.setattr(mesh_module, "_TEST_FAILURE_INJECTOR", always_fail)

    with pytest.raises(RuntimeError, match="DETERMINISTIC_DEGRADATION:boundary_failure"):
        mesh.cycle([job])

    trust_after_first_failure = mesh._nodes["alpha"].trust

    with pytest.raises(RuntimeError, match="DETERMINISTIC_DEGRADATION:boundary_failure"):
        mesh.cycle([job])

    assert mesh._nodes["alpha"].trust == trust_after_first_failure

    monkeypatch.setattr(mesh_module, "_TEST_FAILURE_INJECTOR", None)

