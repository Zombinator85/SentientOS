"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


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


def test_fuse_multimodal():
    audio = {'Joy': 0.5}
    text = {'Sadness': 0.2}
    vis = {'Joy': 1.0}
    fused = eu.fuse(audio, text, vis, {'audio':1,'text':1,'vision':2})
    assert fused['Joy'] > 0.5
