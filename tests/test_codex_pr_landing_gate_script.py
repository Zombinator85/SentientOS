from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import codex_pr_landing_gate as cli
from sentientos.landing_validation_plan import seal_validation_plan


def _matrix() -> str:
    return json.dumps({"status": "passed", "required_failure_count": 0, "results": [{"label": "targeted_tests", "exit_code": 0, "required": True}, {"label": "targeted_mypy", "exit_code": 0, "required": True}, {"label": "mypy_baseline", "exit_code": 0, "required": True}, {"label": "docs_check_deps", "exit_code": 0, "required": False}, {"label": "docs_build", "exit_code": 0, "required": True}, {"label": "prompt_boundaries", "exit_code": 0, "required": True}, {"label": "strict_audits", "exit_code": 0, "required": True}, {"label": "audit_immutability", "exit_code": 0, "required": True}]})


def test_gate_allows(capsys) -> None:  # type: ignore[no-untyped-def]
    rc = cli.main(["gate", "--title", "[codex:developer] ok", "--intended-commit-title", "[codex:developer] ok", "--matrix-json", _matrix()])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "pr_metadata_allowed"


def test_gate_accepts_matrix_json_path(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(_matrix(), encoding="utf-8")
    rc = cli.main(["gate", "--title", "[codex:developer] ok", "--intended-commit-title", "[codex:developer] ok", "--matrix-json-path", str(matrix_path)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "pr_metadata_allowed"


def test_gate_accepts_pathlike_matrix_json_compat(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(_matrix(), encoding="utf-8")
    rc = cli.main(["gate", "--title", "[codex:developer] ok", "--intended-commit-title", "[codex:developer] ok", "--matrix-json", str(matrix_path)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "pr_metadata_allowed"


@pytest.mark.no_legacy_skip
def test_gate_accepts_verified_solo_plan_without_matrix(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    title = "[codex:landing] solo evidence"
    plan = seal_validation_plan({"requested_profile": "solo", "effective_profile": "solo", "repository_sha": "a" * 40, "phase": "pr-metadata", "title": title, "intended_commit_title": title, "changed_file_identity": [], "task_acceptance_manifest_digest": None, "task_acceptance_provenance_digest": None, "focused_test_command_contract": ["pytest exact-node"], "targeted_mypy_command_contract": [], "required_stage_ids": ["focused_tests"], "conditionally_required_stage_ids": [], "skipped_or_deferred_stage_ids": ["matrix_summary"], "stage_results": {"focused_tests": {"status": "passed", "duration_seconds": 1}}, "total_validation_duration_seconds": 1, "configured_total_budget_seconds": 1200, "remaining_budget_seconds": 1199, "exhaustive_matrix_status": "not_requested_for_solo_profile", "exhaustive_matrix_digest": None, "overall_status": "ready_for_pr_metadata"})
    plan_path = tmp_path / "validation-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    body = "\n".join(["Validation profile: solo", "Exhaustive matrix disposition: not_requested_for_solo_profile", "Targeted mypy result: not run", "Baseline result: passed", "Docs build result: unchanged", "Prompt-boundary result: passed", "Strict audit result: passed", "Immutability verifier result: passed", "Unresolved risks: none"])
    rc = cli.main(["gate", "--title", title, "--intended-commit-title", title, "--body", body, "--validation-plan-json-path", str(plan_path)])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["decision"] == "pr_metadata_allowed"
    assert payload["lane_contract_summary"]["status"] == "not_required_for_solo_profile"


@pytest.mark.no_legacy_skip
def test_gate_does_not_infer_solo_from_body_without_plan(capsys) -> None:  # type: ignore[no-untyped-def]
    title = "[codex:landing] solo evidence"
    body = "\n".join(["Validation profile: solo", "Exhaustive matrix disposition: not_requested_for_solo_profile", "Targeted mypy result", "Baseline result", "Docs build result", "Prompt-boundary result", "Strict audit result", "Immutability verifier result", "Unresolved risks"])
    rc = cli.main(["gate", "--title", title, "--intended-commit-title", title, "--body", body, "--matrix-json", "{}"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["decision"] == "pr_metadata_blocked"
    assert "validation_evidence_missing" in payload["blocker_codes"]
