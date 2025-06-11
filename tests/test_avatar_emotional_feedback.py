import importlib
from pathlib import Path

import sentientos.avatar_emotional_feedback as aef


def test_log_and_trend(tmp_path, monkeypatch):
    log = tmp_path / "feedback.jsonl"
    monkeypatch.setenv("AVATAR_FEEDBACK_LOG", str(log))
    importlib.reload(aef)
    aef.log_feedback("ava", "invoked", "smile", mood="joy", user="alice")
    aef.log_feedback("ava", "played", "smile")
    assert log.exists()
    lines = log.read_text().splitlines()
    assert len(lines) == 2
    trend = aef.mood_trend("ava")
    assert trend == "positive"
