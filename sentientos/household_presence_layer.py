from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

POLICY_RESULTS = ("allowed", "allowed_with_limits", "operator_confirmation_required", "manual_review_required", "blocked")

@dataclass(frozen=True)
class HouseholdDiscernmentRule:
    rule_id: str
    zones: tuple[str, ...]
    entities: tuple[str, ...]
    modalities: tuple[str, ...]
    risk_contexts: tuple[str, ...]
    allowed_awareness: tuple[str, ...]
    prohibited_awareness: tuple[str, ...]
    default_response: str
    escalation_response: str
    memory_class: str
    affective_orientation: tuple[str, ...]
    operator_confirmation_required: bool
    policy_result: str
    principle: str = "least_intrusive_adequate_response"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_default_household_presence_layer() -> dict[str, Any]:
    layer = {
        "schema_version": "household_presence_layer.v1",
        "metadata_only": True,
        "core_doctrine": "SentientOS is a household presence system, not a surveillance appliance.",
        "zones": ["home_zone","bed_zone","child_safety_zone","bathroom_child_safety_zone","protected_care_zone","adult_private_zone","exterior_ambient_zone","exterior_security_zone","wildlife_zone","exterior_sensitive_zone","deadzone"],
        "modalities": ["camera_exterior","camera_interior","microphone_nearfield","camera_microphone_exterior","camera_speaker_exterior","wifi_roomfield","rf_presence","usb_device_presence","quest_operator_visor","local_device_context"],
        "memory_classes": ["live_awareness","ambient_journal","wildlife_ledger","household_memory","adult_private_context","protected_care_event","security_event_log","nuisance_evidence_log","restricted_memory"],
        "entity_classes": ["household_adult","household_child","household_member","wildlife_visitor","pet_or_domestic_animal","unknown_animal","exterior_person","vehicle","unknown_motion"],
        "policy_results": list(POLICY_RESULTS),
        "household_consent": {"adult_operators_required": 2, "minor_authority_scope": ["care", "safety", "routine", "household_presence"]},
        "adult_private_context": {"allowed": True, "normal_household_context": True, "prohibited_general_memory": ["raw_explicit_audio_video","screenshots","transcripts","titles","browsing_specifics","act_classifications","explicit_adult_details"], "child_visible_blocked": True},
        "protected_care_zone": {"allows": ["slip_fall_inference","bath_distress_inference","caregiver_present_state","potty_training_plumbing_risk","toilet_paper_unspooling_risk","water_running_too_long","repeated_flush_risk","child_distress"], "blocks": ["casual_viewing","raw_video_retention","nudity_or_body_state_inference","general_memory_leakage"]},
        "wildlife_ledger": {"named_profiles_allowed": True, "example_profile": {"nickname": "Fat Boi", "species": "squirrel"}},
        "exterior_awareness": {"security_vehicle_metadata_allowed": True, "human_intimate_dossier_blocked": True, "blocked_defaults": ["license_plate_ocr", "face_recognition", "named_neighbor_profile", "routine_inference", "cross_day_tracking"]},
        "speaker_boundary": {"default_silent": True, "recognized_household_address_mode_allowed": True, "emergency_intercession_high_friction": True, "nuisance_confrontation_blocked": True},
        "wifi_rf_roomfield": {"interior_proprioception_only": True, "blocked": ["neighbor_zone_modeling", "adjoining_unit_inference", "through_wall_target_inference", "identity_inference", "rf_exterior_human_profile"]},
        "external_authority": {"automatic_contact_blocked": True, "evidence_packet_prep_allowed": True, "export_requires_confirmation": True},
        "jurisdictional_discernment": {"metadata_mode_only": True, "live_lookup_performed": False},
        "affective_discernment": {"non_authority": True, "non_reward": True, "orientation_fields": ["attention","memory_salience","interruption_thresholds","care_posture","threat_nuisance_posture","privacy_discretion_posture","uncertainty_handling","least_intrusive_adequate_response"]},
        "future_adapter_sequence": ["hardware inventory / sensory device discovery","exterior camera event bridge","camera privacy/deadzone mask","wildlife ledger adapter","roomfield/Wi-Fi RF stub","roomfield fusion","Quest operator visor read-only overlay","speaker policy gate","operator-confirmed action surfaces"],
    }
    rules = [
        HouseholdDiscernmentRule("adult_private_context_rule", ("adult_private_zone","bed_zone"), ("household_adult",), ("camera_interior","local_device_context","wifi_roomfield"), ("adult_private_context",), ("do_not_disturb_routing","child_visible_output_filtering"), ("explicit_detail_general_memory","exterior_disclosure"), "silent_discreet", "adult_operator_confirmed_escalation", "adult_private_context", ("discretion","restraint","silence"), True, "allowed_with_limits").to_dict(),
        HouseholdDiscernmentRule("bathroom_child_safety_rule", ("bathroom_child_safety_zone","protected_care_zone"), ("household_child","household_member"), ("camera_interior","microphone_nearfield"), ("slip_fall","bath_distress","potty_training_plumbing_risk"), ("safety_summary","quiet_parent_alert"), ("raw_video_retention","explicit_body_state_inference"), "quiet_parent_alert", "emergency_escalation", "protected_care_event", ("care","protection"), False, "allowed_with_limits").to_dict(),
        HouseholdDiscernmentRule("wildlife_named_profile_rule", ("wildlife_zone","exterior_ambient_zone"), ("wildlife_visitor","unknown_animal","pet_or_domestic_animal"), ("camera_exterior",), ("wildlife_presence",), ("named_wildlife_profile","visit_window_memory"), ("human_privacy_profile_restrictions"), "ambient_journal_update", "toddler_safety_warning", "wildlife_ledger", ("warmth","wonder"), False, "allowed").to_dict(),
        HouseholdDiscernmentRule("exterior_speaker_boundary_rule", ("exterior_security_zone","exterior_sensitive_zone"), ("exterior_person","vehicle","unknown_motion"), ("camera_speaker_exterior","camera_microphone_exterior"), ("nuisance_event","security_event"), ("recognized_household_address_response","safety_intercession"), ("nuisance_confrontation","neighbor_management","automated_accusation"), "silent_default", "operator_confirmed_high_friction_safety_intercession", "security_event_log", ("threat_posture","restraint"), True, "allowed_with_limits").to_dict(),
    ]
    layer["discernment_rules"] = rules
    layer["deterministic_digest"] = hashlib.sha256(json.dumps(layer, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return layer


def validate_household_presence_layer(layer: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    if not layer.get("metadata_only"):
        findings.append("metadata_only_required")
    if layer.get("jurisdictional_discernment", {}).get("live_lookup_performed"):
        findings.append("jurisdictional_live_lookup_forbidden")
    if not layer.get("external_authority", {}).get("automatic_contact_blocked"):
        findings.append("automatic_external_contact_must_be_blocked")
    return {"ok": not findings, "findings": findings}


def household_presence_layer_json(layer: dict[str, Any]) -> str:
    return json.dumps(layer, indent=2, sort_keys=True) + "\n"
