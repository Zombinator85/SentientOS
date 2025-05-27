import audioop
import wave
from pathlib import Path
from typing import Dict, Tuple
from emotions import empty_emotion_vector

try:
    import librosa  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    librosa = None  # type: ignore
    np = None  # type: ignore


def vad_and_features(path: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Derive an emotion vector and raw features from ``path``.

    If ``librosa``/``numpy`` are available, compute simple spectral
    features (RMS, ZCR, centroid) to estimate valence, arousal and
    dominance. Otherwise fall back to RMS volume analysis using the
    standard ``wave`` module.
    """
    p = Path(path)
    if not p.exists():
        return empty_emotion_vector(), {}

    if librosa is None or np is None:  # Fallback path
        try:
            with wave.open(str(p), "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                rms = audioop.rms(frames, wf.getsampwidth())
        except Exception:
            rms = 0
        vec = empty_emotion_vector()
        if rms < 500:
            vec["Sadness"] = 1.0
        elif rms > 3000:
            vec["Anger"] = min(1.0, (rms - 3000) / 7000)
            vec["Enthusiasm"] = 0.8
        else:
            vec["Contentment"] = 0.6
        return vec, {"rms": float(rms)}

    # librosa-based features
    try:
        y, sr = librosa.load(str(p), sr=16000)
        rms = float(librosa.feature.rms(y=y).mean())
        zcr = float(librosa.feature.zero_crossing_rate(y).mean())
        centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
    except Exception:
        return empty_emotion_vector(), {}

    features = {"rms": rms, "zcr": zcr, "centroid": centroid}

    # Rough mapping to valence/arousal/dominance
    valence = max(-1.0, min(1.0, (centroid - 1500) / 2000))
    arousal = max(0.0, min(1.0, rms * 10))
    dominance = max(0.0, min(1.0, zcr * 10))

    vec = empty_emotion_vector()
    if valence >= 0:
        vec["Joy"] = valence
    else:
        vec["Sadness"] = -valence
    vec["Enthusiasm"] = arousal
    vec["Confident"] = dominance
    return vec, features
