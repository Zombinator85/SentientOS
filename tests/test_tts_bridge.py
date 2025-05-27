import os
import sys
from importlib import reload

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tts_bridge


def test_speak_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_LOG_DIR", str(tmp_path))
    reload(tts_bridge)
    path = tts_bridge.speak("hi")
    # if engine missing, speak returns None
    assert path is None or os.path.exists(path)
