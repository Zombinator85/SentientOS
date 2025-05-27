from typing import Dict, List
from emotions import empty_emotion_vector

MAX_HISTORY = 5
_history: List[Dict[str, float]] = []


def add_emotion(vec: Dict[str, float]) -> None:
    """Add an emotion vector to rolling history."""
    if not vec:
        return
    _history.append(vec)
    if len(_history) > MAX_HISTORY:
        del _history[:-MAX_HISTORY]


def average_emotion() -> Dict[str, float]:
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
