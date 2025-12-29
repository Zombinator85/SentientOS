from __future__ import annotations

import os

import pytest

from sentientos.consciousness.integration import run_consciousness_cycle
from sentientos.diagnostics import (
    ErrorClass,
    FailedPhase,
    RecoveryEligibility,
    attempt_recovery,
    build_error_frame,
)
from sentientos.diagnostics.recovery import RECOVERY_SKIPPED, RECOVERY_SUCCEEDED
from sentientos.introspection import EventType, TraceSpine, build_event
from sentientos.introspection.narrative_views import (
    ensure_view_allowed,
    render_artifact_view,
    render_cycle_context_view,
    render_event_chain,
)

pytestmark = pytest.mark.no_legacy_skip


class IntrospectionCollector:
    def __init__(self) -> None:
        self.events = []
        self._counter = 0

    def emit(
        self,
        *,
        event_type: EventType,
        phase: str,
        summary: str,
        metadata: dict | None = None,
        linked_artifact_ids: list[str] | None = None,
        timestamp_logical: int | None = None,
        **_: object,
    ) -> None:
        if timestamp_logical is None:
            self._counter += 1
            logical = self._counter
        else:
            logical = timestamp_logical
        event = build_event(
            event_type=event_type,
            phase=phase,
            timestamp_logical=logical,
            linked_artifact_ids=linked_artifact_ids or [],
            summary=summary,
            metadata=metadata or {},
        )
        self.events.append(event)


def _patch_introspection(monkeypatch: pytest.MonkeyPatch) -> IntrospectionCollector:
    collector = IntrospectionCollector()
    monkeypatch.setattr("sentientos.introspection.spine.emit_introspection_event", collector.emit)
    monkeypatch.setattr("sentientos.diagnostics.error_frame.emit_introspection_event", collector.emit)
    monkeypatch.setattr("sentientos.diagnostics.recovery.emit_introspection_event", collector.emit)
    monkeypatch.setattr("sentientos.consciousness.cognitive_state.emit_introspection_event", collector.emit)
    monkeypatch.setattr("sentientos.consciousness.integration.emit_introspection_event", collector.emit)
    monkeypatch.setattr(
        "sentientos.governance.intentional_forgetting.emit_introspection_event",
        collector.emit,
    )
    return collector


def test_diagnostic_frames_emit_introspection_and_renderable(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = _patch_introspection(monkeypatch)
    frame = build_error_frame(
        error_code="INVARIANT_VIOLATION",
        error_class=ErrorClass.INTEGRITY,
        failed_phase=FailedPhase.TEST,
        suppressed_actions=["retry"],
        human_summary="Invariant breach detected.",
    )

    diagnostic_events = [event for event in collector.events if event.event_type == EventType.DIAGNOSTIC]
    assert diagnostic_events, "Diagnostic frame emitted no introspection events."
    assert any(
        frame.content_hash() in event.linked_artifact_ids for event in diagnostic_events
    ), "Diagnostic event did not link the error frame hash."

    spine = TraceSpine(events=collector.events)
    view = render_artifact_view(spine, frame.content_hash())
    assert frame.content_hash() in "\n".join(view.lines), "Diagnostic hash missing from narrative view."


def test_recovery_attempts_emit_visibility(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    collector = _patch_introspection(monkeypatch)
    missing_dir = tmp_path / "missing"
    frame = build_error_frame(
        error_code="MISSING_RESOURCE",
        error_class=ErrorClass.INSTALL,
        failed_phase=FailedPhase.INSTALL,
        suppressed_actions=["retry"],
        human_summary="Install workspace directory is missing.",
        technical_details={"missing_path": missing_dir.as_posix(), "missing_kind": "directory"},
        recovery_eligibility=RecoveryEligibility.RECOVERABLE,
    )
    outcome = attempt_recovery(frame)
    assert outcome.status == RECOVERY_SUCCEEDED

    simulation_events = [
        event for event in collector.events if event.event_type == EventType.RECOVERY_SIMULATION
    ]
    execution_events = [
        event
        for event in collector.events
        if event.event_type == EventType.RECOVERY_EXECUTION and event.metadata.get("status") == "executed"
    ]
    assert simulation_events, "Recovery simulation did not emit introspection events."
    assert execution_events, "Recovery execution did not emit introspection events."

    execution_event = execution_events[0]
    assert frame.content_hash() in execution_event.linked_artifact_ids
    assert execution_event.metadata.get("ladder_id") == "install-missing-directory-v1"
    assert outcome.proof is not None
    assert execution_event.metadata.get("pre_snapshot_hash") == outcome.proof.pre_snapshot_hash
    assert execution_event.metadata.get("post_snapshot_hash") == outcome.proof.post_snapshot_hash

    collector.events.clear()
    ineligible_frame = build_error_frame(
        error_code="INVARIANT_VIOLATION",
        error_class=ErrorClass.INTEGRITY,
        failed_phase=FailedPhase.TEST,
        suppressed_actions=["retry"],
        human_summary="Invariant breach detected.",
    )
    skip_outcome = attempt_recovery(ineligible_frame)
    assert skip_outcome.status == RECOVERY_SKIPPED

    refused_events = [
        event
        for event in collector.events
        if event.event_type == EventType.RECOVERY_EXECUTION and event.metadata.get("status") == "refused"
    ]
    assert refused_events, "Recovery refusal did not emit introspection events."
    assert ineligible_frame.content_hash() in refused_events[0].linked_artifact_ids


def test_cognition_cycle_emits_snapshot_and_renderable(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    collector = _patch_introspection(monkeypatch)
    run_consciousness_cycle(
        {
            "include_pressure_snapshot": True,
            "pressure_snapshot_path": str(tmp_path / "pressure.json"),
        }
    )

    cycle_events = [event for event in collector.events if event.event_type == EventType.COGNITION_CYCLE]
    snapshot_events = [
        event for event in collector.events if event.event_type == EventType.SNAPSHOT_EMISSION
    ]
    assert cycle_events, "Cognition cycle emitted no introspection event."
    assert snapshot_events, "Cognition snapshot emission is silent."

    cycle_event = cycle_events[0]
    snapshot_event = snapshot_events[0]
    snapshot_hash = cycle_event.metadata.get("snapshot_hash")
    assert snapshot_hash, "Cognition cycle missing snapshot hash metadata."
    assert snapshot_hash in snapshot_event.linked_artifact_ids
    assert cycle_event.metadata.get("cognitive_posture"), "Cognition cycle missing posture metadata."
    assert cycle_event.metadata.get(
        "cognitive_load_narrative"
    ), "Cognition cycle missing load metadata."

    spine = TraceSpine(events=collector.events)
    view = render_cycle_context_view(spine, cycle_event.event_id)
    view_text = "\n".join(view.lines)
    assert "posture=-" not in view_text
    assert "load=-" not in view_text


def test_forgetting_pressure_links_into_cycle_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    collector = _patch_introspection(monkeypatch)
    run_consciousness_cycle(
        {
            "include_pressure_snapshot": True,
            "pressure_snapshot_path": str(tmp_path / "forget.json"),
        }
    )

    forgetting_events = [
        event for event in collector.events if event.event_type == EventType.FORGETTING_PRESSURE
    ]
    assert forgetting_events, "Forgetting pressure snapshot emitted no introspection event."

    snapshot_events = [
        event for event in collector.events if event.event_type == EventType.SNAPSHOT_EMISSION
    ]
    assert snapshot_events

    forgetting_event = forgetting_events[0]
    snapshot_event = snapshot_events[0]
    assert snapshot_event.metadata.get("pressure_snapshot_hash") == forgetting_event.metadata.get(
        "snapshot_hash"
    )

    cycle_event = next(
        event for event in collector.events if event.event_type == EventType.COGNITION_CYCLE
    )
    spine = TraceSpine(events=collector.events)
    view = render_cycle_context_view(spine, cycle_event.event_id)
    assert "forgetting_pressure_event_id=-" not in "\n".join(view.lines)


def test_cli_actions_and_failures_emit_introspection(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = _patch_introspection(monkeypatch)
    import sentientos.__main__ as main_module

    def boom() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "_print_status", boom)

    with pytest.raises(SystemExit) as excinfo:
        main_module.main(["status"])
    assert excinfo.value.code == 1

    assert any(event.event_type == EventType.CLI_ACTION for event in collector.events)
    assert any(event.event_type == EventType.DIAGNOSTIC for event in collector.events)


def test_cli_action_emitted_for_safe_command(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = _patch_introspection(monkeypatch)
    import sentientos.__main__ as main_module

    monkeypatch.setattr(main_module, "_print_status", lambda: None)
    main_module.main(["status"])

    assert any(
        event.event_type == EventType.CLI_ACTION and event.metadata.get("command") == "status"
        for event in collector.events
    )


def test_narrative_reachability_covers_all_event_types() -> None:
    events = []
    timestamp = 0
    for event_type in EventType:
        timestamp += 1
        events.append(
            build_event(
                event_type=event_type,
                phase="audit",
                timestamp_logical=timestamp,
                linked_artifact_ids=[f"artifact-{event_type.value}"],
                summary="visibility audit",
                metadata={"event_type": event_type.value},
            )
        )

    view = render_event_chain(events)
    rendered = "\n".join(view.lines)
    for event_type in EventType:
        assert event_type.value in rendered, f"Narrative views orphaned {event_type.value} events."


def test_narrative_rendering_has_no_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_emit(*_: object, **__: object) -> None:
        raise AssertionError("Narrative rendering emitted introspection events.")

    monkeypatch.setattr("sentientos.introspection.spine.emit_introspection_event", fail_emit)

    event = build_event(
        event_type=EventType.DIAGNOSTIC,
        phase="diagnostic",
        timestamp_logical=1,
        linked_artifact_ids=["artifact"],
        summary="Diagnostic error frame created.",
        metadata={"error_code": "ERR"},
    )
    spine = TraceSpine(events=[event])
    before = list(spine.events)

    render_event_chain(spine.events)
    render_artifact_view(spine, "artifact")
    render_cycle_context_view(spine, "missing")

    assert spine.events == before


def test_narrative_rendering_blocked_in_recovery_or_cognition() -> None:
    os.environ["SENTIENTOS_EXECUTION_CONTEXT"] = "recovery"
    try:
        with pytest.raises(RuntimeError):
            ensure_view_allowed()
    finally:
        os.environ.pop("SENTIENTOS_EXECUTION_CONTEXT", None)

    os.environ["SENTIENTOS_EXECUTION_CONTEXT"] = "cognition"
    try:
        with pytest.raises(RuntimeError):
            ensure_view_allowed()
    finally:
        os.environ.pop("SENTIENTOS_EXECUTION_CONTEXT", None)
