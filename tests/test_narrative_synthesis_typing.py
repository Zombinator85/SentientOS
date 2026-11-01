import pytest

from sentientos.narrative_synthesis import _summarize_routines, _summarize_tasks

pytestmark = pytest.mark.no_legacy_skip


def test_task_summary_keeps_accumulated_events_and_sorted_references():
    summary = _summarize_tasks(
        [
            {"task_id": "task-1", "event": "task_result", "status": "completed", "rolling_hash": "hash-2"},
            {
                "task_id": "task-1",
                "event": "epr_action",
                "action_id": "action-1",
                "reversibility": "reversible",
                "status": "blocked",
                "error": "approval_required",
                "prev_hash": "hash-1",
            },
            {"task_id": "task-1", "kind": "adapter", "artifacts": {"adapter_id": "adapter-1"}},
        ]
    )

    assert summary == {
        "tasks": [
            {
                "task_id": "task-1",
                "status": "completed",
                "blocked": True,
                "block_type": "missing_approval",
                "block_reason": "approval_required",
                "adapters": ["adapter-1"],
                "epr_actions": ["action-1"],
                "log_ids": ["hash-1", "hash-2"],
                "reversibility": ["reversible"],
            }
        ]
    }


def test_routine_summary_keeps_execution_and_conflict_counts():
    summary = _summarize_routines(
        [
            {"routine_id": "routine-1", "event": "delegated_execution", "outcome": "failed", "scope_adherence": False, "rolling_hash": "hash-1"},
            {"routine_id": "routine-1", "event": "routine_evaluation", "outcome": "conflict_paused"},
        ]
    )

    assert summary == {
        "routines": [
            {
                "routine_id": "routine-1",
                "executions": 1,
                "failed": 1,
                "scope_violations": 1,
                "log_ids": ["hash-1"],
                "conflict_paused": True,
            }
        ],
        "conflicts": ["routine-1"],
    }
