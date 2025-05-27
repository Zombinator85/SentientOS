import audioop
import wave
from pathlib import Path
from typing import Dict, Tuple

try:
    import numpy as np
    import librosa
except Exception:  # pragma: no cover - optional dependency
    np = None
    librosa = None

from emotions import empty_emotion_vector


def _fallback_rms(path: str) -> float:
    try:
        with wave.open(path, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            return audioop.rms(frames, wf.getsampwidth())
    except Exception:
        return 0.0


def vad_and_features(path: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Return an emotion vector and raw features for ``path``.

    The implementation uses ``librosa`` when available to compute simple
    acoustic features. If dependencies are missing, it falls back to a
    crude RMS-based estimate.
    """
    features: Dict[str, float] = {}
    vec = empty_emotion_vector()
    p = Path(path)
    if not p.exists():
        return vec, features

    if librosa and np:  # pragma: no cover - optional path
        try:
            y, sr = librosa.load(path, sr=16000)
            zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))
            rms = float(np.mean(librosa.feature.rms(y)))
            centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
            bandwidth = float(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr)))
            features = {
                "zcr": zcr,
                "rms": rms,
                "centroid": centroid,
                "bandwidth": bandwidth,
            }
            # very simple mapping to valence/arousal/dominance
            valence = max(0.0, min(1.0, 0.5 + (centroid - 3000) / 3000))
            arousal = max(0.0, min(1.0, rms * 10))
            dominance = max(0.0, min(1.0, 0.5 + (bandwidth - 1500) / 1500))
        except Exception:
            valence = arousal = dominance = 0.0
    else:
        rms = _fallback_rms(path)
        features = {"rms": rms}
        valence = 0.5
        arousal = min(1.0, rms / 5000)
        dominance = 0.5

    if valence > 0.6:
        vec["Joy"] = valence
    elif valence < 0.4:
        vec["Sadness"] = 1 - valence
    else:
        vec["Contentment"] = 0.5

    if arousal > 0.6:
        vec["Enthusiasm"] = arousal
    elif arousal < 0.3:
        vec["Boredom"] = 1 - arousal

    if dominance > 0.6:
        vec["Confident"] = dominance
    elif dominance < 0.4:
        vec["Insecurity"] = 1 - dominance

    features.update({"valence": valence, "arousal": arousal, "dominance": dominance})
    return vec, features
