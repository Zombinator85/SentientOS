"""Canonical non-authoritative embodiment fusion surface.

This module fuses perception telemetry into bounded embodiment snapshots. It is
strictly derived-only and never admits work, executes actions, writes memory, or
triggers feedback.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "embodiment.snapshot.v1"
SUPPORTED_MODALITIES = ("screen", "audio", "vision", "multimodal", "feedback", "gaze")
CORE_MODALITIES = {"screen", "audio", "vision", "multimodal", "feedback"}


def _normalize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    observation = event.get("observation")
    return {
        "event_type": str(event.get("event_type", "")),
        "modality": str(event.get("modality", "unknown")),
        "timestamp": float(event.get("timestamp", 0.0)),
        "source": str(event.get("source", "")),
        "source_module": str(event.get("source_module", "unknown")),
        "privacy_class": str(event.get("privacy_class", "sensitive")),
        "raw_retention": bool(event.get("raw_retention", False)),
        "can_trigger_actions": bool(event.get("can_trigger_actions", False)),
        "can_write_memory": bool(event.get("can_write_memory", False)),
        "correlation_id": event.get("correlation_id") or (observation.get("correlation_id") if isinstance(observation, Mapping) else None),
        "observation": dict(observation) if isinstance(observation, Mapping) else {},
    }


def embodiment_snapshot_source_ref(event: Mapping[str, Any]) -> str:
    normalized = _normalize_event(event)
    payload = {
        "event_type": normalized["event_type"],
        "timestamp": normalized["timestamp"],
        "source": normalized["source"],
        "source_module": normalized["source_module"],
        "modality": normalized["modality"],
        "observation": normalized["observation"],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:20]
    return f"{normalized['source_module']}:{normalized['modality']}:{digest}"


def group_perception_events_by_correlation(events: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        normalized = _normalize_event(event)
        key = str(normalized.get("correlation_id") or "uncorrelated")
        grouped.setdefault(key, []).append(normalized)
    for key in grouped:
        grouped[key] = sorted(grouped[key], key=lambda row: (row["timestamp"], row["modality"], row["source_module"]))
    return grouped


def summarize_embodied_context(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    modalities = set(snapshot.get("modalities_present", []))
    missing_core = sorted(CORE_MODALITIES - modalities)
    completeness = "complete" if not missing_core else ("partial" if modalities else "empty")
    confidence = round(len(modalities & CORE_MODALITIES) / len(CORE_MODALITIES), 3)
    return {
        "completeness": completeness,
        "confidence": confidence,
        "missing_core_modalities": missing_core,
    }


def build_embodiment_snapshot(events: Sequence[Mapping[str, Any]], *, created_at: float | None = None, correlation_id: str | None = None) -> dict[str, Any]:
    normalized_events = [_normalize_event(event) for event in events if str(event.get("modality", "")) in SUPPORTED_MODALITIES]
    latest_by_modality: dict[str, dict[str, Any]] = {}
    for event in normalized_events:
        mod = event["modality"]
        prior = latest_by_modality.get(mod)
        if prior is None or event["timestamp"] >= prior["timestamp"]:
            latest_by_modality[mod] = event

    modalities_present = sorted(latest_by_modality.keys())
    privacy_classes = sorted({event["privacy_class"] for event in normalized_events})
    source_modules = sorted({event["source_module"] for event in normalized_events})
    source_event_refs = sorted(embodiment_snapshot_source_ref(event) for event in normalized_events)

    inferred_correlation = correlation_id
    if inferred_correlation is None:
        for event in normalized_events:
            if event.get("correlation_id"):
                inferred_correlation = str(event["correlation_id"])
                break

    retention_present = any(event["raw_retention"] for event in normalized_events)
    retention_requested = retention_present
    risk_flags = {
        "can_write_memory": any(event["can_write_memory"] for event in normalized_events),
        "can_trigger_actions": any(event["can_trigger_actions"] for event in normalized_events),
        "biometric_or_emotion_sensitive": any(mod in {"vision", "audio", "feedback", "multimodal", "gaze"} for mod in modalities_present),
    }

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "created_at": float(created_at if created_at is not None else time.time()),
        "correlation_id": inferred_correlation,
        "modalities_present": modalities_present,
        "source_event_refs": source_event_refs,
        "source_modules": source_modules,
        "privacy_classes": privacy_classes,
        "raw_retention_present": retention_present,
        "raw_retention_requested": retention_requested,
        "raw_retention_default": False,
        "risk_flags": risk_flags,
        "current_screen_context": latest_by_modality.get("screen", {}).get("observation"),
        "current_audio_context": latest_by_modality.get("audio", {}).get("observation"),
        "current_vision_context": latest_by_modality.get("vision", {}).get("observation"),
        "current_feedback_context": latest_by_modality.get("feedback", {}).get("observation"),
        "multimodal_context": latest_by_modality.get("multimodal", {}).get("observation"),
        "current_gaze_context": latest_by_modality.get("gaze", {}).get("observation"),
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
    }
    snapshot["confidence_posture"] = summarize_embodied_context(snapshot)
    digest_material = dict(snapshot)
    digest_material.pop("created_at", None)
    snapshot["snapshot_id"] = hashlib.sha256(json.dumps(digest_material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    return snapshot


def fuse_perception_events(events: Sequence[Mapping[str, Any]], *, created_at: float | None = None, correlation_id: str | None = None) -> dict[str, Any]:
    return build_embodiment_snapshot(events, created_at=created_at, correlation_id=correlation_id)


__all__ = [
    "build_embodiment_snapshot",
    "fuse_perception_events",
    "group_perception_events_by_correlation",
    "summarize_embodied_context",
    "embodiment_snapshot_source_ref",
]
