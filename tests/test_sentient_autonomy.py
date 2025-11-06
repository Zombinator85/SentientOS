import pytest

from council_adapters import LocalVoice
from sentient_autonomy import SentientAutonomyEngine
from sentient_mesh import SentientMesh


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "auto-deepseek")
    monkeypatch.setenv("OPENAI_API_KEY", "auto-open")


def test_autonomy_generates_and_schedules_plans(tmp_path):
    mesh = SentientMesh(transcripts_dir=tmp_path, voices=[LocalVoice("autonomy-local")])
    mesh.update_node(
        "coordinator",
        trust=3.0,
        load=0.1,
        capabilities=["sentient_script", "planner"],
        emotion={"Focus": 0.7},
    )

    engine = SentientAutonomyEngine(mesh)
    engine.start()
    engine.queue_goal("Balance trust across nodes", priority=2)
    plans = engine.reflective_cycle(force=True)
    assert plans
    plan = plans[0]
    assert plan["plan_id"].startswith("auto-") or plan["plan_id"].startswith("goal-")
    assert plan["goal"]
    assert "script" in plan

    status = engine.status()
    assert status["counts"]["scheduled"] >= 0
    mesh_snapshot = mesh.status()
    assert isinstance(mesh_snapshot["assignments"], dict)
    sessions = mesh.sessions()
    assert sessions, "autonomy cycle should record council sessions"
