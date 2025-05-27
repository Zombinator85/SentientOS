try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency
    np = None
try:
    import librosa  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    librosa = None
from emotions import empty_emotion_vector
from typing import Tuple, Dict

def vad_and_features(path: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Analyze audio file and return emotion vector and raw features."""
    if librosa is None or np is None:
        return empty_emotion_vector(), {}
    try:
        y, sr = librosa.load(path, sr=16000)
    except Exception:
        return empty_emotion_vector(), {}
    rms = float(np.mean(librosa.feature.rms(y=y)))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    pitch, _ = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr
    )
    pitch_val = float(np.nanmean(pitch)) if pitch is not None else 0.0
    features = {
        "rms": rms,
        "zcr": zcr,
        "centroid": centroid,
        "pitch": pitch_val,
    }
    valence = max(0.0, min(1.0, (pitch_val - 150.0) / 200.0 + centroid / 5000.0))
    arousal = max(0.0, min(1.0, rms * 20.0))
    dominance = max(0.0, min(1.0, (pitch_val - 100.0) / 200.0 + zcr))
    features.update({"valence": valence, "arousal": arousal, "dominance": dominance})

    emotions = empty_emotion_vector()
    if valence > 0.5:
        emotions["Joy"] = valence
    else:
        emotions["Sadness"] = 1.0 - valence
    if arousal > 0.6:
        emotions["Enthusiasm"] = arousal
    if dominance > 0.6:
        emotions["Confident"] = dominance
    return emotions, features
