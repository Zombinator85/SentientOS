import time

import memory_manager as mm
from curiosity_executor import CuriosityExecutor
from curiosity_goal_helper import CuriosityConfig, CuriosityGoalHelper
from sentientos.daemons.curiosity_loop import CuriosityLoopDaemon
from sentientos.metrics import MetricsRegistry


def _fake_goal(goal_id: str, text: str, intent: dict) -> dict:
    return {"id": goal_id, "text": text, "intent": intent}


def test_curiosity_helper_creates_goal(monkeypatch):
    helper = CuriosityGoalHelper(
        CuriosityConfig(enable=True, max_goals_per_hour=5, cooldown_minutes=1)
    )

    def fake_add_goal(text, intent=None, user="", priority=1, deadline=None, schedule_at=None):
        return _fake_goal("goal-1", text, intent or {})

    monkeypatch.setattr(mm, "add_goal", fake_add_goal)
    observation = {
        "summary": "Robot notices a shimmering artifact on the console.",
        "observation_id": "obs-1",
        "novel_objects": ["artifact"],
    }
    goal = helper.create_goal(observation, novelty=0.9, source="perception_reasoner")
    assert goal is not None
    assert helper.queue_length() == 1
    status = helper.status()
    assert status["status"] in {"active", "idle"}
    assert status["queue"] == 1


def test_curiosity_executor_records_reflection(monkeypatch):
    helper = CuriosityGoalHelper(CuriosityConfig(enable=True))
    counter = {"value": 0}

    def fake_add_goal(text, intent=None, user="", priority=1, deadline=None, schedule_at=None):
        counter["value"] += 1
        return _fake_goal(f"goal-{counter['value']}", text, intent or {})

    stored_reflection = {}

    def fake_store_reflection(reflection):
        stored = dict(reflection)
        stored.setdefault("reflection_id", "ref-1")
        stored_reflection.update(stored)
        return stored

    monkeypatch.setattr(mm, "add_goal", fake_add_goal)
    monkeypatch.setattr(mm, "store_reflection", fake_store_reflection)
    monkeypatch.setattr(mm, "append_memory", lambda *args, **kwargs: "mem")
    monkeypatch.setattr(mm, "update_novelty_score", lambda *args, **kwargs: True)

    observation = {
        "summary": "Unexpected sensor flicker detected.",
        "observation_id": "obs-2",
        "novel_objects": [],
    }
    helper.create_goal(observation, novelty=0.8, source="perception_reasoner")

    def investigator(entry):
        return {"recommendation": "Inspect sensor calibration", "context": ["log excerpt"]}

    executor = CuriosityExecutor(helper, metrics=MetricsRegistry(), investigator=investigator)
    result = executor.execute_next()
    assert result is not None
    assert "Inspect sensor calibration" in result["insight_summary"]
    assert stored_reflection["observation_id"] == "obs-2"
    assert stored_reflection["goal_id"] == "goal-1"


def test_curiosity_loop_daemon_status(monkeypatch):
    helper = CuriosityGoalHelper(CuriosityConfig(enable=True))

    def fake_add_goal(text, intent=None, user="", priority=1, deadline=None, schedule_at=None):
        return _fake_goal("goal-loop", text, intent or {})

    reflections = []

    def fake_store_reflection(reflection):
        record = dict(reflection)
        record.setdefault("reflection_id", f"ref-{len(reflections)}")
        reflections.append(record)
        return record

    monkeypatch.setattr(mm, "add_goal", fake_add_goal)
    monkeypatch.setattr(mm, "store_reflection", fake_store_reflection)
    monkeypatch.setattr(mm, "append_memory", lambda *args, **kwargs: "mem")
    monkeypatch.setattr(mm, "update_novelty_score", lambda *args, **kwargs: True)
    digest_calls = []
    monkeypatch.setattr(mm, "summarise_daily_insights", lambda: digest_calls.append(time.time()))

    observation = {
        "summary": "Ambient audio revealed unfamiliar melody.",
        "observation_id": "obs-3",
        "novel_objects": ["melody"],
    }
    helper.create_goal(observation, novelty=0.7, source="perception_reasoner")

    executor = CuriosityExecutor(
        helper,
        metrics=MetricsRegistry(),
        investigator=lambda entry: {"recommendation": "Archive the melody", "context": []},
    )
    daemon = CuriosityLoopDaemon(helper, executor, cadence_seconds=60, metrics=MetricsRegistry())
    daemon.run_once()
    status = daemon.status()
    assert status["queue"] == 0
    assert status["status"] in {"idle", "active"}
    assert len(status["recent_outcomes"]) >= 1
    assert digest_calls, "Daily insight digest should be generated"
