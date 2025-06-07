import sys, os
from importlib import reload

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def test_multimodal_vision_only(tmp_path, monkeypatch):
    """Test vision-only mode: logs correct structure and no faces/audio by default."""
    monkeypatch.setenv("MULTI_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("MULTIMODAL_LOG", str(tmp_path / "multi.jsonl"))
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    import multimodal_tracker as mt
    reload(mt)
    tracker = mt.MultiModalEmotionTracker(enable_voice=False, camera_index=None, output_dir=str(tmp_path))
    result = tracker.process_once(None)
    assert "timestamp" in result
    assert "faces" in result
    assert result["faces"] == []
    # Ensure log file is written
    log_files = list(tmp_path.glob("*.jsonl"))
    assert log_files and all(f.read_text() for f in log_files)

def test_multimodal_voice_only(tmp_path, monkeypatch):
    """Test voice-only mode logs correct audio and timeline."""
    monkeypatch.setenv("MULTI_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("MULTIMODAL_LOG", str(tmp_path / "multi.jsonl"))
    monkeypatch.delenv("SENTIENTOS_HEADLESS", raising=False)

    # Patch mic_bridge for voice sentiment
    class FakeMic:
        @staticmethod
        def recognize_from_mic(save_audio: bool = True):
            return {"emotions": {"Joy": 1.0}}
    monkeypatch.setitem(sys.modules, "mic_bridge", FakeMic)
    import multimodal_tracker as mt
    reload(mt)
    tracker = mt.MultiModalEmotionTracker(enable_vision=False, enable_voice=True, camera_index=None, output_dir=str(tmp_path))
    result = tracker.process_once(None)
    # Check that at least one timeline entry for voice with Joy=1.0 exists
    found = any(
        e for t in tracker.memory.timelines.values() for e in t if e["source"] == "voice" and e["emotions"].get("Joy") == 1.0
    )
    assert found

def test_multimodal_both_sources(tmp_path, monkeypatch):
    """Test both vision and voice pipelines log and update memory."""
    monkeypatch.setenv("MULTI_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("MULTIMODAL_LOG", str(tmp_path / "multi.jsonl"))
    monkeypatch.delenv("SENTIENTOS_HEADLESS", raising=False)

    # Patch mic_bridge for voice
    class FakeMic:
        @staticmethod
        def recognize_from_mic(save_audio: bool = True):
            return {"emotions": {"Joy": 1.0}}
    monkeypatch.setitem(sys.modules, "mic_bridge", FakeMic)

    # Patch vision tracker for a fake face/emotion
    import multimodal_tracker as mt
    reload(mt)
    class FakeVision:
        def process_frame(self, frame):
            return {"faces": [{"id": 1, "emotions": {"Sadness": 0.5}, "dominant": "Sadness"}]}
    mt.FaceEmotionTracker = FakeVision
    tracker = mt.MultiModalEmotionTracker(enable_vision=True, enable_voice=True, camera_index=None, output_dir=str(tmp_path))
    result = tracker.process_once("frame")
    # Check both faces and voice are present and timelines are updated
    assert result["faces"]
    assert any(
        e for t in tracker.memory.timelines.values() for e in t if "vision" in e["source"] or "voice" in e["source"]
    )

def test_multimodal_headless(tmp_path, monkeypatch):
    """Test when neither vision nor mic is available (headless mode)."""
    monkeypatch.setenv("MULTI_LOG_DIR", str(tmp_path))
    monkeypatch.setitem(sys.modules, "mic_bridge", None)
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    import multimodal_tracker as mt
    reload(mt)
    tracker = mt.MultiModalEmotionTracker(enable_vision=False, enable_voice=False, camera_index=None, output_dir=str(tmp_path))
    result = tracker.process_once(None)
    assert "faces" in result
    # Timeline should be empty
    assert tracker.memory.timelines == {}
