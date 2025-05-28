from importlib import reload
import os
import sys


def test_speak_without_engine(monkeypatch):
    monkeypatch.setenv('TTS_ENGINE', 'pyttsx3')
    monkeypatch.setitem(sys.modules, 'pyttsx3', None)
    monkeypatch.setenv('SENTIENTOS_HEADLESS', '1')
    import tts_bridge as tb
    reload(tb)
    assert tb.speak('hi') is None


def test_elevenlabs_fallback(monkeypatch):
    monkeypatch.setenv('TTS_ENGINE', 'elevenlabs')
    monkeypatch.delenv('ELEVEN_API_KEY', raising=False)
    monkeypatch.setenv('SENTIENTOS_HEADLESS', '1')
    import tts_bridge as tb
    reload(tb)
    assert tb.speak('hi') is None

def test_persona_switch():
    import tts_bridge as tb
    tb.set_voice_persona('test-voice')
    assert tb.CURRENT_PERSONA == 'test-voice'

def test_adapt_persona():
    import tts_bridge as tb
    tb.set_voice_persona('base')
    tb.ALT_VOICE = 'alt'
    tb.DEFAULT_VOICE = 'def'
    tb.adapt_persona({'Sadness': 0.5})
    assert tb.CURRENT_PERSONA == 'alt'
