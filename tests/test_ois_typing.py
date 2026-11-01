from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from sentientos import ois

pytestmark = pytest.mark.no_legacy_skip


def test_execution_trace_normalizes_invalid_timestamps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ois, "_read_audit_log", lambda _path: [])
    monkeypatch.setattr(ois, "_index_by_task", lambda _entries: {})
    monkeypatch.setattr(
        ois,
        "_collect_task_executions",
        lambda _entries, _admissions: [{"type": "task", "timestamp": "invalid"}],
    )
    monkeypatch.setattr(
        ois,
        "_collect_routine_executions",
        lambda _entries: [{"type": "routine", "timestamp": 2.0}],
    )

    trace = ois.build_execution_trace()

    assert [item["type"] for item in trace["executions"]] == ["routine", "task"]


def test_routine_summary_returns_object_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Registry:
        def __init__(self) -> None:
            pass

        def list_routines(self) -> list[Any]:
            return [
                SimpleNamespace(
                    routine_id="routine-1",
                    trigger_description="on signal",
                    action_description="record note",
                    scope=("workspace",),
                )
            ]

    monkeypatch.setattr(ois, "RoutineRegistry", _Registry)

    result = ois._summarize_routines([])

    assert result["enabled"][0]["routine_id"] == "routine-1"
    assert result["paused"] == []


def test_task_execution_records_keep_typed_event_lists() -> None:
    executions = ois._collect_task_executions(
        [
            {"task_id": "task-1", "timestamp": 1, "event": "epr_action", "status": "blocked"},
            {"task_id": "task-1", "timestamp": 2, "event": "exhaustion", "reason": "budget"},
        ],
        {"task-1": {"actor": "operator", "mode": "approved"}},
    )

    assert executions[0]["timestamp"] == 2.0
    assert executions[0]["authority_boundaries"] == [
        {"type": "missing_approval", "detail": None}
    ]
    assert executions[0]["failures"] == [
        {"reason": "budget", "type": "exhaustion", "exhaustion_type": None}
    ]


def test_task_parser_rejects_string_as_privilege_sequence() -> None:
    task = ois._parse_task(
        {
            "task_id": "simulation",
            "objective": "check typed payload",
            "required_privileges": "admin",
        }
    )

    assert task.required_privileges == ()
