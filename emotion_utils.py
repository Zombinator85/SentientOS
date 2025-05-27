import os
from typing import Dict, Tuple

try:
    import numpy as np  # type: ignore
    import librosa  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None
    librosa = None

from emotions import empty_emotion_vector


def vad_and_features(path: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Return emotion vector and raw features for an audio file.

    Uses simple spectral features when ``librosa`` is available. Falls back to an
    empty vector when dependencies are missing or the file cannot be processed.
    """
    vec = empty_emotion_vector()
    features: Dict[str, float] = {}
    if librosa is None or np is None or not os.path.exists(path):
        return vec, features

    try:
        y, sr = librosa.load(path, sr=16000)
        rms = float(np.mean(librosa.feature.rms(y=y)))
        centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
        features["rms"] = rms
        features["centroid"] = centroid
        # naive mapping to valence/arousal/dominance
        valence = min(1.0, max(0.0, (centroid - 1500) / 3000))
        arousal = min(1.0, max(0.0, (rms - 0.05) / 0.3))
        dominance = arousal
        if valence > 0.6:
            vec["Joy"] = valence
        elif valence < 0.4:
            vec["Sadness"] = 1.0 - valence
        if arousal > 0.7:
            vec["Anger"] = arousal
        elif arousal < 0.3:
            vec["Contentment"] = 1.0 - arousal
        if dominance > 0.7:
            vec["Confident"] = dominance
    except Exception:
        pass
    return vec, features
