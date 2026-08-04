from __future__ import annotations

import json
import pytest

from sentientos.codex_pr_landing_gate import build_and_verify_pr_body, verify_pr_landing_gate
from sentientos.landing_validation_plan import seal_validation_plan


@pytest.mark.no_legacy_skip
def test_solo_profile_lands_without_exhaustive_matrix() -> None:
    title = "[codex:x] task"
    plan = seal_validation_plan({"requested_profile": "solo", "effective_profile": "solo", "repository_sha": "a" * 40, "phase": "pre-commit", "title": title, "intended_commit_title": title, "changed_file_identity": [], "task_acceptance_manifest_digest": None, "task_acceptance_provenance_digest": None, "focused_test_command_contract": ["pytest x"], "targeted_mypy_command_contract": [], "required_stage_ids": [], "conditionally_required_stage_ids": [], "skipped_or_deferred_stage_ids": ["matrix_summary"], "stage_results": {}, "total_validation_duration_seconds": 1, "configured_total_budget_seconds": 1200, "remaining_budget_seconds": 1199, "exhaustive_matrix_status": "not_requested_for_solo_profile", "exhaustive_matrix_digest": None, "overall_status": "ready_to_commit"})
    result = verify_pr_landing_gate(proposed_pr_title=title, intended_commit_title=title, proposed_pr_body="\n".join(["full command matrix results", "matrix runner --summary result", "matrix runner --output result/path", "targeted mypy result", "baseline result", "docs build result", "prompt-boundary result", "strict audit result", "immutability verifier result", "unresolved risks"]), validation_plan_json_text=json.dumps(plan))
    assert result.status == "codex_pr_landing_gate_ready"


def _matrix(**overrides: object) -> str:
    payload = {
        "status": "passed",
        "required_failure_count": 0,
        "results": [
            {"label": "targeted_tests", "exit_code": 0, "required": True},
            {"label": "targeted_mypy", "exit_code": 0, "required": True},
            {"label": "mypy_baseline", "exit_code": 0, "required": True},
            {"label": "docs_check_deps", "exit_code": 0, "required": False},
            {"label": "docs_build", "exit_code": 0, "required": True},
            {"label": "prompt_boundaries", "exit_code": 0, "required": True},
            {"label": "strict_audits", "exit_code": 0, "required": True},
            {"label": "audit_immutability", "exit_code": 0, "required": True},
        ],
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_mismatched_intended_commit_title_blocks() -> None:
    res = verify_pr_landing_gate(proposed_pr_title="[codex:developer] a", intended_commit_title="[codex:developer] b", proposed_pr_body="local tests only", matrix_json_text=_matrix())
    assert res.decision == "pr_metadata_blocked"


def test_matrix_failed_blocks_even_when_body_claims_pass() -> None:
    res = build_and_verify_pr_body(proposed_pr_title="[codex:developer] ok", intended_commit_title="[codex:developer] ok", matrix_json_text=_matrix(status="failed", required_failure_count=1))
    assert "matrix_status_not_passed" in res.blocker_codes


def test_gate_build_body_passes() -> None:
    res = build_and_verify_pr_body(proposed_pr_title="[codex:developer] ok", intended_commit_title="[codex:developer] ok", matrix_json_text=_matrix())
    assert res.decision == "pr_metadata_allowed"
