import tempfile
import wave
from importlib import reload

import emotion_utils as eu


def create_silence(path: str) -> None:
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b'\x00' * 1600)


def test_vad_and_features_runs(tmp_path):
    wav = tmp_path / 'test.wav'
    create_silence(str(wav))
    reload(eu)
    vec, feats = eu.vad_and_features(str(wav))
    assert isinstance(vec, dict)
    assert isinstance(feats, dict)


def test_neural_detection_toggle(tmp_path, monkeypatch):
    wav = tmp_path / 'test.wav'
    create_silence(str(wav))
    monkeypatch.setenv('EMOTION_DETECTOR', 'neural')
    reload(eu)
    vec, feats = eu.detect(str(wav))
    assert isinstance(vec, dict)
    assert isinstance(feats, dict)
