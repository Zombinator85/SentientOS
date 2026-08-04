from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.codex_finalize_landing import build_parser, main
from sentientos.codex_finalize_landing import CodexFinalizeLandingPolicy
from sentientos.landing_validation_plan import SOLO_MATRIX_STATUS, seal_validation_plan, verify_validation_plan

pytestmark = pytest.mark.no_legacy_skip


def _plan(**updates: object) -> dict[str, object]:
    data: dict[str, object] = {
        "requested_profile": "solo", "effective_profile": "solo", "repository_sha": "a" * 40,
        "phase": "pre-commit", "title": "[codex:x] task", "intended_commit_title": "[codex:x] task",
        "changed_file_identity": [], "task_acceptance_manifest_digest": None,
        "task_acceptance_provenance_digest": None, "focused_test_command_contract": ["pytest x"],
        "targeted_mypy_command_contract": ["mypy x"], "required_stage_ids": ["focused_tests"],
        "conditionally_required_stage_ids": ["docs_build"], "skipped_or_deferred_stage_ids": ["matrix_summary"],
        "stage_results": {"focused_tests": {"status": "passed", "duration_seconds": 0.1}},
        "total_validation_duration_seconds": 1.0, "configured_total_budget_seconds": 1200,
        "remaining_budget_seconds": 1199.0, "exhaustive_matrix_status": SOLO_MATRIX_STATUS,
        "exhaustive_matrix_digest": None, "overall_status": "ready_to_commit",
    }
    data.update(updates)
    return seal_validation_plan(data)


def test_solo_profile_is_default() -> None:
    args = build_parser().parse_args(["finalize"])
    assert args.validation_profile == "solo"
    assert CodexFinalizeLandingPolicy().require_matrix_summary is False


def test_solo_profile_invokes_zero_matrix_processes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[str] = []
    monkeypatch.setattr("scripts.codex_finalize_landing._git_status", lambda: [])
    def fake(stage: str, command: str, required: bool, progress: bool, timeout: int, deadline: float, child_environment: dict[str, str]):
        from scripts.codex_finalize_landing import StageRuntime
        from sentientos.codex_finalize_landing import CodexFinalizeLandingCommandResult
        seen.append(stage)
        return CodexFinalizeLandingCommandResult(stage, command, 0, required=required), StageRuntime(stage, command, 0, True, 0, 0, "", "", "required", "passed", False)
    monkeypatch.setattr("scripts.codex_finalize_landing._run_stage", fake)
    assert main(["finalize", "--title", "x", "--intended-commit-title", "x", "--phase", "pre-commit", "--focused-test-command", "true", "--runtime-sandbox-root", str(tmp_path / "run"), "--output", str(tmp_path / "out.json")]) == 0
    assert not any("matrix" in stage for stage in seen)


def test_solo_profile_records_matrix_not_requested() -> None:
    assert _plan()["exhaustive_matrix_status"] == SOLO_MATRIX_STATUS


def test_solo_profile_requires_focused_tests_and_task_acceptance() -> None:
    assert CodexFinalizeLandingPolicy().require_focused_tests


def test_exhaustive_profile_preserves_matrix_v2() -> None:
    assert build_parser().parse_args(["finalize", "--validation-profile", "exhaustive"]).validation_profile == "exhaustive"


def test_profile_change_between_phases_is_rejected() -> None:
    changed = _plan(effective_profile="exhaustive", exhaustive_matrix_status="matrix_passed")
    assert "validation_profile_invalid_or_mutated" in verify_validation_plan(changed)[1]


def test_solo_validation_plan_digest_tampering_is_rejected() -> None:
    plan = _plan(); plan["title"] = "tampered"
    assert "validation_plan_digest_mismatch" in verify_validation_plan(plan)[1]


def test_postcommit_reuses_exact_solo_validation_plan() -> None:
    plan = _plan()
    assert seal_validation_plan({k: v for k, v in plan.items() if k not in {"schema_version", "artifact_digest"}})["artifact_digest"] == plan["artifact_digest"]


def test_docs_are_conditional_in_solo_profile() -> None:
    assert "docs_build" in _plan()["conditionally_required_stage_ids"]


def test_solo_budget_preserves_terminal_reserve() -> None:
    args = build_parser().parse_args(["finalize", "--terminal-reserve-seconds", "60"])
    assert args.terminal_reserve_seconds == 60
