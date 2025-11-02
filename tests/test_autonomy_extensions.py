from __future__ import annotations

import json
import os
import sys

import importlib
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture()
def memory_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload

    import memory_manager as mm
    import notification

    reload(mm)
    reload(notification)
    return mm


def test_reflexion_records_insight(memory_env):
    from importlib import reload

    import reflexion_loop

    reload(reflexion_loop)

    goal = {"id": "g1", "text": "Test goal"}
    result = {"status": "failed", "critique": "Missing data"}
    insight = reflexion_loop.record_insight(goal, result, {"votes": []})
    assert insight["status"] == "failed"
    raw_files = sorted(memory_env.RAW_PATH.glob("*.json"))
    assert raw_files
    payload = json.loads(raw_files[-1].read_text())
    assert "reflexion" in payload["text"].lower()


def test_goal_curator_schedules_goal(memory_env):
    import goal_curator

    importlib.reload(goal_curator)

    for _ in range(3):
        memory_env.append_memory("Generate nightly digest", tags=["user_request"], source="unit")
    created = goal_curator.maybe_schedule_goals(min_repetitions=2)
    assert created
    goals = memory_env.get_goals()
    assert any("nightly digest" in g["text"].lower() for g in goals)


def test_critic_and_oracle_logging(memory_env):
    import critic_daemon
    import oracle_bridge

    importlib.reload(critic_daemon)
    importlib.reload(oracle_bridge)

    goal = {"id": "g2", "text": "Deploy update"}
    result = {"status": "failed", "error": "timeout"}
    consensus = {"approved": False, "votes": []}
    review = critic_daemon.review_action(goal, result, consensus)
    assert review["severity"] != "ok"
    consult = oracle_bridge.consult("Deploy update", intent={"type": "shell"})
    assert "recommendation" in consult


def test_emotion_snapshot(memory_env):
    import emotion_memory
    import emotion_ledger_analytics

    importlib.reload(emotion_memory)
    importlib.reload(emotion_ledger_analytics)

    emotion_memory.add_emotion({"Joy": 0.8, "Trust": 0.6})
    emotion_memory.add_emotion({"Joy": 0.2, "Trust": 0.4})
    snapshot = emotion_ledger_analytics.capture_snapshot()
    assert "average" in snapshot
    assert list(memory_env.RAW_PATH.glob("*.json"))


def test_hungry_eyes_active_learning(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))

    from sentientos.daemons.hungry_eyes import HungryEyesSentinel, HungryEyesDatasetBuilder

    builder = HungryEyesDatasetBuilder()
    for idx in range(5):
        builder.add_event({"status": "OK", "proof_report": {"valid": True}, "summary": f"case {idx}"})
    sentinel = HungryEyesSentinel(retrain_window=2)
    sentinel.fit(builder.build())
    assert sentinel.dataset_size == 5
    sentinel.observe({"status": "REJECTED", "proof_report": {"valid": False}, "summary": "new"})
    assert sentinel.dataset_size >= 6
