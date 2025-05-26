from typing import Dict, Tuple
try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None

try:
    import librosa  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    librosa = None

try:
    import torch  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    torch = None

from emotions import empty_emotion_vector


class _SimpleEmotionNet:
    """Tiny neural net mapping audio features to VAD."""

    def __init__(self):
        if torch is not None:  # pragma: no cover - only runs if torch is present
            self.fc1_weight = torch.tensor(
                [[0.5, -0.3, 0.1, 0.2], [-0.4, 0.6, 0.2, -0.1], [0.3, 0.2, 0.5, 0.4]]
            )
            self.fc1_bias = torch.tensor([0.0, 0.0, 0.0])
        else:
            self.fc1_weight = None
            self.fc1_bias = None

    def __call__(self, feats: "np.ndarray | list[float]") -> Tuple[float, float, float]:
        if torch is None or self.fc1_weight is None or np is None:
            return 0.0, 0.0, 0.0
        x = torch.tensor(feats, dtype=torch.float32)
        out = torch.tanh(torch.matmul(self.fc1_weight, x) + self.fc1_bias)
        v, a, d = out.tolist()
        v = float(max(-1.0, min(1.0, v)))
        a = float(max(0.0, min(1.0, (a + 1) / 2)))
        d = float(max(0.0, min(1.0, (d + 1) / 2)))
        return v, a, d


_MODEL = _SimpleEmotionNet()


def extract_features(path: str) -> "np.ndarray | list[float]":
    """Return basic audio features [energy, zcr, centroid, pitch]."""
    if librosa is None or np is None:  # pragma: no cover - no optional deps
        return [0.0, 0.0, 0.0, 0.0]
    y, sr = librosa.load(path, sr=16000)
    energy = float(np.mean(librosa.feature.rms(y=y)))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    pitches, _ = librosa.piptrack(y=y, sr=sr)
    pitch = float(np.mean(pitches[pitches > 0])) if np.any(pitches > 0) else 0.0
    if np is None:
        return [energy, zcr, centroid, pitch]
    return np.array([energy, zcr, centroid, pitch], dtype=float)


def predict_vad(path: str) -> Tuple[float, float, float]:
    """Predict valence, arousal, dominance from audio file."""
    feats = extract_features(path)
    v, a, d = _MODEL(feats)
    return v, a, d


def vad_to_epu(valence: float, arousal: float, dominance: float) -> Dict[str, float]:
    """Map VAD values to 64-dim emotion vector."""
    vec = empty_emotion_vector()
    if valence > 0.2:
        vec["Joy"] = valence
    if valence < -0.2:
        vec["Sadness"] = abs(valence)
    if arousal > 0.6 and valence > 0:
        vec["Enthusiasm"] = (arousal + valence) / 2
    if arousal > 0.6 and valence < 0:
        vec["Anger"] = (arousal + abs(valence)) / 2
    if dominance > 0.6:
        vec["Confident"] = dominance
    return vec


def vad_and_features(path: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Return (EPV vector, raw feature dict) for ``path``."""
    v, a, d = predict_vad(path)
    vec = vad_to_epu(v, a, d)
    features = {"valence": v, "arousal": a, "dominance": d}
    return vec, features
