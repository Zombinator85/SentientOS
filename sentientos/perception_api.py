"""Non-authoritative perception telemetry facade.

This module normalizes legacy perception observations into explicit, privacy-aware
telemetry envelopes. It does not admit, execute, route, schedule, or authorize work.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

DEFAULT_SCHEMA = "perception.telemetry.v2"
PULSE_COMPAT_EVENT_TYPE_PREFIX = "perception.legacy"


def perception_event_source_ref(source_module: str, *, legacy: bool = True) -> str:
    return f"legacy:{source_module}" if legacy else source_module


def build_pulse_compatible_perception_event(
    modality: str,
    observation: Mapping[str, Any],
    *,
    source_module: str,
    raw_retention: bool = False,
    privacy_class: str = "sensitive",
    can_trigger_actions: bool = False,
    can_write_memory: bool = False,
    legacy_quarantine: bool = False,
    quarantine_risk: str | None = None,
) -> dict[str, Any]:
    timestamp = float(observation.get("timestamp", time.time()))
    event = {
        "schema": DEFAULT_SCHEMA,
        "event_type": f"{PULSE_COMPAT_EVENT_TYPE_PREFIX}.{modality}",
        "timestamp": timestamp,
        "source": perception_event_source_ref(source_module),
        "source_module": source_module,
        "extractor_id": "legacy_perception_bridge",
        "extractor_version": "phase42",
        "modality": modality,
        "observation": dict(observation),
        "privacy_class": privacy_class,
        "raw_retention": bool(raw_retention),
        "authority": "none",
        "telemetry_only": True,
        "can_trigger_actions": bool(can_trigger_actions),
        "can_write_memory": bool(can_write_memory),
        "legacy_surface": True,
        "legacy_quarantine": bool(legacy_quarantine),
        "provenance": {"bridge": "sentientos.perception_api", "non_authoritative": True},
    }
    if quarantine_risk:
        event["quarantine_risk"] = quarantine_risk
    return event


def publish_perception_telemetry(event: Mapping[str, Any], *, publisher: Callable[[dict[str, Any]], Any] | None = None) -> bool:
    payload = dict(event)
    if publisher is not None:
        publisher(payload)
        return True
    return False


def maybe_publish_legacy_perception_event(
    modality: str,
    observation: Mapping[str, Any],
    *,
    source_module: str,
    raw_retention: bool = False,
    privacy_class: str = "sensitive",
    can_trigger_actions: bool = False,
    can_write_memory: bool = False,
    legacy_quarantine: bool = False,
    quarantine_risk: str | None = None,
    publisher: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    event = build_pulse_compatible_perception_event(
        modality,
        observation,
        source_module=source_module,
        raw_retention=raw_retention,
        privacy_class=privacy_class,
        can_trigger_actions=can_trigger_actions,
        can_write_memory=can_write_memory,
        legacy_quarantine=legacy_quarantine,
        quarantine_risk=quarantine_risk,
    )
    publish_perception_telemetry(event, publisher=publisher)
    return event


def emit_legacy_perception_telemetry(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return maybe_publish_legacy_perception_event(*args, **kwargs)


def build_perception_event(modality: str, observation: Mapping[str, Any], *, source: str, raw_retention: bool = False, privacy: str = "sensitive", can_trigger_actions: bool = False, can_write_memory: bool = False, legacy: bool = True) -> dict[str, Any]:
    return build_pulse_compatible_perception_event(modality, observation, source_module=source, raw_retention=raw_retention, privacy_class=privacy, can_trigger_actions=can_trigger_actions, can_write_memory=can_write_memory, legacy_quarantine=legacy)


def normalize_screen_observation(*, text: str, ocr_confidence: float | None, width: int | None, height: int | None, timestamp: float | None = None) -> dict[str, Any]:
    return {"timestamp": float(timestamp or time.time()), "text": text, "ocr_confidence": ocr_confidence, "width": width, "height": height}


def normalize_audio_observation(*, message: str | None, source: str, audio_file: str | None, emotion_features: Mapping[str, float] | None = None, timestamp: float | None = None) -> dict[str, Any]:
    return {"timestamp": float(timestamp or time.time()), "message": message, "source": source, "audio_file": audio_file, "emotion_features": dict(emotion_features or {})}


def normalize_vision_observation(*, faces: list[dict[str, Any]], timestamp: float | None = None) -> dict[str, Any]:
    return {"timestamp": float(timestamp or time.time()), "faces": faces}


def normalize_multimodal_observation(*, timestamp: float, vision: Mapping[str, Any], voice: Mapping[str, Any], scene: Mapping[str, Any] | None = None, screen: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"timestamp": timestamp, "vision": dict(vision), "voice": dict(voice), "source_modalities": ["vision", "voice"]}
    if scene is not None:
        payload["scene"] = dict(scene)
        payload["source_modalities"].append("scene")
    if screen is not None:
        payload["screen"] = dict(screen)
        payload["source_modalities"].append("screen")
    return payload


def build_feedback_observation(*, user: int, emotion: str, value: float, action: str, timestamp: float | None = None) -> dict[str, Any]:
    return {"timestamp": float(timestamp or time.time()), "user": user, "emotion": emotion, "value": value, "action": action, "action_approved": False}


def normalize_perception_correlation_id(event: Mapping[str, Any]) -> str | None:
    value = event.get("correlation_id")
    if value is None and isinstance(event.get("observation"), Mapping):
        value = event["observation"].get("correlation_id")
    return str(value) if value not in (None, "") else None


def normalize_perception_risk_flags(event: Mapping[str, Any]) -> dict[str, bool]:
    modality = str(event.get("modality", ""))
    return {
        "can_trigger_actions": bool(event.get("can_trigger_actions", False)),
        "can_write_memory": bool(event.get("can_write_memory", False)),
        "biometric_or_emotion_sensitive": modality in {"audio", "vision", "feedback", "multimodal", "gaze"},
    }


def quarantine_legacy_perception_event(modality: str, observation: Mapping[str, Any], *, source: str, risk: str) -> dict[str, Any]:
    return build_pulse_compatible_perception_event(modality, observation, source_module=source, legacy_quarantine=True, quarantine_risk=risk)


__all__ = [
    "build_perception_event",
    "build_pulse_compatible_perception_event",
    "publish_perception_telemetry",
    "emit_legacy_perception_telemetry",
    "maybe_publish_legacy_perception_event",
    "perception_event_source_ref",
    "normalize_screen_observation",
    "normalize_audio_observation",
    "normalize_vision_observation",
    "normalize_multimodal_observation",
    "build_feedback_observation",
    "quarantine_legacy_perception_event",
    "normalize_perception_correlation_id",
    "normalize_perception_risk_flags",
]
