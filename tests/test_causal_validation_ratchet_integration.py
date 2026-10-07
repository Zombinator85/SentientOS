from __future__ import annotations

from sentientos.codex_finalize_landing import (
    CodexFinalizeLandingCommandResult,
    CodexFinalizeLandingRequest,
    evaluate_finalize_landing,
)
from sentientos.forge_failures import semantic_failure_signature
from sentientos.validation_causality import (
    STATUS_NO_REGRESSION,
    STATUS_REGRESSION,
    compare_runs,
    command_contract_digest,
    environment_digest,
    verify_comparison,
)

BASE = "a" * 40
CANDIDATE = "b" * 40
WORKSPACE = "sha256:" + "c" * 64
NODE = "tests/test_debt.py::test_legacy"
ARGV = ["python", "-m", "scripts.run_tests", "-q", NODE]
ENVIRONMENT = {"python_version": "3.11", "pytest": "8.4"}


def _failure(message: str) -> dict[str, object]:
    return {
        "signature": semantic_failure_signature(NODE, "AssertionError", message),
        "nodeid": NODE,
        "exception_type": "AssertionError",
        "message": message,
        "count": 1,
    }


def _run(sha: str, workspace: str, failures: list[dict[str, object]]) -> dict[str, object]:
    return {
        "repository_sha": sha,
        "workspace_identity": workspace,
        "command_contract": {"runner": "scripts.run_tests", "argv": ARGV},
        "command_contract_digest": command_contract_digest(ARGV),
        "environment_identity": ENVIRONMENT,
        "environment_digest": environment_digest(ENVIRONMENT),
        "complete": True,
        "exit_code": 1 if failures else 0,
        "tests_collected": 1,
        "tests_executed": 1,
        "junit_sha256": "sha256:" + "d" * 64,
        "normalized_failure_multiset": failures,
    }


def _evidence(candidate_failures: list[dict[str, object]]) -> dict[str, object]:
    return compare_runs(
        immutable_base_sha=BASE,
        candidate_sha=CANDIDATE,
        candidate_workspace_identity=WORKSPACE,
        base_run=_run(BASE, "sha256:" + "1" * 64, [_failure("pre-existing invariant")]),
        candidate_run=_run(CANDIDATE, WORKSPACE, candidate_failures),
    )


def _landing(evidence: dict[str, object]):
    request = CodexFinalizeLandingRequest(
        title="x",
        intended_commit_title="x",
        matrix_json_path="/tmp/matrix.json",
        phase="pre-commit",
        focused_test_commands=("focused",),
        repository_sha=CANDIDATE,
        immutable_base_sha=BASE,
        candidate_workspace_identity=WORKSPACE,
        causal_validation_evidence=evidence,
        causal_validation_expected_command_digest=str(evidence["command_contract_digest"]),
        task_acceptance_status="task_acceptance_ready",
        protected_corridor_status="passed",
        require_causal_validation=True,
    )
    commands = (
        CodexFinalizeLandingCommandResult("focused_tests", "focused", 0),
        CodexFinalizeLandingCommandResult(
            "broad_validation", "scripts.run_tests -q " + NODE, 1,
            output_tail="FAILED " + NODE + " - AssertionError: pre-existing invariant",
            command_contract_digest=str(evidence["command_contract_digest"]),
        ),
    )
    return evaluate_finalize_landing(request, commands, ())


def test_matched_health_debt_flows_through_finalizer_without_task_regression() -> None:
    evidence = _evidence([_failure("pre-existing invariant")])
    assert evidence["status"] == STATUS_NO_REGRESSION
    assert evidence["repository_health_status"] == "red"
    assert verify_comparison(
        evidence,
        immutable_base_sha=BASE,
        candidate_sha=CANDIDATE,
        candidate_workspace_identity=WORKSPACE,
    )["status"] == STATUS_NO_REGRESSION

    result = _landing(evidence)

    assert result.decision.status == "ready_to_commit"
    assert result.report.assessments["repository_health_status"] == "red"
    assert result.report.assessments["regression_gate_status"] == "no_regression"
    assert result.report.commands[-1].exit_code == 1


def test_new_candidate_failure_flows_through_finalizer_as_blocking_regression() -> None:
    evidence = _evidence([_failure("candidate changed invariant")])
    assert evidence["status"] == STATUS_REGRESSION

    result = _landing(evidence)

    assert result.decision.status == "repair_required_task_caused"
    assert "candidate_regression_detected" in result.decision.reasons
