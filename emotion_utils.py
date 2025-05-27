import os
from typing import Dict, Tuple

try:
    import numpy as np  # type: ignore
    import librosa  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None
    librosa = None

from emotions import empty_emotion_vector

# Name of the emotion detection backend. "heuristic" uses
# :func:`vad_and_features`, "neural" uses :func:`neural_emotions`.
DETECTOR = os.getenv("EMOTION_DETECTOR", "heuristic")


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


def _map_vad_to_epu(valence: float, arousal: float, dominance: float) -> Dict[str, float]:
    """Map valence, arousal, dominance to the canonical emotion vector."""
    vec = empty_emotion_vector()
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
    return vec


def neural_emotions(path: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Lightweight neural-ish emotion classifier.

    This is intentionally simple so that tests run quickly. It mimics a neural
    network using MFCC features and some fixed weights.
    """
    vec = empty_emotion_vector()
    features: Dict[str, float] = {}
    if librosa is None or np is None or not os.path.exists(path):
        return vec, features

    try:
        y, sr = librosa.load(path, sr=16000)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        rms = float(np.mean(librosa.feature.rms(y=y)))
        pitch = float(np.mean(librosa.yin(y, fmin=50, fmax=300)))
        features.update({"rms": rms, "pitch": pitch})

        # toy weights converting MFCC mean values to V/A/D
        w = np.linspace(0.1, 0.3, mfcc.shape[0])
        mfcc_mean = np.mean(mfcc, axis=1)
        score = float(np.dot(w, mfcc_mean) / (np.sum(w) + 1e-6))
        valence = max(0.0, min(1.0, (score + 200) / 400))
        arousal = max(0.0, min(1.0, (rms * 2)))
        dominance = max(0.0, min(1.0, (pitch - 50) / 250))
        vec = _map_vad_to_epu(valence, arousal, dominance)
    except Exception:
        pass

    return vec, features


LEXICON = {
    "happy": "Joy",
    "sad": "Sadness",
    "angry": "Anger",
    "love": "Love",
    "fear": "Fear",
}


def text_sentiment(text: str) -> Dict[str, float]:
    """Very small lexicon-based sentiment lookup."""
    vec = empty_emotion_vector()
    words = text.lower().split()
    for w in words:
        label = LEXICON.get(w)
        if label:
            vec[label] = max(vec.get(label, 0.0), 0.8)
    return vec


def fuse(audio_vec: Dict[str, float], text_vec: Dict[str, float]) -> Dict[str, float]:
    """Fuse audio and text emotion vectors."""
    out = empty_emotion_vector()
    for k in out.keys():
        out[k] = max(audio_vec.get(k, 0.0), text_vec.get(k, 0.0))
    return out


def detect(path: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Dispatch to the configured emotion detector."""
    if DETECTOR == "neural":
        return neural_emotions(path)
    return vad_and_features(path)
