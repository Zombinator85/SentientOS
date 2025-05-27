from pathlib import Path
from importlib import reload
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tts_bridge

class DummyEngine:
    def __init__(self):
        self.props = {}
    def setProperty(self, name, value):
        self.props[name] = value
    def save_to_file(self, text, path):
        Path(path).write_text('audio')
    def say(self, text):
        pass
    def runAndWait(self):
        pass
    def stop(self):
        pass


def test_speak_creates_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_LOG_DIR", str(tmp_path))
    reload(tts_bridge)
    tts_bridge.ENGINE = DummyEngine()
    tts_bridge.ENGINE_TYPE = "pyttsx3"
    out = tts_bridge.speak("hello")
    assert Path(out).exists()

