from importlib import reload


def test_multimodal_vision_only(tmp_path, monkeypatch):
    log = tmp_path / "multi.jsonl"
    monkeypatch.setenv("MULTIMODAL_LOG", str(log))
    import multimodal_tracker as mt
    reload(mt)
    tracker = mt.MultiModalEmotionTracker(enable_voice=False, camera_index=None)
    result = tracker.process(None)
    assert "timestamp" in result
    assert result["faces"] == []
    tracker._log(result)
    assert log.exists() and log.read_text()


def test_multimodal_voice_only(tmp_path, monkeypatch):
    log = tmp_path / "multi.jsonl"
    monkeypatch.setenv("MULTIMODAL_LOG", str(log))
    import multimodal_tracker as mt
    reload(mt)

    def fake_listen(self):
        return {"Joy": 1.0}

    monkeypatch.setattr(mt.VoiceSentiment, "listen", fake_listen)
    tracker = mt.MultiModalEmotionTracker(enable_vision=False, enable_voice=True)
    result = tracker.process(None)
    assert result.get("audio") == {"Joy": 1.0}
    assert tracker.timelines[0]


def test_multimodal_both_sources(tmp_path, monkeypatch):
    log = tmp_path / "multi.jsonl"
    monkeypatch.setenv("MULTIMODAL_LOG", str(log))
    import multimodal_tracker as mt
    reload(mt)

    def fake_listen(self):
        return {"Joy": 1.0}

    monkeypatch.setattr(mt.VoiceSentiment, "listen", fake_listen)

    def fake_process(self, frame):
        return {
            "timestamp": 0,
            "faces": [{"id": 1, "emotions": {"Sadness": 0.5}, "dominant": "Sadness"}],
        }

    monkeypatch.setattr(mt.FaceEmotionTracker, "process_frame", fake_process)
    monkeypatch.setattr(mt.FaceEmotionTracker, "__init__", lambda self, **k: None)
    tracker = mt.MultiModalEmotionTracker(enable_vision=True, enable_voice=True)
    result = tracker.process("frame")
    assert result["faces"] and result.get("audio")
    assert tracker.timelines[1]
    assert tracker.timelines[0]

