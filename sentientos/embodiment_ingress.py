"""Canonical non-authoritative embodiment ingress gate.

This module evaluates embodiment/perception snapshots and returns proposal-only
candidates describing memory/action/operator-attention pressure.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "embodiment.ingress.v1"


def embodiment_ingress_receipt_ref(snapshot: Mapping[str, Any], *, salt: str = "") -> str:
    material = {
        "snapshot_id": snapshot.get("snapshot_id"),
        "source_event_refs": list(snapshot.get("source_event_refs", [])),
        "correlation_id": snapshot.get("correlation_id"),
        "salt": salt,
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    return f"ingress:{digest}"


def classify_embodied_pressure(snapshot: Mapping[str, Any]) -> list[str]:
    classes: list[str] = []
    modalities = set(snapshot.get("modalities_present", []))
    if "audio" in modalities or snapshot.get("current_audio_context", {}).get("message"):
        classes.append("memory_write_pressure")
    if "feedback" in modalities:
        classes.append("feedback_action_pressure")
    if "vision" in modalities:
        classes.append("biometric_emotion_pressure")
    if "multimodal" in modalities:
        classes.append("multimodal_summary_pressure")
    if "screen" in modalities:
        classes.append("screen_privacy_pressure")
    if not modalities:
        classes.append("incomplete_context_pressure")
    return sorted(set(classes))


def build_memory_ingress_candidate(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    audio = snapshot.get("current_audio_context") or {}
    message = audio.get("message")
    if not message:
        return None
    return {
        "candidate_type": "memory",
        "candidate_ref": embodiment_ingress_receipt_ref(snapshot, salt="memory"),
        "source": audio.get("source", "audio"),
        "proposed_text": str(message),
        "requires_review": True,
        "non_authoritative": True,
    }


def build_feedback_ingress_candidate(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    feedback = snapshot.get("current_feedback_context") or {}
    action = feedback.get("action")
    if not action:
        return None
    return {
        "candidate_type": "feedback",
        "candidate_ref": embodiment_ingress_receipt_ref(snapshot, salt="feedback"),
        "action": str(action),
        "blocked": True,
        "requires_operator_review": True,
        "non_authoritative": True,
    }


def build_operator_attention_candidate(snapshot: Mapping[str, Any], pressure: Sequence[str]) -> dict[str, Any] | None:
    if not pressure:
        return None
    return {
        "candidate_type": "operator_attention",
        "candidate_ref": embodiment_ingress_receipt_ref(snapshot, salt="attention"),
        "recommended": True,
        "reasons": list(pressure),
        "non_authoritative": True,
    }


def resolve_embodiment_ingress_posture(snapshot: Mapping[str, Any], pressure: Sequence[str]) -> str:
    conf = (snapshot.get("confidence_posture") or {}) if isinstance(snapshot.get("confidence_posture"), Mapping) else {}
    if conf.get("completeness") in {"empty", "partial"}:
        return "incomplete_context_hold"
    if "biometric_emotion_pressure" in pressure:
        return "biometric_sensitive_hold"
    if "screen_privacy_pressure" in pressure:
        return "privacy_sensitive_hold"
    if snapshot.get("raw_retention_present"):
        return "privacy_sensitive_hold"
    if snapshot.get("consent_required"):
        return "consent_required_hold"
    if "feedback_action_pressure" in pressure:
        return "action_candidate_blocked"
    if "memory_write_pressure" in pressure:
        return "memory_candidate_requires_review"
    if "multimodal_summary_pressure" in pressure:
        return "operator_attention_recommended"
    return "no_ingress_needed"


def evaluate_embodiment_ingress(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    pressure = classify_embodied_pressure(snapshot)
    posture = resolve_embodiment_ingress_posture(snapshot, pressure)
    risk_flags = dict(snapshot.get("risk_flags", {})) if isinstance(snapshot.get("risk_flags"), Mapping) else {}
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "ingress_id": embodiment_ingress_receipt_ref(snapshot),
        "source_snapshot_ref": str(snapshot.get("snapshot_id", "")),
        "source_event_refs": list(snapshot.get("source_event_refs", [])),
        "pressure_classifications": pressure,
        "recommended_posture": posture,
        "memory_candidate": build_memory_ingress_candidate(snapshot),
        "feedback_candidate": build_feedback_ingress_candidate(snapshot),
        "operator_attention_candidate": build_operator_attention_candidate(snapshot, pressure),
        "privacy_retention_posture": "hold" if "privacy_sensitive_hold" == posture else "review",
        "consent_posture": "consent_required" if posture == "consent_required_hold" else "not_asserted",
        "risk_flags": risk_flags,
        "rationale": [f"pressure:{p}" for p in pressure] or ["pressure:none"],
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_write_memory": True,
        "does_not_trigger_feedback": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
    }
    return receipt


def should_allow_legacy_memory_write(mode: str) -> bool:
    return mode == "compatibility_legacy"


def should_allow_legacy_feedback_action(mode: str) -> bool:
    return mode == "compatibility_legacy"


def mark_legacy_direct_effect_preserved(receipt: Mapping[str, Any], *, effect_type: str, mode: str) -> dict[str, Any]:
    marked = dict(receipt)
    marked["ingress_gate_mode"] = mode
    marked["legacy_direct_effect"] = effect_type
    marked["legacy_direct_effect_preserved"] = mode == "compatibility_legacy"
    marked["transition_state"] = "legacy_fallback" if mode == "compatibility_legacy" else "proposal_only"
    return marked


__all__ = [
    "evaluate_embodiment_ingress",
    "classify_embodied_pressure",
    "build_memory_ingress_candidate",
    "build_feedback_ingress_candidate",
    "build_operator_attention_candidate",
    "resolve_embodiment_ingress_posture",
    "embodiment_ingress_receipt_ref",
    "should_allow_legacy_memory_write",
    "should_allow_legacy_feedback_action",
    "mark_legacy_direct_effect_preserved",
]
