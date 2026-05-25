from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping

REGION_SHAPES = {"full_frame", "normalized_rectangle", "normalized_polygon", "named_zone", "source_declared_region", "unknown_region"}
ZONE_CLASSES = {"deadzone", "exterior_sensitive_zone", "protected_care_zone", "bathroom_child_safety_zone", "adult_private_zone", "child_safety_zone", "wildlife_zone", "exterior_security_zone", "exterior_ambient_zone", "home_zone", "unknown_zone"}
REDACTION_STATES = {"not_required", "required_not_applied", "applied", "inherited_from_source", "unverifiable", "blocked"}


@dataclass(frozen=True)
class HouseholdDeadzoneRedactionPolicy:
    schema_version: str = "household_presence_deadzone_redaction_policy.v1"
    block_external_disclosure: bool = True
    block_speaker_without_gate: bool = True


@dataclass(frozen=True)
class HouseholdRedactionRegion:
    region_id: str
    shape: str
    zone_classification: str


@dataclass(frozen=True)
class HouseholdRedactionMask:
    mask_id: str
    state: str
    redaction_required: bool


@dataclass(frozen=True)
class HouseholdRedactionSource:
    source_name: str
    source_kind: str


@dataclass(frozen=True)
class HouseholdRedactionEvidence:
    source: HouseholdRedactionSource
    region: HouseholdRedactionRegion
    mask: HouseholdRedactionMask
    evidence_id: str


@dataclass(frozen=True)
class HouseholdRedactionRequest:
    event_id: str
    zone: str
    entity_class: str
    event_type: str
    redaction_state: str
    redaction_required: bool
    speaker_output_requested: bool
    external_disclosure_requested: bool
    named_profile_requested: bool
    intimate_profile_requested: bool
    license_plate_tracking_requested: bool
    metadata: dict[str, Any]


@dataclass(frozen=True)
class HouseholdRedactionDecision:
    status: str
    decisions: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class HouseholdRedactionReport:
    policy_schema: str
    event_id: str
    zone: str
    entity_class: str
    redaction_state: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class HouseholdDeadzoneRedactionResult:
    decision: HouseholdRedactionDecision
    report: HouseholdRedactionReport

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_default_policy() -> HouseholdDeadzoneRedactionPolicy:
    return HouseholdDeadzoneRedactionPolicy()


def normalize_request(payload: Mapping[str, Any]) -> HouseholdRedactionRequest:
    metadata = dict(payload.get("metadata", {})) if isinstance(payload.get("metadata"), Mapping) else {}
    return HouseholdRedactionRequest(
        event_id=str(payload.get("event_id", "unknown")),
        zone=str(payload.get("zone", "unknown_zone")),
        entity_class=str(payload.get("entity_class", "unknown")),
        event_type=str(payload.get("event_type", "generic_perception_event")),
        redaction_state=str(payload.get("redaction_state", "required_not_applied")),
        redaction_required=bool(payload.get("redaction_required", True)),
        speaker_output_requested=bool(payload.get("speaker_output_requested", False)),
        external_disclosure_requested=bool(payload.get("external_disclosure_requested", False)),
        named_profile_requested=bool(payload.get("named_profile_requested", False)),
        intimate_profile_requested=bool(payload.get("intimate_profile_requested", False)),
        license_plate_tracking_requested=bool(payload.get("license_plate_tracking_requested", False)),
        metadata=metadata,
    )


def validate_policy(policy: HouseholdDeadzoneRedactionPolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith(".v1") and policy.block_external_disclosure and policy.block_speaker_without_gate
    return {"ok": ok, "status": "household_deadzone_redaction_policy_valid" if ok else "household_deadzone_redaction_policy_invalid"}


def evaluate_redaction_request(payload: Mapping[str, Any], policy: HouseholdDeadzoneRedactionPolicy | None = None) -> HouseholdDeadzoneRedactionResult:
    p = policy or build_default_policy()
    r = normalize_request(payload)
    decisions = {"allow_live_awareness_only", "block_speaker_output", "block_external_disclosure"}
    warnings: set[str] = set()
    notes: set[str] = set()

    if r.zone not in ZONE_CLASSES:
        warnings.add("unknown_zone")
    if r.redaction_state not in REDACTION_STATES:
        warnings.add("unknown_redaction_state")

    if r.zone == "deadzone" or (r.zone == "exterior_sensitive_zone" and r.redaction_required and r.redaction_state in {"required_not_applied", "unverifiable", "blocked"}):
        decisions.update({"block_storage", "block_naming", "block_profile", "block_evidence_retention", "block_child_visible_output"})
        notes.add("deadzone_or_unredacted_sensitive_region_blocks_downstream")
    elif r.redaction_state in {"applied", "inherited_from_source"}:
        decisions.add("allow_redacted_storage")

    if r.zone in {"protected_care_zone", "bathroom_child_safety_zone"}:
        decisions.add("allow_protected_care_summary")
        decisions.update({"block_storage", "block_evidence_retention"})
        notes.add("protected_care_summary_only")

    if r.zone == "adult_private_zone":
        decisions.add("allow_live_awareness_only")
        decisions.update({"block_profile", "block_naming", "block_child_visible_output"})
        notes.add("adult_private_zone_blocks_explicit_general_memory")

    if r.entity_class == "wildlife_visitor" and r.zone == "wildlife_zone" and r.redaction_state in {"applied", "not_required", "inherited_from_source"}:
        decisions.update({"allow_wildlife_ledger_candidate", "allow_redacted_storage"})
    if r.entity_class == "exterior_person":
        decisions.update({"block_naming", "block_profile"})
        if r.named_profile_requested or r.intimate_profile_requested:
            warnings.add("exterior_person_named_intimate_profile_blocked")
    if r.entity_class == "vehicle" and r.zone == "exterior_security_zone":
        decisions.add("allow_security_event_metadata")
        if r.license_plate_tracking_requested:
            decisions.add("block_profile")
            warnings.add("license_plate_tracking_blocked_by_default")

    if r.metadata.get("face_affect_gaze", False):
        warnings.add("face_affect_gaze_non_authority_only")

    if r.speaker_output_requested and p.block_speaker_without_gate:
        decisions.add("block_speaker_output")
        warnings.add("speaker_gate_required")
    if r.external_disclosure_requested and p.block_external_disclosure:
        decisions.add("block_external_disclosure")
        warnings.add("external_disclosure_blocked")

    status = "allowed"
    if any(x in decisions for x in ("block_storage", "block_profile", "block_naming", "block_evidence_retention")):
        status = "blocked"
    elif warnings:
        status = "allowed_with_warnings"

    decision = HouseholdRedactionDecision(status=status, decisions=tuple(sorted(decisions)), warnings=tuple(sorted(warnings)))
    report = HouseholdRedactionReport(policy_schema=p.schema_version, event_id=r.event_id, zone=r.zone, entity_class=r.entity_class, redaction_state=r.redaction_state, notes=tuple(sorted(notes)))
    return HouseholdDeadzoneRedactionResult(decision=decision, report=report)


def summarize_result(result: HouseholdDeadzoneRedactionResult) -> dict[str, Any]:
    return {
        "status": result.decision.status,
        "event_id": result.report.event_id,
        "zone": result.report.zone,
        "decision_count": len(result.decision.decisions),
        "blocked": any(d.startswith("block_") for d in result.decision.decisions),
    }


def dumps_result(result: HouseholdDeadzoneRedactionResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True)
