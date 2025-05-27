import os
import sys
import wave
import struct

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import emotion_utils


def _create_wave(path):
    framerate = 16000
    t = [
        int(32767 * 0.5 * __import__('math').sin(2 * __import__('math').pi * 440 * i / framerate))
        for i in range(framerate // 10)
    ]
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(b''.join(struct.pack('<h', samp) for samp in t))


def test_vad_and_features(tmp_path):
    wav = tmp_path / "tone.wav"
    _create_wave(wav)
    vec, feats = emotion_utils.vad_and_features(str(wav))
    assert isinstance(vec, dict)
    assert isinstance(feats, dict)
    assert "valence" in feats

