"""Persistence helpers for autonomy runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional

import hashlib

from sentientos.gradient_contract import enforce_no_gradient_fields, GradientInvariantViolation


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
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive path
            raise SnapshotDivergenceError("continuity snapshot unreadable") from exc

        snapshot_payload, stored_digest = _extract_snapshot_payload(payload)
        enforce_no_gradient_fields(snapshot_payload, context="continuity_state.load")
        canonical = canonicalise_continuity_snapshot(snapshot_payload)
        enforce_no_gradient_fields(canonical, context="continuity_state.load")
        computed_digest = continuity_snapshot_digest(canonical)
        if not stored_digest:
            raise SnapshotDivergenceError("continuity snapshot missing digest")
        if stored_digest != computed_digest:
            raise SnapshotDivergenceError("continuity snapshot digest mismatch")
        return ContinuitySnapshot.from_mapping(canonical)

    def save(self, snapshot: ContinuitySnapshot) -> Path:
        raw_payload = snapshot.to_dict()
        enforce_no_gradient_fields(raw_payload, context="continuity_state.save")
        canonical = canonicalise_continuity_snapshot(raw_payload)
        enforce_no_gradient_fields(canonical, context="continuity_state.save")
        digest = continuity_snapshot_digest(canonical)
        stored = {"snapshot": canonical, "digest": digest}
        self._path.write_text(
            json.dumps(stored, ensure_ascii=False, indent=2) + "\n",
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
    "SnapshotDivergenceError",
    "canonicalise_continuity_snapshot",
    "continuity_snapshot_digest",
]


class SnapshotDivergenceError(RuntimeError):
    """Raised when a persisted continuity snapshot cannot be trusted."""


_ALLOWED_ROOT_FIELDS: tuple[str, ...] = (
    "mood",
    "readiness",
    "curiosity_queue",
    "curiosity_inflight",
    "last_readiness_ts",
)

_READINESS_FIELDS: tuple[str, ...] = (
    "summary",
    "report",
    "timestamp",
    "status",
)

_CURIOUS_FIELDS: tuple[str, ...] = (
    "goal",
    "observation",
    "created_at",
    "source",
    "status",
    "id",
)


def canonicalise_continuity_snapshot(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    if snapshot is None or not isinstance(snapshot, Mapping):
        raise SnapshotDivergenceError("continuity snapshot must be a mapping")

    canonical: dict[str, Any] = {
        "mood": _canonical_value(snapshot.get("mood"), path=("mood",)),
        "readiness": _canonical_value(
            snapshot.get("readiness"), path=("readiness",), allowed_keys=_READINESS_FIELDS
        ),
        "curiosity_queue": _canonical_value(
            snapshot.get("curiosity_queue", []) or [], path=("curiosity_queue",), allowed_keys=_CURIOUS_FIELDS
        ),
        "curiosity_inflight": _canonical_value(
            snapshot.get("curiosity_inflight", []) or [],
            path=("curiosity_inflight",),
            allowed_keys=_CURIOUS_FIELDS,
        ),
        "last_readiness_ts": _canonical_value(
            snapshot.get("last_readiness_ts"), path=("last_readiness_ts",)
        ),
    }
    return canonical


def continuity_snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    serialised = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _extract_snapshot_payload(
    payload: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any], str | None]:
    if payload is None or not isinstance(payload, Mapping):
        raise SnapshotDivergenceError("continuity snapshot payload must be a mapping")
    if "snapshot" in payload and isinstance(payload.get("snapshot"), Mapping):
        snapshot_payload = payload["snapshot"]
        digest = payload.get("digest")
    else:
        digest = payload.get("digest")
        snapshot_payload = {key: value for key, value in payload.items() if key != "digest"}
    digest_str = str(digest) if digest else None
    return snapshot_payload, digest_str


def _canonical_value(value: Any, *, path: tuple[str, ...], allowed_keys: tuple[str, ...] | None = None) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        filtered = (
            (str(key), val)
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
            if (path or str(key) in _ALLOWED_ROOT_FIELDS)
            and (allowed_keys is None or str(key) in allowed_keys)
        )
        return {
            key: _canonical_value(val, path=(*path, key), allowed_keys=allowed_keys)
            for key, val in filtered
        }
    if isinstance(value, (list, tuple)):
        return [
            _canonical_value(item, path=(*path, str(idx)), allowed_keys=allowed_keys)
            for idx, item in enumerate(value)
        ]
    raise SnapshotDivergenceError(
        f"non-serializable value at {' -> '.join(path) or 'root'}: {type(value).__name__}"
    )
