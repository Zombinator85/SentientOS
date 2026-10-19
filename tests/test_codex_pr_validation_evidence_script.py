from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import codex_pr_validation_evidence as cli
from sentientos.landing_validation_plan import seal_validation_plan


def test_verify_fails_without_matrix(capsys) -> None:  # type: ignore[no-untyped-def]
    rc = cli.main(["verify", "--title", "[codex:developer] ok", "--body", "local tests only"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert "matrix_evidence_missing" in payload["findings"]


def test_build_from_matrix(capsys) -> None:  # type: ignore[no-untyped-def]
    matrix = json.dumps({"status": "passed", "required_failure_count": 0, "results": [{"label": "targeted_mypy", "exit_code": 0}, {"label": "mypy_baseline", "exit_code": 0}, {"label": "docs_build", "exit_code": 0}, {"label": "prompt_boundaries", "exit_code": 0}, {"label": "strict_audits", "exit_code": 0}, {"label": "audit_immutability", "exit_code": 0}, {"label": "docs_check_deps", "exit_code": 0}]})
    rc = cli.main(["build", "--matrix-json", matrix])
    assert rc == 0
    assert "Matrix runner --output result/path" in capsys.readouterr().out


@pytest.mark.no_legacy_skip
def test_verify_accepts_validation_plan_file_for_solo_profile(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    title = "[codex:landing] solo evidence"
    plan = seal_validation_plan({"requested_profile": "solo", "effective_profile": "solo", "repository_sha": "a" * 40, "phase": "pr-metadata", "title": title, "intended_commit_title": title, "changed_file_identity": [], "task_acceptance_manifest_digest": None, "task_acceptance_provenance_digest": None, "focused_test_command_contract": ["pytest exact-node"], "targeted_mypy_command_contract": [], "required_stage_ids": ["focused_tests"], "conditionally_required_stage_ids": [], "skipped_or_deferred_stage_ids": ["matrix_summary"], "stage_results": {"focused_tests": {"status": "passed", "duration_seconds": 1}}, "total_validation_duration_seconds": 1, "configured_total_budget_seconds": 1200, "remaining_budget_seconds": 1199, "exhaustive_matrix_status": "not_requested_for_solo_profile", "exhaustive_matrix_digest": None, "overall_status": "ready_for_pr_metadata"})
    plan_path = tmp_path / "validation-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    body = "\n".join(["Validation profile: solo", "Exhaustive matrix disposition: not_requested_for_solo_profile", "Targeted mypy result", "Baseline result", "Docs build result", "Prompt-boundary result", "Strict audit result", "Immutability verifier result", "Unresolved risks"])
    rc = cli.main(["verify", "--title", title, "--intended-commit-title", title, "--body", body, "--validation-plan-json-path", str(plan_path)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["status"] == "codex_pr_validation_evidence_ready"
