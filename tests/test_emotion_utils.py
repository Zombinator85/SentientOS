import os
import sys
from importlib import reload
import wave
try:
    import numpy as np
except Exception:
    np = None
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import emotion_utils as eu


def _make_wave(path: str, freq: float = 440.0):
    sr = 16000
    t = np.linspace(0, 0.5, int(sr * 0.5), False)
    tone = np.sin(freq * t * 2 * np.pi)
    tone = (tone * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(tone.tobytes())


def test_vad_and_features(tmp_path):
    wav = tmp_path / "tone.wav"
    if np is None:
        pytest.skip("numpy not available")
    _make_wave(str(wav))
    emotions, feats = eu.vad_and_features(str(wav))
    assert isinstance(emotions, dict)
    assert isinstance(feats, dict)
    # Expect some features present even if library falls back
    assert "rms" in feats
