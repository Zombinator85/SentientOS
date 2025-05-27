from importlib import reload
import os
import sys


def test_speak_without_engine(monkeypatch):
    monkeypatch.setenv('TTS_ENGINE', 'pyttsx3')
    monkeypatch.setitem(sys.modules, 'pyttsx3', None)
    import tts_bridge as tb
    reload(tb)
    assert tb.speak('hi') is None
