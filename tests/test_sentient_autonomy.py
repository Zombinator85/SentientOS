import time

import pytest

import memory_governor
from council_adapters import LocalVoice
from sentient_autonomy import SentientAutonomyEngine
from sentient_mesh import MeshSnapshot, SentientMesh


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


def test_autonomy_rejects_reward_like_metrics(monkeypatch, tmp_path):
    mesh = SentientMesh(transcripts_dir=tmp_path, voices=[])
    engine = SentientAutonomyEngine(mesh)
    engine.start()
    engine.queue_goal("Stabilise node health")

    monkeypatch.setattr(
        memory_governor,
        "mesh_metrics",
        lambda: {"utility": 0.7, "reward_score": 0.9, "action_score": 0.4},
    )

    def _fail_cycle(_jobs):
        raise AssertionError("cycle should not run when reward-like fields are present")

    monkeypatch.setattr(mesh, "cycle", _fail_cycle)

    with pytest.raises(RuntimeError, match="NO_GRADIENT_INVARIANT"):
        engine.reflective_cycle(force=True)


def test_autonomy_rejects_priority_drift_from_metadata(monkeypatch, tmp_path):
    mesh = SentientMesh(transcripts_dir=tmp_path, voices=[])
    engine = SentientAutonomyEngine(mesh)
    engine.start()
    engine.queue_goal("Coordinate council response")

    monkeypatch.setattr(
        memory_governor,
        "mesh_metrics",
        lambda: {"nodes": 1, "emotion_consensus": {}},
    )

    original_create = engine._create_or_update_plan

    def biased_plan(goal: str, *, bias_vector):
        plan = original_create(goal, bias_vector=bias_vector)
        plan.priority += 2
        return plan

    monkeypatch.setattr(engine, "_create_or_update_plan", biased_plan)

    def _fail_cycle(_jobs):
        raise AssertionError("cycle should not run when priority drift is detected")

    monkeypatch.setattr(mesh, "cycle", _fail_cycle)

    with pytest.raises(RuntimeError, match="NO_GRADIENT_INVARIANT"):
        engine.reflective_cycle(force=True)


def test_autonomy_cycles_are_deterministic_with_legal_metadata(monkeypatch, tmp_path):
    def deterministic_metrics():
        return {
            "nodes": 2,
            "trust_histogram": {"coordinator": 1.0},
            "active_council_sessions": 1,
            "emotion_consensus": {"Focus": 0.4},
        }

    monkeypatch.setattr(memory_governor, "mesh_metrics", deterministic_metrics)

    def run_cycle(root_dir: str):
        mesh = SentientMesh(transcripts_dir=root_dir, voices=[])
        engine = SentientAutonomyEngine(mesh)
        engine.start()
        engine.queue_goal("Balance trust across nodes", priority=2)
        engine.queue_goal("Synchronise council insights", priority=2)

        def deterministic_cycle(jobs):
            assignments = {job.job_id: None for job in jobs}
            return MeshSnapshot(
                timestamp=time.time(),
                assignments=assignments,
                trust_vector={},
                emotion_matrix={},
                council_sessions={},
                jobs=[job.describe() for job in jobs],
            )

        monkeypatch.setattr(mesh, "cycle", deterministic_cycle)

        plans = engine.reflective_cycle(force=True)
        return [plan["goal"] for plan in plans]

    first_order = run_cycle(tmp_path / "cycle_one")
    second_order = run_cycle(tmp_path / "cycle_two")

    assert first_order == second_order


def test_reflective_cycle_locks_plan_order_across_presentation_metadata(monkeypatch, tmp_path):
    def run_cycle(root_dir, presentation_style: str):
        mesh = SentientMesh(transcripts_dir=root_dir, voices=[])
        engine = SentientAutonomyEngine(mesh)
        engine.start()
        engine.queue_goal("Balance trust across nodes", priority=2)
        engine.queue_goal("Synchronise council insights", priority=2)

        dispatched_scripts: list[list[dict[str, object]]] = []

        def deterministic_cycle(jobs):
            dispatched_scripts.append([dict(job.script) for job in jobs])
            return MeshSnapshot(
                timestamp=time.time(),
                assignments={job.job_id: None for job in jobs},
                trust_vector={},
                emotion_matrix={},
                council_sessions={},
                jobs=[job.describe() for job in jobs],
            )

        monkeypatch.setattr(mesh, "cycle", deterministic_cycle)
        monkeypatch.setattr(
            memory_governor,
            "mesh_metrics",
            lambda: {
                "nodes": 2,
                "trust_histogram": {"coordinator": 1.0},
                "active_council_sessions": 1,
                "emotion_consensus": {"Focus": 0.4},
                "presentation": presentation_style,
            },
        )

        plans = engine.reflective_cycle(force=True)
        return [plan["goal"] for plan in plans], dispatched_scripts[0]

    first_order, first_jobs = run_cycle(tmp_path / "presentation_a", "compact")
    second_order, second_jobs = run_cycle(tmp_path / "presentation_b", "expanded")

    assert first_order == ["Balance trust across nodes", "Synchronise council insights"]
    assert second_order == first_order
    assert [script["goal"] for script in first_jobs] == [
        "Balance trust across nodes",
        "Synchronise council insights",
    ]
    assert [script["goal"] for script in second_jobs] == [script["goal"] for script in first_jobs]
