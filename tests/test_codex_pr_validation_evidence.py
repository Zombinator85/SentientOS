from __future__ import annotations

import json

from sentientos.codex_pr_validation_evidence import verify_pr_validation_evidence


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
