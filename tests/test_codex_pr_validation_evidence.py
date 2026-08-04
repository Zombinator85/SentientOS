from __future__ import annotations

import json
import pytest

from sentientos.codex_pr_validation_evidence import verify_pr_validation_evidence
from sentientos.landing_validation_plan import seal_validation_plan


def _body() -> str:
    return """
## Full command matrix results
ok
## Matrix runner --summary result
ok
## Matrix runner --output result/path
artifacts/matrix/latest.json
## Targeted mypy result
ok
## Baseline result
ok
## Docs build result
ok
## Prompt-boundary result
ok
## Strict audit result
ok
## Immutability verifier result
ok
## Unresolved risks
none
"""


def _solo_plan() -> dict[str, object]:
    return seal_validation_plan({"requested_profile": "solo", "effective_profile": "solo", "repository_sha": "a" * 40, "phase": "pre-commit", "title": "[codex:x] task", "intended_commit_title": "[codex:x] task", "changed_file_identity": [], "task_acceptance_manifest_digest": None, "task_acceptance_provenance_digest": None, "focused_test_command_contract": ["pytest x"], "targeted_mypy_command_contract": [], "required_stage_ids": ["focused_tests"], "conditionally_required_stage_ids": [], "skipped_or_deferred_stage_ids": ["matrix_summary"], "stage_results": {"focused_tests": {"status": "passed", "duration_seconds": 1}}, "total_validation_duration_seconds": 1, "configured_total_budget_seconds": 1200, "remaining_budget_seconds": 1199, "exhaustive_matrix_status": "not_requested_for_solo_profile", "exhaustive_matrix_digest": None, "overall_status": "ready_to_commit"})


@pytest.mark.no_legacy_skip
def test_solo_profile_accepts_bound_validation_plan_without_matrix() -> None:
    result = verify_pr_validation_evidence(pr_title="[codex:x] task", intended_commit_title="[codex:x] task", pr_body=_body(), validation_plan_json_text=json.dumps(_solo_plan()))
    assert result.status == "codex_pr_validation_evidence_ready"


@pytest.mark.no_legacy_skip
def test_solo_profile_rejects_fake_matrix_pass_claim() -> None:
    plan = _solo_plan(); plan["exhaustive_matrix_status"] = "matrix_passed"
    result = verify_pr_validation_evidence(pr_title="[codex:x] task", intended_commit_title="[codex:x] task", pr_body=_body(), validation_plan_json_text=json.dumps(plan))
    assert "solo_matrix_status_inconsistent" in result.findings


def _matrix(status: str = "passed", required_failure_count: int = 0, targeted_mypy: int = 0, strict: int = 0, docs_check: int = 0, docs_build: int = 0, docs_recheck: int | None = None) -> str:
    rows = [
        {"label": "targeted_mypy", "exit_code": targeted_mypy, "required": True},
        {"label": "mypy_baseline", "exit_code": 0, "required": True},
        {"label": "docs_check_deps", "exit_code": docs_check, "required": False},
        {"label": "docs_build", "exit_code": docs_build, "required": True},
        {"label": "prompt_boundaries", "exit_code": 0, "required": True},
        {"label": "strict_audits", "exit_code": strict, "required": True},
        {"label": "audit_immutability", "exit_code": 0, "required": True},
    ]
    if docs_recheck is not None:
        rows.append({"label": "docs_bootstrap", "exit_code": 0, "required": False})
        rows.append({"label": "docs_check_deps_recheck", "exit_code": docs_recheck, "required": True})
    return json.dumps({"status": status, "required_failure_count": required_failure_count, "results": rows})


def test_local_only_body_fails_1740() -> None:
    res = verify_pr_validation_evidence(pr_title="[codex:developer] ok", pr_body="local tests only")
    assert res.status.endswith("incomplete")


def test_valid_body_with_passing_matrix_passes() -> None:
    res = verify_pr_validation_evidence(pr_title="[codex:developer] ok", pr_body=_body(), matrix_json_text=_matrix())
    assert res.status.endswith("ready")


def test_claim_pass_but_matrix_failed_fails() -> None:
    res = verify_pr_validation_evidence(pr_title="[codex:developer] ok", pr_body=_body(), matrix_json_text=_matrix(status="failed", required_failure_count=1))
    assert "matrix_status_not_passed" in res.findings


def test_targeted_mypy_claim_fails_when_lane_failed() -> None:
    res = verify_pr_validation_evidence(pr_title="[codex:developer] ok", pr_body=_body(), matrix_json_text=_matrix(targeted_mypy=1, required_failure_count=1, status="failed"))
    assert "targeted_mypy_not_passed" in res.findings


def test_docs_bootstrap_recovery_passes() -> None:
    res = verify_pr_validation_evidence(pr_title="[codex:developer] ok", pr_body=_body(), matrix_json_text=_matrix(docs_check=1, docs_recheck=0, docs_build=0))
    assert "docs_check_or_recovery_not_passed" not in res.findings


def test_missing_audits_lane_fails() -> None:
    payload = json.loads(_matrix())
    payload["results"] = [r for r in payload["results"] if r["label"] != "strict_audits"]
    res = verify_pr_validation_evidence(pr_title="[codex:developer] ok", pr_body=_body(), matrix_json_text=json.dumps(payload))
    assert "strict_audits_not_passed" in res.findings
