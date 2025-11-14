from types import SimpleNamespace

import logging

from sentientos.voice.tts import TtsConfig, TtsEngine


class DummyEngine:
    def __init__(self):
        self.properties = {}
        self.voices = [
            SimpleNamespace(id="default", name="Default"),
            SimpleNamespace(id="alice", name="Alice"),
        ]
        self.said = []
        self.runs = 0

    def setProperty(self, key, value):  # noqa: N802 - external API
        self.properties[key] = value

    def getProperty(self, key):  # noqa: N802 - external API
        if key == "voices":
            return self.voices
        return self.properties.get(key)

    def say(self, text):  # noqa: N802 - external API
        self.said.append(text)

    def runAndWait(self):  # noqa: N802 - external API
        self.runs += 1


def test_tts_engine_speak(monkeypatch):
    engine = DummyEngine()
    module = SimpleNamespace(init=lambda: engine)
    monkeypatch.setattr("sentientos.voice.tts.pyttsx3", module)

    config = TtsConfig(enabled=True, rate=200, volume=0.7, voice_name="Alice")
    tts = TtsEngine(config)

    tts.speak("hello world")

    assert engine.properties["rate"] == 200
    assert engine.properties["volume"] == 0.7
    assert engine.properties.get("voice") == "alice"
    assert engine.said == ["hello world"]
    assert engine.runs == 1


def test_tts_engine_noop_when_disabled(monkeypatch):
    calls = {"init": 0}

    class Module:
        def init(self):  # noqa: N802 - external API
            calls["init"] += 1
            return DummyEngine()

    monkeypatch.setattr("sentientos.voice.tts.pyttsx3", Module())

    tts = TtsEngine(TtsConfig(enabled=False))
    tts.speak("quiet")

    assert calls["init"] == 0


def test_tts_engine_handles_errors(monkeypatch, caplog):
    class FailingEngine(DummyEngine):
        def runAndWait(self):  # noqa: N802 - external API
            raise RuntimeError("boom")

    engine = FailingEngine()
    module = SimpleNamespace(init=lambda: engine)
    monkeypatch.setattr("sentientos.voice.tts.pyttsx3", module)

    tts = TtsEngine(TtsConfig(enabled=True))

    with caplog.at_level(logging.WARNING):
        tts.speak("test")

    assert any("TTS playback failed" in message for message in caplog.text.splitlines())
