from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping

BRIDGE_STATUSES = {
    "bridge_ready",
    "bridge_ready_with_warnings",
    "bridge_manual_review_required",
    "bridge_blocked",
    "bridge_failed",
}


@dataclass(frozen=True)
class HouseholdCameraEventBridgePolicy:
    nuisance_repeat_threshold: int = 3
    nuisance_retention_days: int = 14
    allow_external_authority_contact: bool = False


@dataclass(frozen=True)
class HouseholdCameraEventSource:
    source_name: str
    source_kind: str


@dataclass(frozen=True)
class HouseholdCameraEventInput:
    event_id: str
    event_type: str
    zone: str
    modality: str
    entity_class: str
    confidence: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class HouseholdCameraEventZoneMapping:
    deadzone_match: bool
    redaction_required: bool
    redaction_applied: bool
    storage_allowed: bool


@dataclass(frozen=True)
class HouseholdCameraEventDecision:
    decision: str
    status: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class HouseholdPresenceEventPacket:
    schema_version: str
    event_id: str
    zone: str
    modality: str
    entity_class: str
    memory_class: str
    event_purpose: str
    allowed_awareness: tuple[str, ...]
    prohibited_awareness: tuple[str, ...]
    retention_posture: str
    speaker_gate_required: bool
    operator_confirmation_required: bool
    external_authority_contact_allowed: bool
    affective_discernment_orientation: str
    least_intrusive_adequate_response: str
    room_composition: str
    confidence: float
    uncertainty: str
    deadzone_match: bool
    redaction_required: bool
    redaction_applied: bool
    storage_allowed: bool


@dataclass(frozen=True)
class HouseholdCameraEventBridgeResult:
    status: str
    decision: HouseholdCameraEventDecision
    packet: HouseholdPresenceEventPacket

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_event_input(payload: Mapping[str, Any]) -> HouseholdCameraEventInput:
    meta = dict(payload.get("metadata", {})) if isinstance(payload.get("metadata"), Mapping) else {}
    return HouseholdCameraEventInput(
        event_id=str(payload.get("event_id", "unknown")),
        event_type=str(payload.get("event_type", "generic_perception_event")),
        zone=str(payload.get("zone", "unknown_zone")),
        modality=str(payload.get("modality", "camera")),
        entity_class=str(payload.get("entity_class", "unknown")),
        confidence=float(payload.get("confidence", 0.5)),
        metadata=meta,
    )


def _zone_mapping(event: HouseholdCameraEventInput) -> HouseholdCameraEventZoneMapping:
    deadzone = bool(event.metadata.get("deadzone_match", False)) or event.zone in {"deadzone", "exterior_sensitive_zone"}
    redaction_required = deadzone
    redaction_applied = bool(event.metadata.get("redaction_applied", False))
    storage_allowed = not redaction_required or redaction_applied
    return HouseholdCameraEventZoneMapping(deadzone, redaction_required, redaction_applied, storage_allowed)


def bridge_event(payload: Mapping[str, Any], policy: HouseholdCameraEventBridgePolicy | None = None) -> HouseholdCameraEventBridgeResult:
    p = policy or HouseholdCameraEventBridgePolicy()
    e = normalize_event_input(payload)
    zone = _zone_mapping(e)
    warnings: list[str] = []
    decision = "accept_as_ambient_journal"
    status = "bridge_ready"
    memory_class = "ambient_journal"
    purpose = "household_awareness"

    if not zone.storage_allowed:
        decision = "blocked_by_deadzone"
        status = "bridge_blocked"
        warnings.append("redaction_required_but_not_applied")
        memory_class = "blocked"
        purpose = "policy_protection"
    elif e.metadata.get("external_authority_contact", False) and not p.allow_external_authority_contact:
        decision = "blocked_by_external_authority_boundary"
        status = "bridge_blocked"
        warnings.append("external_authority_contact_blocked")
        memory_class = "blocked"
        purpose = "boundary_enforcement"
    elif e.entity_class in {"animal", "wildlife", "non_human"} and e.zone.startswith("exterior"):
        decision = "accept_as_wildlife_ledger_candidate"
        memory_class = "wildlife_ledger_candidate"
        purpose = "wildlife_presence"
    elif e.entity_class == "person" and e.zone.startswith("exterior"):
        decision = "accept_as_security_event"
        memory_class = "security_event_log"
        purpose = "exterior_security_awareness"
        if e.metadata.get("named_profile_requested", False):
            warnings.append("named_person_dossier_prohibited")
            status = "bridge_ready_with_warnings"
    elif e.entity_class == "vehicle" and e.zone == "exterior_security_zone":
        decision = "accept_as_security_event"
        memory_class = "security_event_log"
        purpose = "vehicle_security_metadata"
    if int(e.metadata.get("repeat_count", 0)) >= p.nuisance_repeat_threshold and e.entity_class in {"person", "vehicle"}:
        decision = "accept_as_nuisance_evidence_candidate"
        memory_class = "nuisance_evidence_candidate"
        purpose = "bounded_nuisance_evidence"
    if e.event_type == "protected_care_summary":
        decision = "accept_as_protected_care_summary"
        memory_class = "protected_care_summary"
        purpose = "care_summary_metadata"

    if e.metadata.get("contains_raw_audio", False) or e.metadata.get("contains_raw_transcript", False):
        status = "bridge_blocked"
        decision = "blocked_by_policy"
        warnings.append("raw_audio_transcript_retention_prohibited")

    if e.metadata.get("face_affect_gaze", False):
        warnings.append("face_affect_gaze_non_authority_only")

    if e.metadata.get("speaker_action_requested", False):
        warnings.append("speaker_gate_required")
        status = "bridge_manual_review_required"

    room = str(e.metadata.get("room_composition", "unknown"))
    if room in {"child_present", "guest_present", "caregiver_present", "adult_only"}:
        pass
    else:
        room = "unknown"

    packet = HouseholdPresenceEventPacket(
        schema_version="household_presence_camera_event_packet.v1",
        event_id=e.event_id,
        zone=e.zone,
        modality=e.modality,
        entity_class=e.entity_class,
        memory_class=memory_class,
        event_purpose=purpose,
        allowed_awareness=("live_awareness", "ambient_journal"),
        prohibited_awareness=("intimate_profile", "named_dossier"),
        retention_posture=f"bounded_{p.nuisance_retention_days}d" if memory_class == "nuisance_evidence_candidate" else "minimal",
        speaker_gate_required=True,
        operator_confirmation_required=status in {"bridge_manual_review_required", "bridge_blocked"},
        external_authority_contact_allowed=False,
        affective_discernment_orientation="supportive_non_authority",
        least_intrusive_adequate_response="metadata_only_logging",
        room_composition=room,
        confidence=e.confidence,
        uncertainty="high" if e.confidence < 0.6 else "moderate" if e.confidence < 0.85 else "low",
        deadzone_match=zone.deadzone_match,
        redaction_required=zone.redaction_required,
        redaction_applied=zone.redaction_applied,
        storage_allowed=zone.storage_allowed,
    )
    d = HouseholdCameraEventDecision(decision=decision, status=status if status in BRIDGE_STATUSES else "bridge_failed", warnings=tuple(sorted(set(warnings))))
    return HouseholdCameraEventBridgeResult(status=d.status, decision=d, packet=packet)


def dumps_bridge_result(result: HouseholdCameraEventBridgeResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True)
