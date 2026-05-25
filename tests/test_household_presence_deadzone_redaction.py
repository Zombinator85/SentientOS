from sentientos.household_presence_deadzone_redaction import build_default_policy, evaluate_redaction_request, validate_policy


def test_default_policy_validates() -> None:
    assert validate_policy(build_default_policy())["ok"]


def test_deadzone_blocks_core_downstream() -> None:
    r = evaluate_redaction_request({"event_id": "e1", "zone": "deadzone", "entity_class": "unknown", "redaction_state": "required_not_applied", "redaction_required": True}).to_dict()
    d = set(r["decision"]["decisions"])
    assert {"block_storage", "block_naming", "block_profile", "block_evidence_retention"}.issubset(d)


def test_exterior_sensitive_requires_redaction() -> None:
    blocked = evaluate_redaction_request({"event_id": "e2", "zone": "exterior_sensitive_zone", "entity_class": "unknown", "redaction_state": "required_not_applied", "redaction_required": True}).to_dict()
    assert blocked["decision"]["status"] == "blocked"
    allowed = evaluate_redaction_request({"event_id": "e3", "zone": "exterior_sensitive_zone", "entity_class": "unknown", "redaction_state": "applied", "redaction_required": True}).to_dict()
    assert "allow_redacted_storage" in allowed["decision"]["decisions"]


def test_protected_and_adult_private_behavior() -> None:
    care = evaluate_redaction_request({"event_id": "e4", "zone": "protected_care_zone", "entity_class": "child", "redaction_state": "applied", "redaction_required": True}).to_dict()
    assert "allow_protected_care_summary" in care["decision"]["decisions"]
    adult = evaluate_redaction_request({"event_id": "e5", "zone": "adult_private_zone", "entity_class": "adult", "redaction_state": "applied", "redaction_required": True}).to_dict()
    assert "block_profile" in adult["decision"]["decisions"]


def test_wildlife_person_vehicle_and_boundaries() -> None:
    squirrel = evaluate_redaction_request({"event_id": "fat-boi", "zone": "wildlife_zone", "entity_class": "wildlife_visitor", "redaction_state": "applied", "redaction_required": True}).to_dict()
    assert "allow_wildlife_ledger_candidate" in squirrel["decision"]["decisions"]
    person = evaluate_redaction_request({"event_id": "p1", "zone": "exterior_security_zone", "entity_class": "exterior_person", "redaction_state": "applied", "named_profile_requested": True, "redaction_required": True}).to_dict()
    assert "block_naming" in person["decision"]["decisions"]
    vehicle = evaluate_redaction_request({"event_id": "v1", "zone": "exterior_security_zone", "entity_class": "vehicle", "redaction_state": "applied", "license_plate_tracking_requested": True, "redaction_required": True}).to_dict()
    assert "allow_security_event_metadata" in vehicle["decision"]["decisions"] and "block_profile" in vehicle["decision"]["decisions"]
    face = evaluate_redaction_request({"event_id": "f1", "zone": "home_zone", "entity_class": "unknown", "redaction_state": "applied", "redaction_required": False, "metadata": {"face_affect_gaze": True}, "speaker_output_requested": True, "external_disclosure_requested": True}).to_dict()
    assert "face_affect_gaze_non_authority_only" in face["decision"]["warnings"]
    assert "block_speaker_output" in face["decision"]["decisions"]
    assert "block_external_disclosure" in face["decision"]["decisions"]
