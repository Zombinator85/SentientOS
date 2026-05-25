from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from datetime import datetime, timezone
from typing import Any, Mapping

REGION_SHAPES = {"full_frame","normalized_rectangle","normalized_polygon","named_region","source_declared_region","unknown_region"}
ZONE_CLASSES = {"deadzone","exterior_sensitive_zone","protected_care_zone","bathroom_child_safety_zone","adult_private_zone","child_safety_zone","wildlife_zone","exterior_security_zone","exterior_ambient_zone","home_zone","unknown_zone"}
SOURCE_KINDS = {"existing_camera_daemon","existing_vision_tracker","perception_bus_source","fixture_source","future_live_adapter","unknown_source"}
PRECEDENCE = {"deadzone":1,"exterior_sensitive_zone":2,"adult_private_zone":3,"protected_care_zone":4,"bathroom_child_safety_zone":4,"child_safety_zone":5,"exterior_security_zone":6,"wildlife_zone":7,"exterior_ambient_zone":8,"home_zone":9,"unknown_zone":10}

@dataclass(frozen=True)
class HouseholdCameraZoneConfigPolicy:
    schema_version: str = "household_presence_camera_zone_config.v1"
    min_confidence: float = 0.75

@dataclass(frozen=True)
class HouseholdCameraSourceIdentity:
    source_id: str
    source_kind: str

@dataclass(frozen=True)
class HouseholdCameraZoneRegion:
    region_shape: str
    normalized_coordinates: tuple[float, ...] = ()
    named_region_reference: str = ""

@dataclass(frozen=True)
class HouseholdCameraMaskRegion:
    mask_id: str
    region_shape: str

@dataclass(frozen=True)
class HouseholdCameraZoneConfig:
    source_id: str
    source_kind: str
    zone_id: str
    zone_class: str
    region_shape: str
    purpose: str
    allowed_downstream_uses: tuple[str, ...]
    prohibited_downstream_uses: tuple[str, ...]
    redaction_required: bool
    child_visible_allowed: bool
    adult_private_risk: bool
    protected_care_risk: bool
    exterior_sensitive_risk: bool
    speaker_output_allowed: bool = False
    external_disclosure_allowed: bool = False
    confidence: float = 1.0
    observed_at: str = ""
    updated_at: str = ""
    review_after: str = ""
    expires_at: str = ""
    configured_by: str = ""
    operator_review_required: bool = False
    notes: str = ""
    risk_notes: str = ""
    normalized_coordinates: tuple[float, ...] = ()

@dataclass(frozen=True)
class HouseholdCameraZoneConfigValidationFinding:
    severity: str
    code: str
    detail: str

@dataclass(frozen=True)
class HouseholdCameraZoneConfigReport:
    status: str
    source_count: int
    zone_count: int
    findings: tuple[HouseholdCameraZoneConfigValidationFinding, ...]

@dataclass(frozen=True)
class HouseholdCameraZoneConfigResult:
    report: HouseholdCameraZoneConfigReport
    normalized_config: tuple[HouseholdCameraZoneConfig, ...]
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def build_default_config() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return [{"source_id":"default_fixture_source","source_kind":"fixture_source","zone_id":"zone_home","zone_class":"home_zone","region_shape":"full_frame","purpose":"baseline metadata-only camera zone","normalized_coordinates":[],"allowed_downstream_uses":["household_presence_summary"],"prohibited_downstream_uses":["external_disclosure","speaker_output"],"redaction_required":False,"child_visible_allowed":True,"adult_private_risk":False,"protected_care_risk":False,"exterior_sensitive_risk":False,"speaker_output_allowed":False,"external_disclosure_allowed":False,"confidence":0.99,"observed_at":now,"updated_at":now,"review_after":now,"expires_at":"","configured_by":"codex","operator_review_required":False,"notes":"default","risk_notes":""}]

def validate_zone_config(payload: Mapping[str, Any], policy: HouseholdCameraZoneConfigPolicy | None = None) -> HouseholdCameraZoneConfigResult:
    p = policy or HouseholdCameraZoneConfigPolicy()
    zones = payload.get("zones", payload)
    findings=[]; normalized=[]; sources=set()
    now=datetime.now(timezone.utc)
    for z in zones:
        c=HouseholdCameraZoneConfig(**{**z,"normalized_coordinates":tuple(z.get("normalized_coordinates",[])),"allowed_downstream_uses":tuple(z.get("allowed_downstream_uses",[])),"prohibited_downstream_uses":tuple(z.get("prohibited_downstream_uses",[]))})
        normalized.append(c); sources.add(c.source_id)
        if c.source_kind not in SOURCE_KINDS: findings.append(HouseholdCameraZoneConfigValidationFinding("error","unknown_source_kind",c.source_kind))
        if c.zone_class not in ZONE_CLASSES: findings.append(HouseholdCameraZoneConfigValidationFinding("error","unknown_zone_class",c.zone_class))
        if c.region_shape not in REGION_SHAPES: findings.append(HouseholdCameraZoneConfigValidationFinding("error","unknown_region_shape",c.region_shape))
        if c.zone_class=="exterior_sensitive_zone" and not c.redaction_required: findings.append(HouseholdCameraZoneConfigValidationFinding("error","exterior_sensitive_requires_redaction",c.zone_id))
        if c.zone_class=="deadzone":
            req={"storage","naming","profile","evidence_retention","child_visible_output","speaker_output","external_disclosure"}
            if not req.issubset(set(c.prohibited_downstream_uses)): findings.append(HouseholdCameraZoneConfigValidationFinding("error","deadzone_missing_prohibitions",c.zone_id))
        if c.zone_class in {"protected_care_zone","bathroom_child_safety_zone"} and "summary_only" not in c.allowed_downstream_uses: findings.append(HouseholdCameraZoneConfigValidationFinding("error","protected_care_summary_only_required",c.zone_id))
        if c.zone_class=="adult_private_zone" and "explicit_general_memory" not in c.prohibited_downstream_uses: findings.append(HouseholdCameraZoneConfigValidationFinding("error","adult_private_memory_block_required",c.zone_id))
        if c.zone_class=="wildlife_zone" and "wildlife_ledger_candidate" in c.allowed_downstream_uses and "non_human_only" not in c.notes: findings.append(HouseholdCameraZoneConfigValidationFinding("error","wildlife_non_human_only_required",c.zone_id))
        if c.speaker_output_allowed: findings.append(HouseholdCameraZoneConfigValidationFinding("error","speaker_output_blocked",c.zone_id))
        if c.external_disclosure_allowed: findings.append(HouseholdCameraZoneConfigValidationFinding("error","external_disclosure_blocked",c.zone_id))
        if c.region_shape=="unknown_region" or c.zone_class=="unknown_zone": findings.append(HouseholdCameraZoneConfigValidationFinding("warning","unknown_requires_review",c.zone_id))
        if c.confidence < p.min_confidence: findings.append(HouseholdCameraZoneConfigValidationFinding("warning","low_confidence_review_required",c.zone_id))
        if c.expires_at:
            try:
                exp=datetime.fromisoformat(c.expires_at.replace("Z","+00:00"))
                if exp < now: findings.append(HouseholdCameraZoneConfigValidationFinding("warning","stale_or_expired_config",c.zone_id))
            except ValueError:
                findings.append(HouseholdCameraZoneConfigValidationFinding("error","invalid_expires_at",c.zone_id))
    if not sources: findings.append(HouseholdCameraZoneConfigValidationFinding("error","no_camera_sources","none"))
    if len(sources)>0 and not normalized: findings.append(HouseholdCameraZoneConfigValidationFinding("error","source_missing_explicit_zone","all"))
    status="blocked" if any(f.severity=="error" for f in findings) else ("review_required" if findings else "valid")
    return HouseholdCameraZoneConfigResult(HouseholdCameraZoneConfigReport(status,len(sources),len(normalized),tuple(findings)),tuple(sorted(normalized,key=lambda x:(x.source_id,PRECEDENCE.get(x.zone_class,999),x.zone_id))))

def to_deadzone_redaction_regions(result: HouseholdCameraZoneConfigResult) -> list[dict[str, Any]]:
    return [{"region_id":z.zone_id,"shape":z.region_shape,"zone_classification":z.zone_class,"redaction_required":z.redaction_required} for z in result.normalized_config]

def dumps_result(result: HouseholdCameraZoneConfigResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True)
