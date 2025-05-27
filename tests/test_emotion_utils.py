import wave
import math
from pathlib import Path

import emotion_utils as eu


def create_wav(path: Path) -> None:
    with wave.open(str(path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        frames = bytearray()
        for i in range(16000):
            val = int(10000 * math.sin(2 * math.pi * 440 * i / 16000))
            frames += int(val).to_bytes(2, 'little', signed=True)
        wf.writeframes(frames)


def test_vad_and_features(tmp_path):
    wav = tmp_path / "tone.wav"
    create_wav(wav)
    emotions, features = eu.vad_and_features(str(wav))
    assert isinstance(emotions, dict)
    assert isinstance(features, dict)
    assert "rms" in features
