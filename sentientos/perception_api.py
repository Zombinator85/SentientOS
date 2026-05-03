"""Non-authoritative perception telemetry facade.

This module normalizes legacy perception observations into explicit, privacy-aware
telemetry envelopes. It does not admit, execute, route, or authorize work.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

DEFAULT_SCHEMA = "perception.telemetry.v1"


def build_perception_event(
    modality: str,
    observation: Mapping[str, Any],
    *,
    source: str,
    raw_retention: bool = False,
    privacy: str = "sensitive",
    can_trigger_actions: bool = False,
    can_write_memory: bool = False,
    legacy: bool = True,
) -> dict[str, Any]:
    """Build a pulse-compatible perception telemetry envelope.

    The event is metadata-only and explicitly non-authoritative.
    """
    return {
        "schema": DEFAULT_SCHEMA,
        "timestamp": float(observation.get("timestamp", time.time())),
        "source": source,
        "modality": modality,
        "observation": dict(observation),
        "authority": "none",
        "telemetry_only": True,
        "privacy": privacy,
        "raw_retention": bool(raw_retention),
        "can_trigger_actions": bool(can_trigger_actions),
        "can_write_memory": bool(can_write_memory),
        "legacy_surface": bool(legacy),
    }


def normalize_screen_observation(*, text: str, ocr_confidence: float | None, width: int | None, height: int | None, timestamp: float | None = None) -> dict[str, Any]:
    return {
        "timestamp": float(timestamp or time.time()),
        "text": text,
        "ocr_confidence": ocr_confidence,
        "width": width,
        "height": height,
    }


def normalize_audio_observation(*, message: str | None, source: str, audio_file: str | None, emotion_features: Mapping[str, float] | None = None, timestamp: float | None = None) -> dict[str, Any]:
    return {
        "timestamp": float(timestamp or time.time()),
        "message": message,
        "source": source,
        "audio_file": audio_file,
        "emotion_features": dict(emotion_features or {}),
    }


def normalize_vision_observation(*, faces: list[dict[str, Any]], timestamp: float | None = None) -> dict[str, Any]:
    return {"timestamp": float(timestamp or time.time()), "faces": faces}


def normalize_multimodal_observation(*, timestamp: float, vision: Mapping[str, Any], voice: Mapping[str, Any], scene: Mapping[str, Any] | None = None, screen: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"timestamp": timestamp, "vision": dict(vision), "voice": dict(voice)}
    if scene is not None:
        payload["scene"] = dict(scene)
    if screen is not None:
        payload["screen"] = dict(screen)
    return payload


def build_feedback_observation(*, user: int, emotion: str, value: float, action: str, timestamp: float | None = None) -> dict[str, Any]:
    return {
        "timestamp": float(timestamp or time.time()),
        "user": user,
        "emotion": emotion,
        "value": value,
        "action": action,
    }


def quarantine_legacy_perception_event(modality: str, observation: Mapping[str, Any], *, source: str, risk: str) -> dict[str, Any]:
    event = build_perception_event(modality, observation, source=source)
    event["legacy_quarantine"] = True
    event["quarantine_risk"] = risk
    return event


__all__ = [
    "build_perception_event",
    "normalize_screen_observation",
    "normalize_audio_observation",
    "normalize_vision_observation",
    "normalize_multimodal_observation",
    "build_feedback_observation",
    "quarantine_legacy_perception_event",
]
