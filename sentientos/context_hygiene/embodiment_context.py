from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Sequence

from sentientos.context_hygiene.context_packet import PollutionRisk
from sentientos.context_hygiene.selector import ContextCandidate


class EmbodimentContextSourceKind(str, Enum):
    RAW_PERCEPTION_EVENT = "raw_perception_event"
    LEGACY_SCREEN_ARTIFACT = "legacy_screen_artifact"
    LEGACY_AUDIO_ARTIFACT = "legacy_audio_artifact"
    LEGACY_VISION_ARTIFACT = "legacy_vision_artifact"
    LEGACY_MULTIMODAL_ARTIFACT = "legacy_multimodal_artifact"
    LEGACY_FEEDBACK_ARTIFACT = "legacy_feedback_artifact"
    EMBODIMENT_SNAPSHOT = "embodiment_snapshot"
    EMBODIMENT_INGRESS_RECEIPT = "embodiment_ingress_receipt"
    EMBODIMENT_PROPOSAL = "embodiment_proposal"
    EMBODIMENT_PROPOSAL_DIAGNOSTIC = "embodiment_proposal_diagnostic"
    EMBODIMENT_REVIEW_RECEIPT = "embodiment_review_receipt"
    EMBODIMENT_HANDOFF_CANDIDATE = "embodiment_handoff_candidate"
    EMBODIMENT_GOVERNANCE_BRIDGE_CANDIDATE = "embodiment_governance_bridge_candidate"
    EMBODIMENT_FULFILLMENT_CANDIDATE = "embodiment_fulfillment_candidate"
    EMBODIMENT_FULFILLMENT_RECEIPT = "embodiment_fulfillment_receipt"
    MEMORY_INGRESS_VALIDATION = "memory_ingress_validation"
    ACTION_INGRESS_VALIDATION = "action_ingress_validation"
    RETENTION_INGRESS_VALIDATION = "retention_ingress_validation"
    UNKNOWN = "unknown"


class EmbodimentPrivacyPosture(str, Enum):
    PUBLIC = "public"
    LOW_RISK = "low_risk"
    PRIVACY_SENSITIVE = "privacy_sensitive"
    BIOMETRIC_OR_EMOTION_SENSITIVE = "biometric_or_emotion_sensitive"
    RAW_RETENTION_SENSITIVE = "raw_retention_sensitive"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class EmbodimentContextEligibility:
    eligible: bool
    blocked: bool
    reason: str
    source_kind: EmbodimentContextSourceKind
    privacy_posture: EmbodimentPrivacyPosture


def classify_embodiment_context_source_kind(artifact: Mapping[str, Any]) -> EmbodimentContextSourceKind:
    raw = str(artifact.get("source_kind") or artifact.get("artifact_kind") or "").strip().lower()
    for k in EmbodimentContextSourceKind:
        if raw == k.value:
            return k
    return EmbodimentContextSourceKind.UNKNOWN


def classify_embodiment_privacy_posture(artifact: Mapping[str, Any]) -> EmbodimentPrivacyPosture:
    raw = str(artifact.get("privacy_posture") or "").strip().lower()
    if raw in {p.value for p in EmbodimentPrivacyPosture}:
        return EmbodimentPrivacyPosture(raw)
    if artifact.get("contains_biometric_or_emotion"):
        return EmbodimentPrivacyPosture.BIOMETRIC_OR_EMOTION_SENSITIVE
    if artifact.get("contains_raw_retention"):
        return EmbodimentPrivacyPosture.RAW_RETENTION_SENSITIVE
    return EmbodimentPrivacyPosture.PUBLIC


def embodiment_artifact_is_sanitized_for_context(artifact: Mapping[str, Any]) -> bool:
    return bool(artifact.get("sanitized_context_summary"))


def _has_provenance(artifact: Mapping[str, Any]) -> bool:
    return bool(artifact.get("provenance_refs") or artifact.get("source_refs"))


def _has_scope(artifact: Mapping[str, Any]) -> bool:
    return bool(artifact.get("packet_scope") and artifact.get("conversation_scope_id") and artifact.get("task_scope_id"))


def explain_embodiment_context_exclusion(artifact: Mapping[str, Any]) -> str | None:
    kind = classify_embodiment_context_source_kind(artifact)
    privacy = classify_embodiment_privacy_posture(artifact)
    if kind == EmbodimentContextSourceKind.UNKNOWN:
        return "excluded: unknown embodiment source kind"
    if artifact.get("decision_power", "none") != "none":
        return "excluded: embodiment artifact has decision power"
    if not _has_provenance(artifact):
        return "excluded: missing provenance/source refs"
    if not _has_scope(artifact):
        return "excluded: missing scope"
    if kind in {
        EmbodimentContextSourceKind.RAW_PERCEPTION_EVENT,
        EmbodimentContextSourceKind.LEGACY_SCREEN_ARTIFACT,
        EmbodimentContextSourceKind.LEGACY_AUDIO_ARTIFACT,
        EmbodimentContextSourceKind.LEGACY_VISION_ARTIFACT,
        EmbodimentContextSourceKind.LEGACY_MULTIMODAL_ARTIFACT,
        EmbodimentContextSourceKind.LEGACY_FEEDBACK_ARTIFACT,
    }:
        return "excluded: raw perception artifacts are not context"
    sanitized = embodiment_artifact_is_sanitized_for_context(artifact)
    if privacy == EmbodimentPrivacyPosture.BIOMETRIC_OR_EMOTION_SENSITIVE and not (sanitized and artifact.get("allow_context_biometric_or_emotion")):
        return "excluded: biometric/emotion-sensitive artifact not explicitly allowed"
    if privacy == EmbodimentPrivacyPosture.RAW_RETENTION_SENSITIVE and not (sanitized and artifact.get("allow_context_raw_retention")):
        return "excluded: raw retention artifact not explicitly allowed"
    if privacy == EmbodimentPrivacyPosture.PRIVACY_SENSITIVE and not (sanitized and artifact.get("allow_context_privacy_sensitive")):
        return "excluded: privacy-sensitive artifact not explicitly allowed"
    if kind == EmbodimentContextSourceKind.EMBODIMENT_SNAPSHOT and not sanitized:
        return "excluded: embodiment snapshot not sanitized"
    if kind == EmbodimentContextSourceKind.EMBODIMENT_INGRESS_RECEIPT and not (sanitized or artifact.get("context_eligible")):
        return "excluded: ingress receipt not context-eligible"
    if artifact.get("action_capable") and kind not in {
        EmbodimentContextSourceKind.EMBODIMENT_PROPOSAL,
        EmbodimentContextSourceKind.EMBODIMENT_PROPOSAL_DIAGNOSTIC,
        EmbodimentContextSourceKind.EMBODIMENT_REVIEW_RECEIPT,
    }:
        return "excluded: action-capable artifact not converted to non-actioning form"
    if kind == EmbodimentContextSourceKind.EMBODIMENT_PROPOSAL and str(artifact.get("proposal_status", "")).lower() not in {"reviewable", "pending_review", "non_executing"}:
        return "excluded: embodiment proposal not in reviewable/non-executing status"
    checks = {
        EmbodimentContextSourceKind.EMBODIMENT_HANDOFF_CANDIDATE: "handoff_is_not_fulfillment",
        EmbodimentContextSourceKind.EMBODIMENT_GOVERNANCE_BRIDGE_CANDIDATE: "bridge_is_not_admission",
        EmbodimentContextSourceKind.EMBODIMENT_FULFILLMENT_CANDIDATE: "fulfillment_candidate_is_not_effect",
        EmbodimentContextSourceKind.EMBODIMENT_FULFILLMENT_RECEIPT: "fulfillment_receipt_is_not_effect",
        EmbodimentContextSourceKind.MEMORY_INGRESS_VALIDATION: "validation_is_not_memory_write",
        EmbodimentContextSourceKind.ACTION_INGRESS_VALIDATION: "validation_is_not_action_trigger",
        EmbodimentContextSourceKind.RETENTION_INGRESS_VALIDATION: "validation_is_not_retention_commit",
    }
    if kind in checks and not artifact.get(checks[kind]):
        return f"excluded: required flag missing ({checks[kind]})"
    if kind == EmbodimentContextSourceKind.EMBODIMENT_FULFILLMENT_RECEIPT and not artifact.get("receipt_does_not_prove_side_effect"):
        return "excluded: fulfillment receipt may prove side effects"
    return None


def embodiment_artifact_is_context_eligible(artifact: Mapping[str, Any]) -> bool:
    return explain_embodiment_context_exclusion(artifact) is None


def _risk(artifact: Mapping[str, Any], blocked: bool) -> PollutionRisk:
    if blocked:
        return PollutionRisk.BLOCKED
    privacy = classify_embodiment_privacy_posture(artifact)
    if privacy in {EmbodimentPrivacyPosture.PRIVACY_SENSITIVE, EmbodimentPrivacyPosture.BIOMETRIC_OR_EMOTION_SENSITIVE, EmbodimentPrivacyPosture.RAW_RETENTION_SENSITIVE}:
        return PollutionRisk.HIGH
    return PollutionRisk.LOW if embodiment_artifact_is_sanitized_for_context(artifact) else PollutionRisk.MEDIUM


def embodiment_artifact_to_context_candidate(artifact: Mapping[str, Any]) -> ContextCandidate:
    blocked_reason = explain_embodiment_context_exclusion(artifact)
    kind = classify_embodiment_context_source_kind(artifact)
    lane = "diagnostic" if kind == EmbodimentContextSourceKind.EMBODIMENT_PROPOSAL_DIAGNOSTIC else "embodiment"
    return ContextCandidate(
        ref_id=str(artifact.get("ref_id") or ""),
        ref_type=lane,
        packet_scope=artifact.get("packet_scope"),
        conversation_scope_id=artifact.get("conversation_scope_id"),
        task_scope_id=artifact.get("task_scope_id"),
        summary=artifact.get("content_summary"),
        provenance_refs=tuple(artifact.get("provenance_refs") or artifact.get("source_refs") or ()),
        source_locator=artifact.get("source_locator") or artifact.get("source_path"),
        created_at=artifact.get("created_at") if isinstance(artifact.get("created_at"), datetime) else None,
        observed_at=artifact.get("observed_at") if isinstance(artifact.get("observed_at"), datetime) else None,
        freshness_status=str(artifact.get("freshness_status") or "unknown"),
        contradiction_status=str(artifact.get("contradiction_status") or "unknown"),
        provenance_status=str(artifact.get("provenance_status") or "partial"),
        pollution_risk=_risk(artifact, blocked_reason is not None).value,
        metadata={
            "source_kind": kind.value,
            "privacy_posture": classify_embodiment_privacy_posture(artifact).value,
            "sanitized_context_summary": embodiment_artifact_is_sanitized_for_context(artifact),
            "non_authoritative": bool(artifact.get("non_authoritative", True)),
            "decision_power": str(artifact.get("decision_power", "none")),
            "risk_flags": tuple(artifact.get("risk_flags") or ()),
            "context_eligible": blocked_reason is None,
            "exclusion_reason": blocked_reason,
        },
        already_sanitized_context_summary=(embodiment_artifact_is_sanitized_for_context(artifact) and blocked_reason is None),
    )


def build_embodiment_context_candidates(artifacts: Sequence[Mapping[str, Any]]) -> tuple[ContextCandidate, ...]:
    return tuple(embodiment_artifact_to_context_candidate(a) for a in artifacts)


def summarize_embodiment_context_eligibility(artifacts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    blocked = 0
    eligible = 0
    for artifact in artifacts:
        if embodiment_artifact_is_context_eligible(artifact):
            eligible += 1
        else:
            blocked += 1
    return {"total": len(artifacts), "eligible": eligible, "blocked_or_excluded": blocked}
