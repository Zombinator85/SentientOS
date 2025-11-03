from __future__ import annotations

import importlib
import time
from datetime import datetime

import pytest

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture()
def memory_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import memory_manager as mm
    import notification

    importlib.reload(mm)
    importlib.reload(notification)
    return mm


def _observation_payload(text: str) -> dict[str, object]:
    now = datetime.utcnow().isoformat()
    return {
        "summary": text,
        "timestamp": now,
        "window_start": now,
        "window_end": now,
        "transcripts": [],
        "screen": [],
        "objects": [],
        "object_counts": {},
        "novel_objects": [],
        "emotions": {},
        "source_events": 1,
        "tags": ["observation", "perception"],
        "source": "test", 
    }


def test_reasoner_generates_summary(memory_env, monkeypatch):
    import perception_reasoner
    from sentientos.metrics import MetricsRegistry

    importlib.reload(perception_reasoner)

    metrics = MetricsRegistry()
    reasoner = perception_reasoner.PerceptionReasoner(interval_seconds=0.5, metrics=metrics)

    base = time.time()
    reasoner.ingest({
        "timestamp": base,
        "voice_transcript": "Hello observer",
        "voice": {"Joy": 0.8},
    })
    summary = reasoner.ingest(
        {
            "timestamp": base + 0.6,
            "scene": {
                "summary": "1 cat lounging",
                "objects": [{"label": "cat"}],
                "novel": ["cat"],
            },
        }
    )
    assert summary is not None
    assert "summary" in summary
    observations = memory_env.recent_observations()
    assert observations and observations[0]["summary"]
    snapshot = metrics.snapshot()
    assert snapshot["counters"].get("sos_perception_observations_total", 0) == 1.0


def test_reasoner_spawns_curiosity_task(memory_env, monkeypatch):
    import perception_reasoner
    import goal_curator
    from sentientos.metrics import MetricsRegistry

    importlib.reload(perception_reasoner)
    importlib.reload(goal_curator)

    captured: dict[str, object] = {}

    def fake_spawn(summary, *, novelty, author="perception_reasoner"):
        captured["summary"] = summary
        captured["novelty"] = novelty
        return {"id": "goal-1", "text": "Investigate"}

    monkeypatch.setattr(goal_curator, "spawn_curiosity_goal", fake_spawn)

    metrics = MetricsRegistry()
    reasoner = perception_reasoner.PerceptionReasoner(interval_seconds=0.5, novelty_threshold=0.2, metrics=metrics)

    start = time.time()
    reasoner.ingest({"timestamp": start, "scene": {"summary": "1 comet", "objects": [{"label": "comet"}], "novel": ["comet"]}})
    summary = reasoner.ingest({"timestamp": start + 0.6})
    assert summary is not None
    assert captured
    assert "curiosity_goal" in summary
    snapshot = metrics.snapshot()
    assert snapshot["counters"].get("sos_curiosity_tasks_spawned_total", 0) == 1.0


def test_reflexion_and_critic_include_observation(memory_env):
    import reflexion_loop
    import critic_daemon

    importlib.reload(reflexion_loop)
    importlib.reload(critic_daemon)

    record = memory_env.store_observation_summary(_observation_payload("Testing observation summary"))
    assert record["novelty"] >= 0.0

    goal = {"id": "goal-1", "text": "Test goal"}
    result = {"status": "failed", "critique": "Missing data"}
    insight = reflexion_loop.record_insight(goal, result, None)
    assert "observation_context" in insight
    review = critic_daemon.review_action(goal, result, None)
    assert "observation_context" in review
