from __future__ import annotations

import json

from sentientos.introspection import (
    EventType,
    TraceSpine,
    build_event,
    load_events,
    persist_event,
)
from sentientos.cli.trace_cli import main as trace_main


def test_introspection_event_determinism() -> None:
    metadata = {"status": "ok", "detail": {"count": 2}}
    linked = ["artifact-1", "artifact-2"]
    event_one = build_event(
        event_type=EventType.DIAGNOSTIC,
        phase="diagnostic",
        timestamp_logical=42,
        linked_artifact_ids=linked,
        summary="Diagnostic error frame created.",
        metadata=metadata,
    )
    event_two = build_event(
        event_type=EventType.DIAGNOSTIC,
        phase="diagnostic",
        timestamp_logical=42,
        linked_artifact_ids=linked,
        summary="Diagnostic error frame created.",
        metadata=metadata,
    )
    assert event_one.event_id == event_two.event_id
    assert event_one.to_json() == event_two.to_json()


def test_build_event_does_not_mutate_inputs() -> None:
    metadata = {"status": "ok", "payload": {"count": 1}}
    linked = ["artifact-1"]
    metadata_copy = json.loads(json.dumps(metadata))
    linked_copy = list(linked)
    build_event(
        event_type=EventType.CLI_ACTION,
        phase="cli",
        timestamp_logical=1,
        linked_artifact_ids=linked,
        summary="CLI command invoked.",
        metadata=metadata,
    )
    assert metadata == metadata_copy
    assert linked == linked_copy


def test_trace_reconstruction_filters(tmp_path) -> None:
    log_path = tmp_path / "trace.jsonl"
    first = build_event(
        event_type=EventType.DIAGNOSTIC,
        phase="diagnostic",
        timestamp_logical=1,
        linked_artifact_ids=["artifact-a"],
        summary="Diagnostic error frame created.",
        metadata={"error_code": "ERR"},
    )
    second = build_event(
        event_type=EventType.COGNITION_CYCLE,
        phase="cognition",
        timestamp_logical=2,
        linked_artifact_ids=["artifact-b"],
        summary="Cognition cycle completed.",
        metadata={"snapshot_hash": "artifact-b"},
    )
    persist_event(first, path=str(log_path))
    persist_event(second, path=str(log_path))

    events = load_events(str(log_path))
    spine = TraceSpine(events=events)

    by_phase = spine.linear_trace(phase="cognition")
    assert [event.event_type for event in by_phase] == [EventType.COGNITION_CYCLE]

    by_artifact = spine.linear_trace(artifact_id="artifact-a")
    assert [event.event_type for event in by_artifact] == [EventType.DIAGNOSTIC]

    last_event = spine.linear_trace(last=1)
    assert last_event[0].event_type == EventType.COGNITION_CYCLE


def test_trace_cli_output_stability(tmp_path, capsys) -> None:
    log_path = tmp_path / "trace.jsonl"
    event = build_event(
        event_type=EventType.CLI_ACTION,
        phase="cli",
        timestamp_logical=7,
        linked_artifact_ids=[],
        summary="CLI command invoked.",
        metadata={"command": "trace", "argv": ["trace"], "safe_command": True},
    )
    persist_event(event, path=str(log_path))

    trace_main(["--log-path", str(log_path), "--last", "1"])
    captured = capsys.readouterr().out.strip()
    metadata = json.dumps(event.metadata, sort_keys=True)
    expected = (
        f"000007 | CLI_ACTION | phase=cli | CLI command invoked. | "
        f"artifacts=- | metadata={metadata}"
    )
    assert captured == expected
