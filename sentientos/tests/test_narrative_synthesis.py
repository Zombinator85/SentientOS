from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from log_utils import append_json
import task_admission
import task_executor
from sentientos import authority_surface
from sentientos import narrative_synthesis


def _write_entries(path: Path, entries: list[dict[str, object]]) -> None:
    for entry in entries:
        append_json(path, entry)


def _fixed_now() -> datetime:
    return datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def log_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    task_log = tmp_path / "task_executor.jsonl"
    admission_log = tmp_path / "task_admission.jsonl"
    routine_log = tmp_path / "routine_delegation.jsonl"
    diff_log = tmp_path / "authority_diff.jsonl"
    narrative_log = tmp_path / "narrative.jsonl"

    monkeypatch.setattr(task_executor, "LOG_PATH", str(task_log))
    monkeypatch.setattr(task_admission, "ADMISSION_LOG_PATH", str(admission_log))
    monkeypatch.setattr(narrative_synthesis, "ROUTINE_LOG_PATH", str(routine_log))
    monkeypatch.setattr(narrative_synthesis, "AUTHORITY_DIFF_LOG_PATH", diff_log)
    monkeypatch.setattr(narrative_synthesis, "NARRATIVE_LOG_PATH", narrative_log)
    monkeypatch.setattr(authority_surface, "AUTHORITY_DIFF_LOG_PATH", diff_log)

    return {
        "task_log": task_log,
        "admission_log": admission_log,
        "routine_log": routine_log,
        "diff_log": diff_log,
        "narrative_log": narrative_log,
    }


def test_identical_inputs_produce_identical_narratives(log_paths: dict[str, Path]) -> None:
    _write_entries(
        log_paths["task_log"],
        [
            {
                "event": "task_result",
                "task_id": "task-1",
                "status": "completed",
                "timestamp": 1_700_000_000.0,
            },
        ],
    )
    output_a = narrative_synthesis.build_narrative_summary(now=_fixed_now())
    output_b = narrative_synthesis.build_narrative_summary(now=_fixed_now())
    assert output_a == output_b


def test_no_activity_reports_idle(log_paths: dict[str, Path]) -> None:
    output = narrative_synthesis.build_system_summary_with_time(now=_fixed_now())
    idle_section = next(section for section in output["sections"] if section["title"] == "Why Nothing Happened")
    assert idle_section["lines"] == [
        "No actions were taken because no tasks or delegated routines were active."
    ]


def test_semantic_only_changes_not_reported_as_authority(log_paths: dict[str, Path]) -> None:
    entry = {
        "event": "authority_surface_diff",
        "from_hash": "hash-a",
        "to_hash": "hash-b",
        "changes": [
            {
                "category": "routine",
                "change_type": "add",
                "impact": "semantic_only",
                "description": "Semantic habit class 'Focus' (class-1) added.",
            }
        ],
        "summary": {"total": 1, "authority": 0, "semantic_only": 1},
        "timestamp": 1_700_000_100.0,
    }
    _write_entries(log_paths["diff_log"], [entry])
    output = narrative_synthesis.build_authority_summary(now=_fixed_now())
    lines = output["sections"][0]["lines"]
    assert "no authority changes detected" in lines[0].lower()


def test_blocked_actions_summarized(log_paths: dict[str, Path]) -> None:
    _write_entries(
        log_paths["task_log"],
        [
            {
                "event": "unknown_prerequisite",
                "task_id": "task-2",
                "status": "authority-required",
                "reason": "missing approval",
                "timestamp": 1_700_000_200.0,
            },
        ],
    )
    _write_entries(
        log_paths["routine_log"],
        [
            {
                "event": "delegated_execution",
                "routine_id": "routine-1",
                "outcome": "failed",
                "scope_adherence": False,
                "timestamp": 1_700_000_300.0,
            },
        ],
    )
    output = narrative_synthesis.build_narrative_summary(now=_fixed_now())
    boundary = next(section for section in output["sections"] if section["title"] == "Risk & Boundary Report")
    assert "missing approvals" in boundary["lines"][0]
    assert "scope violations" in boundary["lines"][0]


def test_narratives_stable_under_log_reordering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_log_a = tmp_path / "task_a.jsonl"
    task_log_b = tmp_path / "task_b.jsonl"
    routine_log = tmp_path / "routine.jsonl"
    diff_log = tmp_path / "diff.jsonl"
    narrative_log = tmp_path / "narrative.jsonl"

    monkeypatch.setattr(task_executor, "LOG_PATH", str(task_log_a))
    monkeypatch.setattr(task_admission, "ADMISSION_LOG_PATH", str(tmp_path / "admission.jsonl"))
    monkeypatch.setattr(narrative_synthesis, "ROUTINE_LOG_PATH", str(routine_log))
    monkeypatch.setattr(narrative_synthesis, "AUTHORITY_DIFF_LOG_PATH", diff_log)
    monkeypatch.setattr(narrative_synthesis, "NARRATIVE_LOG_PATH", narrative_log)

    entries = [
        {
            "event": "task_result",
            "task_id": "task-a",
            "status": "completed",
            "timestamp": 1_700_000_400.0,
        },
        {
            "event": "task_result",
            "task_id": "task-b",
            "status": "failed",
            "timestamp": 1_700_000_500.0,
        },
    ]
    _write_entries(task_log_a, entries)
    output_a = narrative_synthesis.build_narrative_summary(now=_fixed_now())

    monkeypatch.setattr(task_executor, "LOG_PATH", str(task_log_b))
    _write_entries(task_log_b, list(reversed(entries)))
    output_b = narrative_synthesis.build_narrative_summary(now=_fixed_now())

    lines_a = [section["lines"] for section in output_a["sections"]]
    lines_b = [section["lines"] for section in output_b["sections"]]
    assert lines_a == lines_b
