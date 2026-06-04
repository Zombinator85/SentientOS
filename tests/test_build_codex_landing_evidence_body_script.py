from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.codex_pr_landing_gate import verify_pr_landing_gate
from sentientos.codex_pr_metadata_contract import REQUIRED_BODY_MARKERS, verify_pr_metadata
from scripts.build_codex_landing_evidence_body import main

TITLE = "[codex:landing] harden evidence and recovery rail"
pytestmark = pytest.mark.no_legacy_skip


def _matrix(path: Path) -> Path:
    payload = {
        "status": "passed",
        "required_failure_count": 0,
        "command_count": 8,
        "required_failures": [],
        "results": [
            {"label": "targeted_tests", "command": ["python", "-m", "scripts.run_tests", "-q", "tests/test_build_codex_landing_evidence_body_script.py"], "required": True, "exit_code": 0},
            {"label": "targeted_mypy", "command": ["python", "-m", "mypy", "scripts/build_codex_landing_evidence_body.py"], "required": True, "exit_code": 0},
            {"label": "mypy_baseline", "command": ["python", "scripts/check_mypy_baseline.py"], "required": True, "exit_code": 0},
            {"label": "docs_check_deps", "command": ["python", "scripts/build_docs.py", "--check-deps"], "required": False, "exit_code": 0},
            {"label": "docs_build", "command": ["python", "scripts/build_docs.py"], "required": True, "exit_code": 0},
            {"label": "prompt_boundaries", "command": ["python", "scripts/verify_context_hygiene_prompt_boundaries.py"], "required": True, "exit_code": 0},
            {"label": "strict_audits", "command": ["python", "verify_audits.py", "--strict"], "required": True, "exit_code": 0},
            {"label": "audit_immutability", "command": ["python", "scripts/audit_immutability_verifier.py"], "required": True, "exit_code": 0},
        ],
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _build(tmp_path: Path) -> Path:
    matrix = _matrix(tmp_path / "matrix.json")
    supervisor = tmp_path / "supervisor.json"
    supervisor.write_text(json.dumps({"decision": {"status": "ready_for_pr_metadata"}, "report": {"reasons": []}}, sort_keys=True), encoding="utf-8")
    output = tmp_path / "body.txt"
    code = main(
        [
            "--title",
            TITLE,
            "--intended-commit-title",
            TITLE,
            "--matrix-json-path",
            str(matrix),
            "--landing-supervisor-json-path",
            str(supervisor),
            "--output",
            str(output),
            "--targeted-mypy",
            "passed",
            "--baseline",
            "passed",
            "--docs-build",
            "passed",
            "--prompt-boundary",
            "passed",
            "--strict-audit",
            "passed",
            "--immutability-verifier",
            "passed",
            "--landing-gate",
            "passed",
            "--finalizer",
            "pre-commit ready_to_commit; post-commit ready_for_pr_metadata",
            "--pr-metadata-guard",
            "pr_metadata_guard_ready",
            "--unresolved-risks",
            "None known.",
        ]
    )
    assert code == 0
    return output


def test_generated_body_includes_matrix_output_path(tmp_path: Path) -> None:
    output = _build(tmp_path)
    assert f"Matrix output path: {tmp_path / 'matrix.json'}" in output.read_text(encoding="utf-8")


def test_generated_body_includes_unresolved_risks(tmp_path: Path) -> None:
    body = _build(tmp_path).read_text(encoding="utf-8")
    assert "### Unresolved risks" in body
    assert "Unresolved risks: None known." in body


def test_generated_body_includes_every_pr_metadata_guard_required_marker(tmp_path: Path) -> None:
    body = _build(tmp_path).read_text(encoding="utf-8")
    result = verify_pr_metadata(pr_title=TITLE, intended_commit_title=TITLE, pr_body=body)
    assert result.status == "codex_pr_metadata_contract_ready"
    for marker in REQUIRED_BODY_MARKERS:
        assert marker in " ".join(body.lower().split())


def test_missing_matrix_json_fails(tmp_path: Path) -> None:
    output = tmp_path / "body.txt"
    code = main(["--title", TITLE, "--intended-commit-title", TITLE, "--matrix-json-path", str(tmp_path / "missing.json"), "--landing-supervisor-json-path", str(tmp_path / "supervisor.json"), "--output", str(output)])
    assert code == 1
    assert not output.exists()


def test_missing_matrix_path_marker_fails(tmp_path: Path) -> None:
    from scripts.build_codex_landing_evidence_body import validate_body

    matrix = _matrix(tmp_path / "matrix.json")
    body = _build(tmp_path).read_text(encoding="utf-8").replace(f"Matrix output path: {matrix}", "Matrix output path omitted")
    try:
        validate_body(body, matrix_json_path=matrix)
    except ValueError as exc:
        assert "Matrix output path" in str(exc)
    else:
        raise AssertionError("validate_body accepted a body without the matrix path marker")


def test_generated_body_passes_landing_gate_without_matrix_output_reference_missing(tmp_path: Path) -> None:
    matrix = _matrix(tmp_path / "matrix.json")
    body = _build(tmp_path).read_text(encoding="utf-8")
    result = verify_pr_landing_gate(proposed_pr_title=TITLE, intended_commit_title=TITLE, proposed_pr_body=body, matrix_json_text=matrix.read_text(encoding="utf-8"))
    assert result.decision == "pr_metadata_allowed"
    assert "matrix_output_reference_missing" not in result.blocker_codes


def test_script_is_deterministic(tmp_path: Path) -> None:
    first = _build(tmp_path).read_text(encoding="utf-8")
    second = _build(tmp_path).read_text(encoding="utf-8")
    assert first == second
