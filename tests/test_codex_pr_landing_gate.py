from __future__ import annotations

import json

from sentientos.codex_pr_landing_gate import build_and_verify_pr_body, verify_pr_landing_gate


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
