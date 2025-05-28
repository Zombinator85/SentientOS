import os
import sys
from importlib import reload


def test_multimodal_process(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTI_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("VISION_LOG", str(tmp_path / "vision.jsonl"))

    class FakeMic:
        @staticmethod
        def recognize_from_mic(save_audio: bool = True):
            return {"message": "hi", "emotions": {"Joy": 1.0}}

    monkeypatch.setitem(sys.modules, "mic_bridge", FakeMic)
    import multimodal_tracker as mt
    reload(mt)
    tracker = mt.MultiModalEmotionTracker(camera_index=None, output_dir=str(tmp_path))
    result = tracker.process_once(None)
    assert "timestamp" in result
    assert "faces" in result


def test_multimodal_headless(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTI_LOG_DIR", str(tmp_path))
    monkeypatch.setitem(sys.modules, "mic_bridge", None)
    import multimodal_tracker as mt
    reload(mt)
    tracker = mt.MultiModalEmotionTracker(camera_index=None)
    result = tracker.process_once(None)
    assert "faces" in result
    assert tracker.memory.timelines == {}
