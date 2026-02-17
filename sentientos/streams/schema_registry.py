"""Schema registry and compatibility gates for event envelopes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

PRESSURE_PAYLOAD_FIELDS = (
    "signal_type",
    "as_of_date",
    "window_days",
    "severity",
    "counts",
    "source",
    "enqueued_at",
    "created_at",
    "last_reviewed_at",
    "next_review_due_at",
    "status",
    "closure_reason",
    "closure_note",
    "review_count",
    "persistence_count",
    "reviewed_at",
    "closed_at",
    "actor",
)

_PRESSURE_EVENT_TYPES = (
    "pressure_enqueue",
    "pressure_acknowledged",
    "pressure_revalidated",
    "pressure_closed",
    "pressure_expired",
)

_DRIFT_EVENT_TYPES = ("drift_day",)
_PERCEPTION_EVENT_TYPES = ("perception.screen", "perception.audio", "perception.vision", "perception.gaze")

_BASE_REQUIRED_ENVELOPE_KEYS = (
    "stream",
    "schema_version",
    "event_id",
    "event_type",
    "timestamp",
    "payload",
)

_DRIFT_PAYLOAD_FIELDS = (
    "date",
    "posture_stuck",
    "plugin_dominance",
    "motion_starvation",
    "anomaly_trend",
    "summary_counts",
    "source_hash",
)

_PERCEPTION_PAYLOAD_FIELDS = (
    "event_type",
    "timestamp",
    "source",
    "extractor_id",
    "extractor_version",
    "confidence",
    "privacy_class",
    "provenance",
    "active_app",
    "window_title",
    "window_class",
    "process_name",
    "browser_domain",
    "browser_url_full",
    "focused_element_hint",
    "ui_context",
    "text_excerpt",
    "cursor_position",
    "screen_geometry",
    "raw_artifact_retained",
    "redaction_applied",
    "redaction_notes",
    "degraded",
    "degradation_reason",
    "sample_rate_hz",
    "window_ms",
    "features",
    "clipping_detected",
    "channel_count",
    "device_hint",
    "raw_audio_retained",
    "redaction_applied",
    "raw_audio_reference",
    "frame_size",
    "fps_estimate",
    "faces_detected",
    "raw_frame_retained",
    "raw_frame_reference",
    "lighting_score",
    "motion_score",
    "gaze_point_norm",
    "gaze_point_px",
    "gaze_vector",
    "calibration_state",
    "calibration_confidence",
    "source_pipeline",
    "screen_id",
    "display_geometry",
    "raw_samples_retained",
    "raw_samples_reference",
)


@dataclass(frozen=True)
class StreamSchemaVersion:
    version: int
    required_envelope_keys: frozenset[str]
    required_payload_keys: Mapping[str, frozenset[str]]
    allowed_payload_keys: Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class StreamSchemaRegistry:
    stream: str
    current_version: int
    versions: Mapping[int, StreamSchemaVersion]


def _pressure_schema_versions() -> Mapping[int, StreamSchemaVersion]:
    required_payload = frozenset({"signal_type", "window_days", "severity", "counts", "source", "enqueued_at"})
    allowed_payload = frozenset(PRESSURE_PAYLOAD_FIELDS)
    per_event_required = {event_type: required_payload for event_type in _PRESSURE_EVENT_TYPES}
    per_event_allowed = {event_type: allowed_payload for event_type in _PRESSURE_EVENT_TYPES}
    return {
        1: StreamSchemaVersion(
            version=1,
            required_envelope_keys=frozenset(_BASE_REQUIRED_ENVELOPE_KEYS),
            required_payload_keys=per_event_required,
            allowed_payload_keys=per_event_allowed,
        ),
        2: StreamSchemaVersion(
            version=2,
            required_envelope_keys=frozenset(_BASE_REQUIRED_ENVELOPE_KEYS),
            required_payload_keys=per_event_required,
            allowed_payload_keys=per_event_allowed,
        ),
    }


def _drift_schema_versions() -> Mapping[int, StreamSchemaVersion]:
    required_payload_v1 = frozenset(
        {"date", "posture_stuck", "plugin_dominance", "motion_starvation", "anomaly_trend"}
    )
    required_payload_v2 = frozenset(
        {
            "date",
            "posture_stuck",
            "plugin_dominance",
            "motion_starvation",
            "anomaly_trend",
            "summary_counts",
        }
    )
    allowed_payload = frozenset(_DRIFT_PAYLOAD_FIELDS)
    per_event_required_v1 = {event_type: required_payload_v1 for event_type in _DRIFT_EVENT_TYPES}
    per_event_required_v2 = {event_type: required_payload_v2 for event_type in _DRIFT_EVENT_TYPES}
    per_event_allowed = {event_type: allowed_payload for event_type in _DRIFT_EVENT_TYPES}
    return {
        1: StreamSchemaVersion(
            version=1,
            required_envelope_keys=frozenset(_BASE_REQUIRED_ENVELOPE_KEYS),
            required_payload_keys=per_event_required_v1,
            allowed_payload_keys=per_event_allowed,
        ),
        2: StreamSchemaVersion(
            version=2,
            required_envelope_keys=frozenset(_BASE_REQUIRED_ENVELOPE_KEYS),
            required_payload_keys=per_event_required_v2,
            allowed_payload_keys=per_event_allowed,
        ),
    }


def _perception_schema_versions() -> Mapping[int, StreamSchemaVersion]:
    required_payload = frozenset(
        {
            "event_type",
            "timestamp",
            "source",
            "extractor_id",
            "extractor_version",
            "confidence",
            "privacy_class",
            "provenance",
        }
    )
    allowed_payload = frozenset(_PERCEPTION_PAYLOAD_FIELDS)
    audio_required_payload = frozenset(
        {
            "event_type",
            "timestamp",
            "source",
            "extractor_id",
            "extractor_version",
            "confidence",
            "privacy_class",
            "provenance",
            "sample_rate_hz",
            "window_ms",
            "features",
            "clipping_detected",
            "channel_count",
            "raw_audio_retained",
            "redaction_applied",
        }
    )
    per_event_required = {
        "perception.screen": required_payload,
        "perception.audio": audio_required_payload,
        "perception.vision": frozenset(
            {
                "event_type",
                "timestamp",
                "source",
                "extractor_id",
                "extractor_version",
                "confidence",
                "privacy_class",
                "provenance",
                "frame_size",
                "fps_estimate",
                "faces_detected",
                "features",
                "raw_frame_retained",
                "redaction_applied",
            }
        ),
        "perception.gaze": frozenset(
            {
                "event_type",
                "timestamp",
                "source",
                "extractor_id",
                "extractor_version",
                "confidence",
                "privacy_class",
                "provenance",
                "gaze_point_norm",
                "calibration_state",
                "source_pipeline",
                "raw_samples_retained",
                "redaction_applied",
            }
        ),
    }
    per_event_allowed = {event_type: allowed_payload for event_type in _PERCEPTION_EVENT_TYPES}
    return {
        1: StreamSchemaVersion(
            version=1,
            required_envelope_keys=frozenset(_BASE_REQUIRED_ENVELOPE_KEYS),
            required_payload_keys=per_event_required,
            allowed_payload_keys=per_event_allowed,
        )
    }


_STREAM_REGISTRY = {
    "pressure": StreamSchemaRegistry(stream="pressure", current_version=2, versions=_pressure_schema_versions()),
    "drift": StreamSchemaRegistry(stream="drift", current_version=2, versions=_drift_schema_versions()),
    "perception": StreamSchemaRegistry(stream="perception", current_version=1, versions=_perception_schema_versions()),
}


def current_schema_version(stream: str) -> int:
    return _registry_for(stream).current_version


def previous_schema_version(stream: str) -> int:
    current = current_schema_version(stream)
    return max(1, current - 1)


def upgrade_envelope(envelope: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(envelope, Mapping):
        raise ValueError("envelope must be a mapping")
    stream = envelope.get("stream")
    if not isinstance(stream, str) or not stream:
        raise ValueError("envelope stream must be a non-empty string")
    registry = _registry_for(stream)
    schema_version = envelope.get("schema_version")
    if not isinstance(schema_version, int):
        raise ValueError(f"{stream} envelope schema_version must be an int")
    if schema_version == registry.current_version:
        normalized = dict(envelope)
        _validate_envelope(normalized, registry.versions[schema_version])
        return normalized
    if schema_version == registry.current_version - 1:
        upgraded = _upgrade_prior_envelope(envelope, registry)
        _validate_envelope(upgraded, registry.versions[registry.current_version])
        return upgraded
    raise ValueError(
        f"{stream} envelope schema_version {schema_version} is outside the {registry.current_version - 1}-"
        f"{registry.current_version} compatibility window"
    )


def _registry_for(stream: str) -> StreamSchemaRegistry:
    registry = _STREAM_REGISTRY.get(stream)
    if registry is None:
        raise ValueError(f"unknown stream '{stream}'")
    return registry


def _upgrade_prior_envelope(envelope: Mapping[str, object], registry: StreamSchemaRegistry) -> dict[str, object]:
    if registry.stream == "pressure":
        return _upgrade_pressure_v1_to_v2(envelope, registry.current_version)
    if registry.stream == "drift":
        return _upgrade_drift_v1_to_v2(envelope, registry.current_version)
    raise ValueError(f"no upgrade shim available for stream '{registry.stream}'")


def _upgrade_pressure_v1_to_v2(envelope: Mapping[str, object], current_version: int) -> dict[str, object]:
    upgraded = dict(envelope)
    upgraded["schema_version"] = current_version
    return upgraded


def _upgrade_drift_v1_to_v2(envelope: Mapping[str, object], current_version: int) -> dict[str, object]:
    upgraded = dict(envelope)
    upgraded["schema_version"] = current_version
    payload = _coerce_payload(upgraded)
    if "summary_counts" not in payload:
        flags_total = sum(
            bool(payload.get(flag))
            for flag in ("posture_stuck", "plugin_dominance", "motion_starvation", "anomaly_trend")
        )
        payload["summary_counts"] = {"flags_total": flags_total}
    upgraded["payload"] = payload
    return upgraded


def _coerce_payload(envelope: Mapping[str, object]) -> dict[str, object]:
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("envelope payload must be a mapping")
    return dict(payload)


def _validate_envelope(envelope: Mapping[str, object], schema: StreamSchemaVersion) -> None:
    _require_keys(envelope, schema.required_envelope_keys, "envelope")
    event_type = envelope.get("event_type")
    if not isinstance(event_type, str) or not event_type:
        raise ValueError("envelope event_type must be a non-empty string")
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("envelope payload must be a mapping")
    required_payload = schema.required_payload_keys.get(event_type)
    allowed_payload = schema.allowed_payload_keys.get(event_type)
    if required_payload is None or allowed_payload is None:
        raise ValueError(f"unknown event_type '{event_type}' for stream '{envelope.get('stream')}'")
    payload_keys = set(payload.keys())
    missing_payload = required_payload - payload_keys
    if missing_payload:
        raise ValueError(f"payload missing required keys: {', '.join(sorted(missing_payload))}")
    extra_payload = payload_keys - allowed_payload
    if extra_payload:
        raise ValueError(f"payload has unexpected keys: {', '.join(sorted(extra_payload))}")


def _require_keys(data: Mapping[str, object], required: frozenset[str], label: str) -> None:
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{label} missing required keys: {', '.join(sorted(missing))}")


__all__ = [
    "PRESSURE_PAYLOAD_FIELDS",
    "current_schema_version",
    "previous_schema_version",
    "upgrade_envelope",
]
