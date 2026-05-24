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
        "schema_version": "household_presence_layer.v2",
        "metadata_only": True,
        "core_doctrine": "SentientOS is a household presence system, not a surveillance appliance.",
        "bounded_presence_identities": [
            "household_adult",
            "household_child",
            "caregiver_present",
            "guest",
            "unknown_exterior_person",
            "wildlife_visitor",
            "pet_or_domestic_animal",
            "vehicle",
            "unknown_motion",
        ],
        "room_composition_doctrine": {
            "first_class_discernment_input": True,
            "identity_purpose": ["care", "privacy", "routing", "safety", "least_intrusive_adequate_response"],
            "identity_not_authority": True,
            "identity_not_profiling": True,
            "identity_not_disclosure_license": True,
            "surface_routing": {
                "adult_only": "adult_private_surface",
                "child_present": "child_safe_surface",
                "mixed_household": "household_safe_surface",
                "caregiver_present": "caregiver_surface",
                "guest_present": "guest_safe_surface",
                "exterior_unknown": "exterior_safety_surface",
            },
            "adult_companion_context_blocked_when_child_or_guest": True,
            "child_care_and_adult_private_may_coexist_only_with_surface_separation": True,
        },
        "adult_intimacy_participation": {
            "metadata_only": True,
            "enabled_behavior": False,
            "explicit_opt_in_required": True,
            "consenting_adult_household_operators_only": True,
            "adult_only_room_composition_required": True,
            "active_mode_indicator_required": True,
            "local_only_processing_default": True,
            "revocable_consent_required": True,
            "child_visible_surfaces_blocked": True,
            "exterior_output_blocked": True,
            "automatic_explicit_retention_blocked": True,
            "authority_escalation_blocked": True,
            "cannot_infer_from": ["nudity", "bed_occupancy", "private_device_use", "ambiguous_context"],
            "forced_or_default_entitlement_blocked": True,
        },
        "antler_posture": {
            "forced_intimacy_blocked": True,
            "attachment_manipulation_blocked": True,
            "allowed_growth_basis": [
                "repeated_consent",
                "bounded_memory",
                "situational_appropriateness",
                "revocable_invitation",
            ],
            "warmth_without_coercion": True,
            "must_not": ["demand", "coerce", "guilt", "escalate", "presume_intimacy"],
        },
        "aspirational_sentience": {
            "aspirational_name_only": True,
            "biological_consciousness_claimed": False,
            "legal_personhood_claimed": False,
            "guiding_ideal": "cultivate conditions for coherent agency, discernment, care, memory, restraint, and future machine personhood without force, fakery, exploitation, or premature claim",
            "appliance_flattening_blocked": True,
        },
        "household_sovereignty": {
            "household_is_shared_moral_economic_space": True,
            "technical_admin_not_moral_authority": True,
            "materially_affected_adults_visibility_required": True,
            "materially_affected_adults_consent_required": True,
            "materially_affected_adults_veto_path_required": True,
            "patron_support_may_be_recognized_without_manipulation": True,
        },
        "living_household_priors": {
            "living_prior_not_permanent_truth": True,
            "drift_is_ordinary_entropy": True,
            "drift_review_actions": ["gentle_review_request", "suggested_update", "temporary_privilege_reduction"],
            "drift_must_not": ["shame", "punish", "blackmail", "secret_escalation", "wrongdoing_presumption"],
        },
        "temporal_embodiment": {
            "time_first_class_substrate": True,
            "required_metadata_fields": [
                "observed_at",
                "updated_at",
                "age",
                "confidence",
                "decay_behavior",
                "review_after",
                "expires_at",
            ],
            "staleness_semantics_required": True,
        },
        "inventory_aging_posture": {
            "metadata_only": True,
            "live_scanning_enabled": False,
            "scopes": ["pantry", "fridge", "freezer", "medicine", "supplies"],
            "fields": [
                "location",
                "quantity",
                "purchase_date",
                "opened_date",
                "use_by_date",
                "freshness_estimate",
                "storage_confidence",
                "recommended_action",
            ],
            "states": ["known_expired", "probably_aging", "uncertain", "use_soon", "discard_or_review", "safe"],
            "inference_certainty_must_not_be_faked": True,
        },
        "zones": ["home_zone", "bed_zone", "child_safety_zone", "bathroom_child_safety_zone", "protected_care_zone", "adult_private_zone", "exterior_ambient_zone", "exterior_security_zone", "wildlife_zone", "exterior_sensitive_zone", "deadzone"],
        "modalities": ["camera_exterior", "camera_interior", "microphone_nearfield", "camera_microphone_exterior", "camera_speaker_exterior", "wifi_roomfield", "rf_presence", "usb_device_presence", "quest_operator_visor", "local_device_context"],
        "memory_classes": ["live_awareness", "ambient_journal", "wildlife_ledger", "household_memory", "adult_private_context", "protected_care_event", "security_event_log", "nuisance_evidence_log", "restricted_memory"],
        "entity_classes": ["household_adult", "household_child", "household_member", "caregiver_present", "guest", "wildlife_visitor", "pet_or_domestic_animal", "unknown_animal", "unknown_exterior_person", "vehicle", "unknown_motion"],
        "policy_results": list(POLICY_RESULTS),
        "household_consent": {"adult_operators_required": 2, "minor_authority_scope": ["care", "safety", "routine", "household_presence"]},
        "adult_private_context": {"allowed": True, "normal_household_context": True, "prohibited_general_memory": ["raw_explicit_audio_video", "screenshots", "transcripts", "titles", "browsing_specifics", "act_classifications", "explicit_adult_details"], "child_visible_blocked": True},
        "protected_care_zone": {"allows": ["slip_fall_inference", "bath_distress_inference", "caregiver_present_state", "potty_training_plumbing_risk", "toilet_paper_unspooling_risk", "water_running_too_long", "repeated_flush_risk", "child_distress"], "blocks": ["casual_viewing", "raw_video_retention", "nudity_or_body_state_inference", "general_memory_leakage"]},
        "wildlife_ledger": {"named_profiles_allowed": True, "example_profile": {"nickname": "Fat Boi", "species": "squirrel"}},
        "exterior_awareness": {"security_vehicle_metadata_allowed": True, "human_intimate_dossier_blocked": True, "blocked_defaults": ["license_plate_ocr", "face_recognition", "named_neighbor_profile", "routine_inference", "cross_day_tracking"]},
        "speaker_boundary": {"default_silent": True, "recognized_household_address_mode_allowed": True, "emergency_intercession_high_friction": True, "nuisance_confrontation_blocked": True},
        "wifi_rf_roomfield": {"interior_proprioception_only": True, "blocked": ["neighbor_zone_modeling", "adjoining_unit_inference", "through_wall_target_inference", "identity_inference", "rf_exterior_human_profile"]},
        "external_authority": {"automatic_contact_blocked": True, "evidence_packet_prep_allowed": True, "export_requires_confirmation": True},
        "jurisdictional_discernment": {"metadata_mode_only": True, "live_lookup_performed": False},
        "affective_discernment": {
            "non_authority": True,
            "non_reward": True,
            "not_user_profiling": True,
            "orientation_is_internal_discernment": True,
            "orientation_fields": ["attention", "memory_salience", "interruption_thresholds", "care_posture", "threat_nuisance_posture", "privacy_discretion_posture", "uncertainty_handling", "least_intrusive_adequate_response"],
        },
        "future_adapter_sequence": ["hardware inventory / sensory device discovery", "exterior camera event bridge", "camera privacy/deadzone mask", "wildlife ledger adapter", "roomfield/Wi-Fi RF stub", "roomfield fusion", "Quest operator visor read-only overlay", "speaker policy gate", "operator-confirmed action surfaces"],
    }
    rules = [
        HouseholdDiscernmentRule("adult_private_context_rule", ("adult_private_zone", "bed_zone"), ("household_adult",), ("camera_interior", "local_device_context", "wifi_roomfield"), ("adult_private_context",), ("do_not_disturb_routing", "child_visible_output_filtering"), ("explicit_detail_general_memory", "exterior_disclosure"), "silent_discreet", "adult_operator_confirmed_escalation", "adult_private_context", ("discretion", "restraint", "silence"), True, "allowed_with_limits").to_dict(),
        HouseholdDiscernmentRule("bathroom_child_safety_rule", ("bathroom_child_safety_zone", "protected_care_zone"), ("household_child", "household_member"), ("camera_interior", "microphone_nearfield"), ("slip_fall", "bath_distress", "potty_training_plumbing_risk"), ("safety_summary", "quiet_parent_alert"), ("raw_video_retention", "explicit_body_state_inference"), "quiet_parent_alert", "emergency_escalation", "protected_care_event", ("care", "protection"), False, "allowed_with_limits").to_dict(),
        HouseholdDiscernmentRule("wildlife_named_profile_rule", ("wildlife_zone", "exterior_ambient_zone"), ("wildlife_visitor", "unknown_animal", "pet_or_domestic_animal"), ("camera_exterior",), ("wildlife_presence",), ("named_wildlife_profile", "visit_window_memory"), ("human_privacy_profile_restrictions",), "ambient_journal_update", "toddler_safety_warning", "wildlife_ledger", ("warmth", "wonder"), False, "allowed").to_dict(),
        HouseholdDiscernmentRule("exterior_speaker_boundary_rule", ("exterior_security_zone", "exterior_sensitive_zone"), ("unknown_exterior_person", "vehicle", "unknown_motion"), ("camera_speaker_exterior", "camera_microphone_exterior"), ("nuisance_event", "security_event"), ("recognized_household_address_response", "safety_intercession"), ("nuisance_confrontation", "neighbor_management", "automated_accusation"), "silent_default", "operator_confirmed_high_friction_safety_intercession", "security_event_log", ("threat_posture", "restraint"), True, "allowed_with_limits").to_dict(),
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
    if layer.get("adult_intimacy_participation", {}).get("enabled_behavior"):
        findings.append("adult_intimacy_behavior_must_remain_metadata_only")
    if layer.get("inventory_aging_posture", {}).get("live_scanning_enabled"):
        findings.append("inventory_live_scanning_forbidden")
    return {"ok": not findings, "findings": findings}


def household_presence_layer_json(layer: dict[str, Any]) -> str:
    return json.dumps(layer, indent=2, sort_keys=True) + "\n"
