"""Persistence helpers for autonomy runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Mapping, MutableMapping, Optional


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class MoodSnapshot:
    mood: str
    baseline: str
    vector: MutableMapping[str, float] = field(default_factory=dict)


class MoodStateManager:
    def __init__(self, path: Path, *, restore: bool = True, decay_factor: float = 0.8) -> None:
        self._path = path
        _ensure_parent(self._path)
        self._restore = restore
        self._decay = max(0.0, min(float(decay_factor), 1.0))
        self._snapshot: MoodSnapshot | None = None

    def load(self, baseline: str) -> MoodSnapshot:
        baseline_normalised = (baseline or "neutral").strip().lower()
        if self._restore and self._path.exists():
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                mood = str(payload.get("mood", baseline_normalised)).strip().lower()
                vector = {
                    key: float(value)
                    for key, value in (payload.get("vector", {}) or {}).items()
                }
                self._snapshot = MoodSnapshot(mood=mood, baseline=baseline_normalised, vector=vector)
                return self._snapshot
            except Exception:
                pass
        self._snapshot = MoodSnapshot(mood=baseline_normalised, baseline=baseline_normalised)
        return self._snapshot

    def current_mood(self) -> Optional[str]:
        if not self._snapshot:
            return None
        return self._snapshot.mood

    def update(self, mood: str, vector: Mapping[str, float] | None = None) -> MoodSnapshot:
        if not self._snapshot:
            self._snapshot = MoodSnapshot(mood=mood, baseline=mood)
        mood_clean = (mood or self._snapshot.baseline).strip().lower()
        self._snapshot.mood = mood_clean
        if vector:
            for key, value in vector.items():
                existing = self._snapshot.vector.get(key, 0.0)
                blended = existing * self._decay + float(value) * (1.0 - self._decay)
                self._snapshot.vector[key] = blended
        return self._snapshot

    def save(self) -> None:
        if not self._snapshot:
            return
        payload = {
            "mood": self._snapshot.mood,
            "baseline": self._snapshot.baseline,
            "vector": self._snapshot.vector,
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def reset(self) -> None:
        self._snapshot = None
        if self._path.exists():
            self._path.unlink()


@dataclass
class ContinuitySnapshot:
    """Serializable representation of autonomy session continuity state."""

    mood: Optional[str] = None
    readiness: Optional[Mapping[str, object]] = None
    curiosity_queue: list[Mapping[str, object]] = field(default_factory=list)
    curiosity_inflight: list[Mapping[str, object]] = field(default_factory=list)
    last_readiness_ts: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "mood": self.mood,
            "readiness": self.readiness,
            "curiosity_queue": list(self.curiosity_queue),
            "curiosity_inflight": list(self.curiosity_inflight),
            "last_readiness_ts": self.last_readiness_ts,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object] | None) -> "ContinuitySnapshot":
        if not payload:
            return cls()
        return cls(
            mood=payload.get("mood"),
            readiness=payload.get("readiness"),
            curiosity_queue=list(payload.get("curiosity_queue", []) or []),
            curiosity_inflight=list(payload.get("curiosity_inflight", []) or []),
            last_readiness_ts=payload.get("last_readiness_ts"),
        )


class ContinuityStateManager:
    """Load and persist the autonomy continuity snapshot."""

    def __init__(self, path: Path) -> None:
        self._path = path
        _ensure_parent(self._path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> ContinuitySnapshot:
        if not self._path.exists():
            return ContinuitySnapshot()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return ContinuitySnapshot()
        return ContinuitySnapshot.from_mapping(data)

    def save(self, snapshot: ContinuitySnapshot) -> Path:
        payload = snapshot.to_dict()
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return self._path

    def clear(self) -> None:
        self._path.unlink(missing_ok=True)


__all__ = [
    "MoodSnapshot",
    "MoodStateManager",
    "ContinuitySnapshot",
    "ContinuityStateManager",
]

