from __future__ import annotations

from copy import deepcopy

from sentientos.forge_failures import semantic_failure_signature
from sentientos.validation_causality import (
    STATUS_BASE_INVALID,
    STATUS_CANDIDATE_INVALID,
    STATUS_COMMAND_MISMATCH,
    STATUS_ENVIRONMENT_MISMATCH,
    STATUS_IMPROVED,
    STATUS_INCOMPLETE,
    STATUS_NO_REGRESSION,
    STATUS_REGRESSION,
    compare_runs,
    command_contract_digest,
    digest_json,
    environment_digest,
    verify_comparison,
)

BASE = "a" * 40
CANDIDATE = "b" * 40
WORKSPACE = "sha256:" + "c" * 64
COMMAND = "pytest -q"
ENVIRONMENT = "test-env"


def _failure(nodeid: str = "tests/test_x.py::test_x", message: str = "boom", count: int = 1, line: int = 10) -> dict[str, object]:
    return {
        "signature": semantic_failure_signature(nodeid, "AssertionError", message),
        "nodeid": nodeid,
        "exception_type": "AssertionError",
        "message": message,
        "count": count,
        "line": line,
    }


def _run(sha: str, identity: str, failures: list[dict[str, object]], *, command: str = COMMAND, environment: str = ENVIRONMENT, complete: bool = True) -> dict[str, object]:
    failed = sum(int(row["count"]) for row in failures)
    argv = ["python", "-m", *command.split()]
    environment_identity = {"identity": environment}
    return {
        "repository_sha": sha,
        "workspace_identity": identity,
        "command_contract_digest": command_contract_digest(argv),
        "command_contract": {"runner": argv[2], "argv": argv},
        "environment_digest": environment_digest(environment_identity),
        "environment_identity": environment_identity,
        "complete": complete,
        "exit_code": 1 if failed else 0,
        "tests_collected": 2,
        "tests_executed": 2,
        "junit_sha256": "sha256:" + "f" * 64,
        "normalized_failure_multiset": failures,
    }


def _comparison(base: list[dict[str, object]], candidate: list[dict[str, object]]) -> dict[str, object]:
    return compare_runs(
        immutable_base_sha=BASE,
        candidate_sha=CANDIDATE,
        candidate_workspace_identity=WORKSPACE,
        base_run=_run(BASE, "sha256:" + "1" * 64, base),
        candidate_run=_run(CANDIDATE, WORKSPACE, candidate),
    )


def _verify(evidence: dict[str, object], **overrides: str) -> dict[str, object]:
    return verify_comparison(
        evidence,
        immutable_base_sha=overrides.get("base", BASE),
        candidate_sha=overrides.get("candidate", CANDIDATE),
        candidate_workspace_identity=overrides.get("workspace", WORKSPACE),
    )


def test_base_clean_candidate_clean_is_no_regression() -> None:
    result = _comparison([], [])
    assert result["status"] == STATUS_NO_REGRESSION
    assert not result["new_candidate_failures"]
    assert result["repository_health_status"] == "green"


def test_identical_base_candidate_failure_is_matched_visible_debt() -> None:
    failure = _failure()
    result = _comparison([failure], [failure])
    assert result["status"] == STATUS_NO_REGRESSION
    assert result["matched_preexisting_failures"] == [{"signature": failure["signature"], "nodeid": failure["nodeid"], "count": 1}]
    assert result["repository_health_status"] == "red"


def test_candidate_new_failure_blocks_even_when_base_failure_remains() -> None:
    result = _comparison([_failure(message="A")], [_failure(message="A"), _failure(message="B", nodeid="tests/test_y.py::test_y")])
    assert result["status"] == STATUS_REGRESSION
    assert [row["message"] if "message" in row else row["nodeid"] for row in result["new_candidate_failures"]] == ["tests/test_y.py::test_y"]


def test_candidate_retiring_failures_is_improvement() -> None:
    result = _comparison([_failure(message="A"), _failure(message="B", nodeid="tests/test_y.py::test_y")], [_failure(message="A")])
    assert result["status"] == STATUS_IMPROVED
    assert len(result["retired_or_improved_failures"]) == 1


def test_changed_failure_at_same_node_is_regression() -> None:
    result = _comparison([_failure(message="A")], [_failure(message="B")])
    assert result["status"] == STATUS_REGRESSION
    assert result["changed_failure_signatures"][0]["nodeid"] == "tests/test_x.py::test_x"


def test_increased_failure_multiplicity_is_regression() -> None:
    result = _comparison([_failure(count=1)], [_failure(count=2)])
    assert result["status"] == STATUS_REGRESSION
    assert result["failure_multiplicity_changes"][0]["delta"] == 1


def test_line_movement_is_diagnostic_not_semantic_identity() -> None:
    before = _failure(line=12)
    after = _failure(line=820)
    result = _comparison([before], [after])
    assert result["status"] == STATUS_NO_REGRESSION


def test_wrong_immutable_base_and_stale_base_run_are_rejected() -> None:
    evidence = _comparison([], [])
    assert _verify(evidence, base="9" * 40)["status"] == STATUS_BASE_INVALID
    stale = deepcopy(evidence)
    stale["base_run_provenance"]["repository_sha"] = "9" * 40
    stale.pop("comparison_digest")
    stale["base_run_provenance_digest"] = digest_json(stale["base_run_provenance"])
    stale["comparison_digest"] = digest_json(stale)
    assert _verify(stale)["status"] == STATUS_BASE_INVALID


def test_candidate_workspace_mismatch_is_rejected() -> None:
    assert _verify(_comparison([], []), workspace="sha256:" + "9" * 64)["status"] == STATUS_CANDIDATE_INVALID


def test_command_contract_mismatch_is_rejected() -> None:
    base = _run(BASE, "sha256:" + "1" * 64, [], command="pytest -q --maxfail=1")
    candidate = _run(CANDIDATE, WORKSPACE, [])
    assert compare_runs(immutable_base_sha=BASE, candidate_sha=CANDIDATE, candidate_workspace_identity=WORKSPACE, base_run=base, candidate_run=candidate)["status"] == STATUS_COMMAND_MISMATCH


def test_materially_incompatible_environment_is_rejected() -> None:
    base = _run(BASE, "sha256:" + "1" * 64, [])
    candidate = _run(CANDIDATE, WORKSPACE, [], environment="other-env")
    assert compare_runs(immutable_base_sha=BASE, candidate_sha=CANDIDATE, candidate_workspace_identity=WORKSPACE, base_run=base, candidate_run=candidate)["status"] == STATUS_ENVIRONMENT_MISMATCH


def test_incomplete_base_or_candidate_run_is_indeterminate() -> None:
    incomplete_base = _run(BASE, "sha256:" + "1" * 64, [], complete=False)
    candidate = _run(CANDIDATE, WORKSPACE, [])
    assert compare_runs(immutable_base_sha=BASE, candidate_sha=CANDIDATE, candidate_workspace_identity=WORKSPACE, base_run=incomplete_base, candidate_run=candidate)["status"] == STATUS_INCOMPLETE
    base = _run(BASE, "sha256:" + "1" * 64, [])
    incomplete_candidate = _run(CANDIDATE, WORKSPACE, [], complete=False)
    assert compare_runs(immutable_base_sha=BASE, candidate_sha=CANDIDATE, candidate_workspace_identity=WORKSPACE, base_run=base, candidate_run=incomplete_candidate)["status"] == STATUS_INCOMPLETE


def test_self_refreshed_candidate_sha_cannot_replace_immutable_base() -> None:
    evidence = _comparison([], [])
    assert _verify(evidence, base=CANDIDATE)["status"] == STATUS_BASE_INVALID


def test_comparison_digest_detects_evidence_tampering() -> None:
    evidence = _comparison([], [])
    evidence["new_candidate_failures"] = [{"signature": "forged"}]
    assert _verify(evidence)["status"] == STATUS_INCOMPLETE
