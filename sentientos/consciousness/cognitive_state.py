from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

from sentientos.consciousness.cognitive_posture import (
    CognitivePosture,
    DEFAULT_POSTURE_HISTORY_WINDOW,
    derive_cognitive_posture,
    derive_load_narrative,
    derive_posture_transition,
    update_posture_history,
)
from sentientos.introspection.spine import EventType, emit_introspection_event

COGNITIVE_SNAPSHOT_VERSION = 1
COGNITIVE_STATE_SNAPSHOT_SCHEMA_VERSION = COGNITIVE_SNAPSHOT_VERSION

_ALLOWED_PRESSURE_FIELDS = {
    "total_active_pressure",
    "pressure_by_subsystem",
    "phase_counts",
    "refusal_count",
    "deferred_count",
    "overload",
    "overload_domains",
    "oldest_unresolved_age",
}


def _hash_payload(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalize_snapshot_version(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def validate_cognitive_snapshot_version(
    snapshot: Mapping[str, object],
    *,
    expected_version: int | None = None,
    min_version: int | None = None,
    max_version: int | None = None,
) -> int:
    """Validate that a cognitive snapshot matches the expected schema version.

    The version is a monotonic integer that only changes when schema or
    semantic meaning changes (not for cosmetic ordering).
    """

    if expected_version is not None and (min_version is not None or max_version is not None):
        raise ValueError("Provide either expected_version or a min/max version range, not both")

    version = snapshot.get("cognitive_snapshot_version")
    if version is None:
        raise ValueError("Snapshot missing cognitive_snapshot_version")

    normalized_version = _normalize_snapshot_version(version, field_name="cognitive_snapshot_version")

    if expected_version is not None:
        normalized_expected = _normalize_snapshot_version(expected_version, field_name="expected_version")
        if normalized_version != normalized_expected:
            raise ValueError(
                f"Snapshot version {normalized_version} does not match expected {normalized_expected}"
            )
        return normalized_version

    if min_version is not None:
        normalized_min = _normalize_snapshot_version(min_version, field_name="min_version")
        if normalized_version < normalized_min:
            raise ValueError(
                f"Snapshot version {normalized_version} is below minimum supported {normalized_min}"
            )

    if max_version is not None:
        normalized_max = _normalize_snapshot_version(max_version, field_name="max_version")
        if normalized_version > normalized_max:
            raise ValueError(
                f"Snapshot version {normalized_version} exceeds maximum supported {normalized_max}"
            )

    return normalized_version


def _normalize_posture(value: str | CognitivePosture | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, CognitivePosture):
        return value.value
    if isinstance(value, str) and value.strip():
        normalized = value.strip().lower()
        if normalized in {posture.value for posture in CognitivePosture}:
            return normalized
    return None


def _coerce_int(value: object, *, default: int | None = 0) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return default


def _normalize_pressure_snapshot(snapshot: Mapping[str, object] | None) -> dict[str, object] | None:
    if snapshot is None:
        return None
    if not isinstance(snapshot, Mapping):
        raise TypeError("pressure_snapshot must be a mapping if provided")

    phase_counts_raw = snapshot.get("phase_counts")
    phase_counts: dict[str, int] = {}
    if isinstance(phase_counts_raw, Mapping):
        for key, value in phase_counts_raw.items():
            phase_counts[str(key)] = int(_coerce_int(value, default=0) or 0)

    pressure_by_subsystem: list[dict[str, object]] = []
    pressure_items = snapshot.get("pressure_by_subsystem")
    if isinstance(pressure_items, (list, tuple)):
        for item in pressure_items:
            if not isinstance(item, Mapping):
                continue
            subsystem = item.get("subsystem")
            if subsystem is None:
                continue
            count = _coerce_int(item.get("count"), default=0)
            pressure_by_subsystem.append({
                "subsystem": str(subsystem),
                "count": int(count or 0),
            })
    pressure_by_subsystem.sort(key=lambda entry: entry.get("subsystem", ""))

    overload_domains: list[dict[str, object]] = []
    overload_items = snapshot.get("overload_domains")
    if isinstance(overload_items, (list, tuple)):
        for item in overload_items:
            if not isinstance(item, Mapping):
                continue
            subsystem = item.get("subsystem")
            if subsystem is None:
                continue
            outstanding = _coerce_int(item.get("outstanding"), default=0)
            overload_domains.append({
                "subsystem": str(subsystem),
                "outstanding": int(outstanding or 0),
            })
    overload_domains.sort(key=lambda entry: entry.get("subsystem", ""))

    total_active = _coerce_int(snapshot.get("total_active_pressure"), default=0)
    refusal_count = _coerce_int(snapshot.get("refusal_count"), default=0)
    deferred_count = _coerce_int(snapshot.get("deferred_count"), default=0)
    oldest_unresolved_age = _coerce_int(snapshot.get("oldest_unresolved_age"), default=None)

    sanitized = {
        "total_active_pressure": int(total_active or 0),
        "pressure_by_subsystem": pressure_by_subsystem,
        "phase_counts": dict(sorted(phase_counts.items(), key=lambda item: item[0])),
        "refusal_count": int(refusal_count or 0),
        "deferred_count": int(deferred_count or 0),
        "overload": bool(overload_domains),
        "overload_domains": overload_domains,
        "oldest_unresolved_age": oldest_unresolved_age,
    }

    pressure_hash = _hash_payload(sanitized)
    sanitized["snapshot_hash"] = pressure_hash

    for field in _ALLOWED_PRESSURE_FIELDS:
        if field not in sanitized:
            sanitized[field] = None

    return sanitized


def build_cognitive_state_snapshot(
    *,
    pressure_snapshot: Mapping[str, object] | None,
    posture_history: Sequence[str] | None = None,
    cognitive_posture: str | CognitivePosture | None = None,
    posture_history_window: int | None = DEFAULT_POSTURE_HISTORY_WINDOW,
) -> dict[str, object]:
    """Build a deterministic, read-only cognitive state snapshot."""

    sanitized_pressure = _normalize_pressure_snapshot(pressure_snapshot)
    posture_value = _normalize_posture(cognitive_posture)
    if posture_value is None and sanitized_pressure is not None:
        posture_value = derive_cognitive_posture(sanitized_pressure).value

    window_value = int(posture_history_window or 0) if posture_history_window is not None else 0
    history = update_posture_history(posture_history, posture_value, window=window_value)
    transition_data = derive_posture_transition(history)

    posture_duration = int(transition_data.get("posture_duration") or 0)
    posture_transition = transition_data.get("posture_transition")
    load_narrative = derive_load_narrative(history, transition_data).value

    snapshot: dict[str, object] = {
        "cognitive_snapshot_version": COGNITIVE_SNAPSHOT_VERSION,
        "pressure_snapshot": sanitized_pressure,
        "cognitive_posture": posture_value,
        "posture_history": list(history),
        "posture_duration": posture_duration,
        "posture_transition": posture_transition,
        "cognitive_load_narrative": load_narrative,
    }
    snapshot["snapshot_hash"] = _hash_payload(snapshot)
    emit_introspection_event(
        event_type=EventType.SNAPSHOT_EMISSION,
        phase="cognition",
        summary="Cognitive state snapshot emitted.",
        metadata={
            "snapshot_hash": snapshot.get("snapshot_hash"),
            "cognitive_posture": snapshot.get("cognitive_posture"),
            "posture_transition": snapshot.get("posture_transition"),
            "posture_duration": snapshot.get("posture_duration"),
            "pressure_snapshot_hash": (sanitized_pressure or {}).get("snapshot_hash"),
        },
        linked_artifact_ids=[str(snapshot.get("snapshot_hash", ""))],
    )
    return snapshot


__all__ = [
    "COGNITIVE_SNAPSHOT_VERSION",
    "COGNITIVE_STATE_SNAPSHOT_SCHEMA_VERSION",
    "build_cognitive_state_snapshot",
    "validate_cognitive_snapshot_version",
]
