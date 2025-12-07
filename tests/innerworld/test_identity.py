from sentientos.identity import IdentityManager


def test_identity_manager_initial_state():
    manager = IdentityManager()
    assert manager.get_events() == []
    assert manager.get_self_concept() == {}


def test_log_event_records_monotonic_timestamps():
    manager = IdentityManager()
    manager.log_event("boot", "System initialized")
    manager.log_event("reflection", "Self-check complete")

    assert manager.get_events() == [
        {"timestamp": 1, "type": "boot", "description": "System initialized"},
        {"timestamp": 2, "type": "reflection", "description": "Self-check complete"},
    ]


def test_get_events_returns_defensive_copies():
    manager = IdentityManager()
    manager.log_event("boot", "System initialized")

    external_view = manager.get_events()
    external_view[0]["description"] = "tampered"

    assert manager.get_events()[0]["description"] == "System initialized"


def test_self_concept_overwrite_and_copy():
    manager = IdentityManager()
    manager.update_self_concept("role", "observer")
    manager.update_self_concept("role", "participant")

    snapshot = manager.get_self_concept()
    assert snapshot == {"role": "participant"}

    snapshot["role"] = "tampered"
    assert manager.get_self_concept()["role"] == "participant"


def test_summarize_is_deterministic():
    manager = IdentityManager()
    manager.log_event("boot", "System initialized")
    manager.log_event("reflection", "Self-check complete")
    manager.log_event("reflection", "Documented startup")
    manager.update_self_concept("role", "participant")
    manager.update_self_concept("status", "online")

    summary = manager.summarize()

    assert summary == "Identity summary: 3 events, 2 event types, 2 self-concept traits."
