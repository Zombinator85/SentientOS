import os
from importlib import reload


def test_tracker_process_frame(tmp_path, monkeypatch):
    log = tmp_path / "vision.jsonl"
    monkeypatch.setenv("VISION_LOG", str(log))
    import vision_tracker as vt
    reload(vt)
    tracker = vt.FaceEmotionTracker(camera_index=None, output_file=str(log))
    result = tracker.process_frame(None)
    assert "timestamp" in result
    assert isinstance(result.get("faces"), list)
    tracker.log_result(result)
    assert log.exists() and log.read_text()


def test_update_voice_sentiment(tmp_path, monkeypatch):
    log = tmp_path / "vision.jsonl"
    monkeypatch.setenv("VISION_LOG", str(log))
    import vision_tracker as vt
    reload(vt)
    tracker = vt.FaceEmotionTracker(camera_index=None, output_file=str(log))
    tracker.update_voice_sentiment(1, {"happy": 1.0})
    assert tracker.histories[1]
