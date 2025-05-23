import audioop
import wave
from typing import Tuple

try:
    import numpy as np
    from pyAudioAnalysis import audioBasicIO, MidTermFeatures
    HAS_PAA = True
except Exception:
    HAS_PAA = False


def _energy_emotion(audio_path: str) -> Tuple[str, float]:
    with wave.open(audio_path, "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        sampwidth = wf.getsampwidth()
        rms = audioop.rms(frames, sampwidth)
        label = "excited" if rms > 1000 else "calm"
        score = min(1.0, rms / 5000)
        return label, score


def detect_emotion(audio_path: str) -> Tuple[str, float]:
    """Return (label, score) for the given audio file."""
    if HAS_PAA:
        try:
            fs, sig = audioBasicIO.read_audio_file(audio_path)
            sig = audioBasicIO.stereo_to_mono(sig)
            mt, _ = MidTermFeatures.mid_feature_extraction(sig, fs, 1.0, 1.0, 0.05, 0.05)
            energy = float(np.mean(mt[0]))
            label = "excited" if energy > 0.3 else "calm"
            score = min(1.0, energy)
            return label, score
        except Exception:
            pass
    try:
        return _energy_emotion(audio_path)
    except Exception:
        return "neutral", 0.0
