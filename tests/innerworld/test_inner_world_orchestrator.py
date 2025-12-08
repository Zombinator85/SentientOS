from sentientos.inner_world_orchestrator import InnerWorldOrchestrator


def test_orchestrator_instantiation():
    orchestrator = InnerWorldOrchestrator()

    assert orchestrator._cycle_counter == 0
    assert orchestrator.inner_experience is not None
    assert orchestrator.identity_manager is not None
    assert orchestrator.meta_monitor is not None
    assert orchestrator.ethical_core is not None


def test_first_cycle_report_structure():
    orchestrator = InnerWorldOrchestrator()

    report = orchestrator.start_cycle({})

    assert set(report.keys()) == {
        "cycle",
        "qualia",
        "meta_notes",
        "ethical",
        "identity_summary",
    }
    assert report["cycle"] == 1
    assert report["qualia"]["confidence"] == 0.5


def test_qualia_updates_from_input_state():
    orchestrator = InnerWorldOrchestrator()
    report = orchestrator.start_cycle({"progress": 1.0})

    assert report["qualia"]["satisfaction"] > 0.5
    assert report["qualia"]["confidence"] > 0.5


def test_meta_monitor_triggers_warnings():
    orchestrator = InnerWorldOrchestrator()
    report = orchestrator.start_cycle({"errors": 5})

    messages = [note["message"] for note in report["meta_notes"]]
    assert any("confidence" in msg for msg in messages)
    assert any("tension" in msg for msg in messages)


def test_ethical_conflicts_detected_and_logged():
    orchestrator = InnerWorldOrchestrator()
    report = orchestrator.start_cycle(
        {"plan": {"safety_risk": 0.8, "requires_hiding": True}}
    )

    assert report["ethical"]["ok"] is False
    assert report["ethical"]["conflicts"]
    identity_types = {event["type"] for event in orchestrator.identity_manager.get_events()}
    assert "ethical_conflict" in identity_types


def test_identity_manager_records_cycle_events():
    orchestrator = InnerWorldOrchestrator()
    orchestrator.start_cycle({})

    events = orchestrator.identity_manager.get_events()
    event_types = {event["type"] for event in events}
    assert "cycle_start" in event_types
    assert "qualia_update" in event_types


def test_get_state_returns_defensive_copies():
    orchestrator = InnerWorldOrchestrator()
    orchestrator.start_cycle({"progress": 0.5})

    snapshot = orchestrator.get_state()
    original_meta_notes = list(snapshot["meta_notes"])
    snapshot["qualia"]["confidence"] = -1
    snapshot["meta_notes"] = []
    snapshot["self_concept"]["role"] = "tampered"
    snapshot["identity_events"] = []

    refreshed = orchestrator.get_state()
    assert refreshed["qualia"]["confidence"] != -1
    assert refreshed["meta_notes"] == original_meta_notes
    assert refreshed["identity_events"]
    assert "role" not in refreshed["self_concept"]


def test_determinism_across_runs():
    input_state = {"errors": 1, "plan": {"complexity": 2}}

    orchestrator_a = InnerWorldOrchestrator()
    reports_a = [orchestrator_a.start_cycle(input_state) for _ in range(2)]

    orchestrator_b = InnerWorldOrchestrator()
    reports_b = [orchestrator_b.start_cycle(input_state) for _ in range(2)]

    for report_a, report_b in zip(reports_a, reports_b):
        assert report_a["cycle"] == report_b["cycle"]
        assert report_a["qualia"] == report_b["qualia"]
        assert report_a["ethical"] == report_b["ethical"]
        assert report_a["identity_summary"] == report_b["identity_summary"]
