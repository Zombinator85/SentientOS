from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping

from sentientos.household_presence_camera_event_bridge import bridge_event
from sentientos.household_presence_deadzone_redaction import evaluate_redaction_request


@dataclass(frozen=True)
class HouseholdCameraRedactionPipelinePolicy:
    schema_version: str = "household_presence_camera_redaction_pipeline_policy.v1"
    require_child_visible_guard: bool = True


@dataclass(frozen=True)
class HouseholdCameraRedactionPipelineRequest:
    payload: dict[str, Any]


@dataclass(frozen=True)
class HouseholdCameraRedactionPipelineInput:
    event_id: str
    zone: str
    entity_class: str
    event_type: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class HouseholdCameraRedactionPipelineStage:
    name: str
    status: str


@dataclass(frozen=True)
class HouseholdCameraRedactionPipelineDecision:
    route: str
    blocked: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class HouseholdCameraRedactionPipelinePacket:
    event_id: str
    route: str
    confidence: float
    uncertainty: str
    digest: str
    annotations: tuple[str, ...]


@dataclass(frozen=True)
class HouseholdCameraRedactionPipelineResult:
    status: str
    stages: tuple[HouseholdCameraRedactionPipelineStage, ...]
    decision: HouseholdCameraRedactionPipelineDecision
    packet: HouseholdCameraRedactionPipelinePacket

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_default_policy() -> HouseholdCameraRedactionPipelinePolicy:
    return HouseholdCameraRedactionPipelinePolicy()


def normalize_input(payload: Mapping[str, Any]) -> HouseholdCameraRedactionPipelineInput:
    meta = dict(payload.get("metadata", {})) if isinstance(payload.get("metadata"), Mapping) else {}
    return HouseholdCameraRedactionPipelineInput(
        event_id=str(payload.get("event_id", "unknown")),
        zone=str(payload.get("zone", "unknown_zone")),
        entity_class=str(payload.get("entity_class", "unknown")),
        event_type=str(payload.get("event_type", "generic_perception_event")),
        metadata=meta,
    )


def validate_policy(policy: HouseholdCameraRedactionPipelinePolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith(".v1")
    return {"ok": ok, "status": "household_camera_redaction_pipeline_policy_valid" if ok else "household_camera_redaction_pipeline_policy_invalid"}


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def evaluate_pipeline(payload: Mapping[str, Any], policy: HouseholdCameraRedactionPipelinePolicy | None = None) -> HouseholdCameraRedactionPipelineResult:
    p = policy or build_default_policy()
    i = normalize_input(payload)
    stages = [HouseholdCameraRedactionPipelineStage("input_loaded", "ok")]

    bridge = bridge_event(payload)
    stages.append(HouseholdCameraRedactionPipelineStage("camera_event_normalized", bridge.status))

    redaction = evaluate_redaction_request({
        "event_id": i.event_id,
        "zone": i.zone,
        "entity_class": i.entity_class,
        "event_type": i.event_type,
        "redaction_required": bridge.packet.redaction_required,
        "redaction_state": "applied" if bridge.packet.redaction_applied else "required_not_applied" if bridge.packet.redaction_required else "not_required",
        "speaker_output_requested": bool(i.metadata.get("speaker_action_requested", False)),
        "external_disclosure_requested": bool(i.metadata.get("external_authority_contact", False)),
        "named_profile_requested": bool(i.metadata.get("named_profile_requested", False)),
        "intimate_profile_requested": bool(i.metadata.get("intimate_profile_requested", False)),
        "license_plate_tracking_requested": bool(i.metadata.get("license_plate_tracking_requested", False)),
        "metadata": i.metadata,
    })
    stages.append(HouseholdCameraRedactionPipelineStage("redaction_contract_evaluated", redaction.decision.status))

    route = "redacted_ambient_journal"
    reasons: set[str] = set(redaction.decision.warnings)
    annotations: set[str] = set(redaction.decision.warnings)
    blocked = False

    if i.metadata.get("external_authority_contact", False):
        route = "blocked_by_external_authority_boundary"
        blocked = True
    elif i.metadata.get("speaker_action_requested", False):
        route = "blocked_by_speaker_boundary"
        blocked = True
    elif i.zone == "deadzone":
        route = "blocked_by_deadzone"
        blocked = True
    elif i.zone == "exterior_sensitive_zone" and bridge.packet.redaction_required and not bridge.packet.redaction_applied:
        route = "blocked_by_missing_redaction"
        blocked = True
    elif i.zone == "adult_private_zone":
        route = "blocked_by_adult_private_policy" if i.metadata.get("child_visible_output", False) else "operator_review_required"
        blocked = i.metadata.get("child_visible_output", False)
    elif i.zone in {"protected_care_zone", "bathroom_child_safety_zone"}:
        route = "protected_care_summary"
        annotations.add("raw_bathroom_retention_blocked")
    elif i.entity_class in {"wildlife", "wildlife_visitor", "animal", "non_human"} and i.zone == "wildlife_zone":
        route = "wildlife_ledger_candidate"
    elif i.entity_class == "vehicle":
        route = "security_event_metadata"
        annotations.add("plate_routine_profiling_blocked")
    elif i.metadata.get("nuisance_threshold_exceeded", False):
        route = "nuisance_evidence_metadata"
        annotations.add("bounded_retention_only")
    elif i.entity_class in {"person", "exterior_person"}:
        route = "security_event_metadata" if i.zone.startswith("exterior") else "live_awareness_only"
        annotations.add("named_intimate_dossier_blocked")

    if i.metadata.get("face_affect_gaze", False):
        annotations.add("face_affect_gaze_non_authority_only")

    stages.append(HouseholdCameraRedactionPipelineStage("downstream_route_selected", route))
    if route == "operator_review_required":
        stages.append(HouseholdCameraRedactionPipelineStage("operator_review_marked", "required"))
    if blocked:
        stages.append(HouseholdCameraRedactionPipelineStage("blocked", "yes"))

    packet_payload = {"event_id": i.event_id, "route": route, "zone": i.zone, "entity_class": i.entity_class, "event_type": i.event_type}
    packet = HouseholdCameraRedactionPipelinePacket(i.event_id, route, float(payload.get("confidence", 0.5)), "high" if float(payload.get("confidence", 0.5)) < 0.6 else "moderate", _digest(packet_payload), tuple(sorted(annotations)))
    decision = HouseholdCameraRedactionPipelineDecision(route, blocked, tuple(sorted(reasons)))
    status = "blocked" if blocked else "ready"
    _ = p
    return HouseholdCameraRedactionPipelineResult(status, tuple(stages), decision, packet)


def dumps_result(result: HouseholdCameraRedactionPipelineResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True)
