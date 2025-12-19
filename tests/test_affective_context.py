import affective_context as ac
import policy_engine as pe
import memory_governor
from sentient_autonomy import SentientAutonomyEngine
from sentient_mesh import MeshSnapshot, SentientMesh


def test_contract_fields_and_bounded_overlay(monkeypatch):
    ac.clear_registry()
    monkeypatch.setattr("emotion_memory.average_emotion", lambda: {"Joy": 2.0, "Fear": -1.0})

    overlay = ac.capture_affective_context("unit-check", overlay={"Joy": 1.5, "Fear": -0.3})

    assert overlay["version"] == ac.AFFECTIVE_CONTEXT_CONTRACT_VERSION
    assert overlay["reason"] == "unit-check"
    assert all(0.0 <= v <= 1.0 for v in overlay["vector"].values())
    assert overlay["bounds"] == {"min": 0.0, "max": 1.0}
    assert overlay["decay_seconds"] > 0

    ac.require_affective_context({"affective_context": overlay})


def test_policy_engine_logs_affective_context(tmp_path):
    cfg = tmp_path / "pol.yml"
    cfg.write_text('{"policies":[{"id":"wave","conditions":{"tags":["wave"]},"actions":[{"type":"gesture","name":"wave"}]}]}')
    engine = pe.PolicyEngine(str(cfg))

    actions = engine.evaluate({"tags": ["wave"]})
    assert actions == [{"type": "gesture", "name": "wave"}]

    assert engine.logs
    entry = engine.logs[-1]
    ac.require_affective_context(entry)
    assert entry["affective_context"]["reason"] == "policy-evaluate"


def test_autonomy_plans_are_affect_annotated(tmp_path, monkeypatch):
    mesh = SentientMesh(transcripts_dir=tmp_path, voices=[])

    def deterministic_cycle(jobs):
        return MeshSnapshot(
            timestamp=0.0,
            assignments={job.job_id: None for job in jobs},
            trust_vector={},
            emotion_matrix={},
            council_sessions={},
            jobs=[job.describe() for job in jobs],
        )

    monkeypatch.setattr(mesh, "cycle", deterministic_cycle)
    monkeypatch.setattr(memory_governor, "mesh_metrics", lambda: {"nodes": 1, "emotion_consensus": {}})

    engine = SentientAutonomyEngine(mesh)
    engine.start()
    engine.queue_goal("Audit SCP sync")
    plans = engine.reflective_cycle(force=True)

    assert plans
    plan = plans[0]
    ac.require_affective_context(plan)
    assert plan["affective_context"]["reason"] in {"autonomy-cycle", "autonomy-plan", "autonomy-plan-create"}

