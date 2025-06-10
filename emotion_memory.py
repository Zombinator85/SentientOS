from typing import Dict, List
from emotions import Emotion, empty_emotion_vector

MAX_HISTORY = 5
_history: List[Emotion] = []

def add_emotion(vec: Emotion) -> None:
    """Add an emotion vector to rolling history."""
    if not vec:
        return
    _history.append(vec)
    if len(_history) > MAX_HISTORY:
        del _history[:-MAX_HISTORY]

def average_emotion() -> Emotion:
    """Return the average emotion vector."""
    avg = empty_emotion_vector()
    if not _history:
        return avg
    for h in _history:
        for k, v in h.items():
            avg[k] = avg.get(k, 0.0) + v
    for k in avg:
        avg[k] /= len(_history)
    return avg

def clear() -> None:
    _history.clear()

def trend() -> Emotion:
    """Return change in average emotion over time."""
    if len(_history) < 2:
        return empty_emotion_vector()
    mid = len(_history) // 2
    first = _history[:mid]
    second = _history[mid:]

    def _avg(vecs: List[Emotion]) -> Emotion:
        out = empty_emotion_vector()
        for v in vecs:
            for k, val in v.items():
                out[k] = out.get(k, 0.0) + val
        for k in out:
            out[k] /= len(vecs)
        return out

    a1 = _avg(first)
    a2 = _avg(second)
    delta = empty_emotion_vector()
    for k in delta:
        delta[k] = a2.get(k, 0.0) - a1.get(k, 0.0)
    return delta
