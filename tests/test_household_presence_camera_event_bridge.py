from sentientos.household_presence_camera_event_bridge import bridge_event


def test_wildlife_mapping_allows_named_non_human() -> None:
    r = bridge_event({"event_id": "1", "event_type": "animal_detected", "zone": "exterior_garden_zone", "modality": "camera", "entity_class": "wildlife", "confidence": 0.9, "metadata": {"nickname": "Fat Boi"}})
    assert r.decision.decision == "accept_as_wildlife_ledger_candidate"


def test_deadzone_blocks_without_redaction() -> None:
    r = bridge_event({"event_id": "2", "event_type": "motion", "zone": "deadzone", "modality": "camera", "entity_class": "person", "confidence": 0.8, "metadata": {"redaction_applied": False}})
    assert r.status == "bridge_blocked"
    assert r.packet.storage_allowed is False


def test_face_affect_gaze_non_authority_warning() -> None:
    r = bridge_event({"event_id": "3", "event_type": "person_detected", "zone": "exterior_security_zone", "modality": "camera", "entity_class": "person", "confidence": 0.8, "metadata": {"face_affect_gaze": True}})
    assert "face_affect_gaze_non_authority_only" in r.decision.warnings
