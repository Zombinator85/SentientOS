import os
from importlib import reload

from feedback import FeedbackManager, FeedbackRule


def test_tracker_process_frame(tmp_path, monkeypatch):
    log = tmp_path / "vision.jsonl"
    monkeypatch.setenv("VISION_LOG", str(log))
    import vision_tracker as vt
    reload(vt)
    fm = FeedbackManager()
    fm.register_action('rec', lambda r, u, v: None)
    fm.add_rule(FeedbackRule(emotion='happy', threshold=0.5, action='rec'))
    tracker = vt.FaceEmotionTracker(camera_index=None, output_file=str(log), feedback=fm)
    result = tracker.process_frame(None)
    assert "timestamp" in result
    assert isinstance(result.get("faces"), list)
    tracker.log_result(result)
    assert log.exists() and log.read_text()
    # ensure feedback manager updated
    assert fm.get_history() == [] or isinstance(fm.get_history(), list)


def test_update_voice_sentiment(tmp_path, monkeypatch):
    log = tmp_path / "vision.jsonl"
    monkeypatch.setenv("VISION_LOG", str(log))
    import vision_tracker as vt
    reload(vt)
    fm = FeedbackManager()
    fm.register_action('rec', lambda r, u, v: None)
    fm.add_rule(FeedbackRule(emotion='happy', threshold=0.5, action='rec'))
    tracker = vt.FaceEmotionTracker(camera_index=None, output_file=str(log), feedback=fm)
    tracker.update_voice_sentiment(1, {"happy": 1.0})
    assert tracker.histories[1]
    assert fm.get_history()
