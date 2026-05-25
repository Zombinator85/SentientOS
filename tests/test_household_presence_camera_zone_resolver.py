from __future__ import annotations

from sentientos.household_presence_camera_zone_resolver import HouseholdCameraZoneResolverPolicy, resolve_camera_event_zone


def _config(conf: float = 0.99, expires_at: str = ""):
    zones = [
        {"source_id":"cam1","source_kind":"fixture_source","zone_id":"zone_deadzone","zone_class":"deadzone","region_shape":"named_region","purpose":"d","allowed_downstream_uses":[],"prohibited_downstream_uses":["storage","naming","profile","evidence_retention","child_visible_output","speaker_output","external_disclosure"],"redaction_required":True,"child_visible_allowed":False,"adult_private_risk":True,"protected_care_risk":False,"exterior_sensitive_risk":False,"confidence":conf,"expires_at":expires_at},
        {"source_id":"cam1","source_kind":"fixture_source","zone_id":"zone_wildlife","zone_class":"wildlife_zone","region_shape":"named_region","purpose":"w","allowed_downstream_uses":["wildlife_ledger_candidate"],"prohibited_downstream_uses":[],"redaction_required":False,"child_visible_allowed":True,"adult_private_risk":False,"protected_care_risk":False,"exterior_sensitive_risk":False,"confidence":conf,"notes":"non_human_only"},
        {"source_id":"cam1","source_kind":"fixture_source","zone_id":"zone_sensitive","zone_class":"exterior_sensitive_zone","region_shape":"named_region","purpose":"s","allowed_downstream_uses":[],"prohibited_downstream_uses":[],"redaction_required":True,"child_visible_allowed":False,"adult_private_risk":False,"protected_care_risk":False,"exterior_sensitive_risk":True,"confidence":conf},
    ]
    return {"zones":zones}


def test_default_policy_validates():
    assert HouseholdCameraZoneResolverPolicy().schema_version.endswith(".v1")


def test_deadzone_precedence_on_full_frame_overlap():
    res = resolve_camera_event_zone(_config(), {"source_id":"cam1","source_kind":"fixture_source","event_id":"e","entity_class":"wildlife_visitor","region_shape":"full_frame"})
    assert res.resolution.effective_zone == "deadzone"
    assert "block_storage" in res.report.restrictions


def test_exterior_sensitive_requires_redaction():
    res = resolve_camera_event_zone(_config(), {"source_id":"cam1","source_kind":"fixture_source","event_id":"e","entity_class":"exterior_person","region_shape":"named_region","named_region_reference":"zone_sensitive"})
    assert res.resolution.redaction_required is True


def test_wildlife_zone_allows_wildlife_candidate():
    res = resolve_camera_event_zone(_config(), {"source_id":"cam1","source_kind":"fixture_source","event_id":"e","entity_class":"wildlife_visitor","region_shape":"named_region","named_region_reference":"zone_wildlife"})
    assert res.resolution.effective_zone == "wildlife_zone"
    assert "allow_wildlife_ledger_candidate" in res.report.restrictions
