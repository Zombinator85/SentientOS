from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_lifecycle_doctor import (
    CodexLifecycleDoctorError,
    CodexLifecycleDoctorRequest,
    build_lifecycle_doctor_report,
)

TITLE = "[codex:landing] add Codex lifecycle doctor CLI"


def _write(path: Path, payload: dict[str, object] | str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True), encoding="utf-8")
    return str(path)


def _matrix(*, required_failure_count: int = 0, results: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {"status": "passed" if required_failure_count == 0 else "failed", "required_failure_count": required_failure_count, "nonproof_count": 0, "diagnostic_failure_count": 0, "results": results or [{"label": "targeted_tests", "required": True, "proof_required": True, "proof_status": "proof-passed", "exit_reason": None}]}


def _finalizer(status: str, **freshness: object) -> dict[str, object]:
    return {"decision": {"status": status}, "evidence_freshness": freshness or {"rerun_required": False, "stale_evidence_refresh_result": "not_required"}}


def _ready_request(tmp_path: Path, **overrides: str) -> CodexLifecycleDoctorRequest:
    paths = {
        "matrix_json_path": _write(tmp_path / "ready_matrix.json", _matrix()),
        "pre_commit_finalizer_json": _write(tmp_path / "pre.json", _finalizer("ready_to_commit")),
        "pr_metadata_finalizer_json": _write(tmp_path / "pr.json", _finalizer("ready_for_pr_metadata", terminal_refresh_status="succeeded")),
        "pr_metadata_guard_json": _write(tmp_path / "guard.json", {"status": "pr_metadata_guard_ready"}),
        "lifecycle_summary_json": _write(tmp_path / "life.json", {"overall_lifecycle_status": "codex_lifecycle_ready", "rerun_required": False, "rerun_reason": None}),
        "test_provenance_json": _write(tmp_path / "prov.json", {"run_intent": "targeted", "execution_mode": "pytest", "tests_selected": 2, "tests_executed": 2, "tests_passed": 2, "tests_skipped": 0, "exit_reason": None}),
    }
    paths.update(overrides)
    return CodexLifecycleDoctorRequest(title=TITLE, intended_commit_title=TITLE, **paths)


def test_doctor_ready_with_mutually_ready_evidence(tmp_path: Path) -> None:
    report = build_lifecycle_doctor_report(_ready_request(tmp_path))
    assert report["overall_doctor_status"] == "doctor_ready"
    assert report["next_safe_action"] == "no_action_ready"
    assert report["test_provenance_summary"]["proof_quality"] is True


def test_incomplete_when_requested_optional_evidence_missing(tmp_path: Path) -> None:
    report = build_lifecycle_doctor_report(_ready_request(tmp_path, pr_metadata_guard_json=str(tmp_path / "missing.json")))
    assert report["overall_doctor_status"] == "doctor_incomplete"
    assert report["next_safe_action"] == "provide_missing_evidence"
    assert "pr_metadata_guard_json" in report["missing_evidence"]


def test_blocked_when_matrix_required_failures(tmp_path: Path) -> None:
    matrix = _write(tmp_path / "blocked_matrix.json", _matrix(required_failure_count=1, results=[{"label": "targeted_tests", "required": True, "proof_required": True, "proof_status": "proof-failed", "exit_reason": "pytest-failed"}]))
    report = build_lifecycle_doctor_report(_ready_request(tmp_path, matrix_json_path=matrix))
    assert report["overall_doctor_status"] == "doctor_blocked"
    assert report["matrix_summary"]["blocked_lanes"][0]["exit_reason"] == "pytest-failed"


def test_blocked_when_required_lane_proof_not_passed_even_with_zero_declared_count(tmp_path: Path) -> None:
    matrix = _write(tmp_path / "matrix.json", _matrix(results=[{"label": "targeted_tests", "required": True, "proof_required": True, "proof_status": "proof-not-executed", "exit_reason": "no-tests-collected"}]))
    report = build_lifecycle_doctor_report(_ready_request(tmp_path, matrix_json_path=matrix))
    assert report["overall_doctor_status"] == "doctor_blocked"
    assert report["matrix_summary"]["blocked_lane_count"] == 1


def test_diagnostic_nonproof_lane_visible_but_nonblocking(tmp_path: Path) -> None:
    matrix = _write(tmp_path / "diag_matrix.json", _matrix(results=[{"label": "diag", "required": False, "proof_required": False, "diagnostic_only": True, "proof_status": "nonproof-diagnostic-failed", "exit_reason": "no-tests-collected"}]))
    report = build_lifecycle_doctor_report(_ready_request(tmp_path, matrix_json_path=matrix))
    assert report["overall_doctor_status"] == "doctor_ready"
    assert report["matrix_summary"]["diagnostic_failure_count"] == 1
    assert report["matrix_summary"]["blocked_lane_count"] == 0


def test_rerun_required_from_finalizer_or_lifecycle(tmp_path: Path) -> None:
    pre = _write(tmp_path / "rerun_pre.json", _finalizer("ready_to_commit", rerun_required=True))
    report = build_lifecycle_doctor_report(_ready_request(tmp_path, pre_commit_finalizer_json=pre))
    assert report["overall_doctor_status"] == "doctor_rerun_required"
    life = _write(tmp_path / "rerun_life.json", {"overall_lifecycle_status": "codex_lifecycle_ready", "rerun_required": True, "rerun_reason": "refresh"})
    report = build_lifecycle_doctor_report(_ready_request(tmp_path, lifecycle_summary_json=life))
    assert report["overall_doctor_status"] == "doctor_rerun_required"


def test_stale_when_finalizer_freshness_requires_refresh(tmp_path: Path) -> None:
    pr = _write(tmp_path / "stale_pr.json", _finalizer("ready_for_pr_metadata", stale_evidence_refresh_result="required_not_allowed"))
    report = build_lifecycle_doctor_report(_ready_request(tmp_path, pr_metadata_finalizer_json=pr))
    assert report["overall_doctor_status"] == "doctor_stale"
    assert report["next_safe_action"] == "rerun_finalizer_with_refresh"


def test_blocked_when_targeted_provenance_not_executed_or_none_passed(tmp_path: Path) -> None:
    prov = _write(tmp_path / "bad_prov.json", {"run_intent": "targeted", "execution_mode": "pytest", "tests_selected": 2, "tests_executed": 0, "tests_passed": 0, "tests_skipped": 2, "exit_reason": "no-tests-collected"})
    report = build_lifecycle_doctor_report(_ready_request(tmp_path, test_provenance_json=prov))
    assert report["overall_doctor_status"] == "doctor_blocked"
    assert report["test_provenance_summary"]["proof_quality"] is False


def test_invalid_json_fails_cleanly(tmp_path: Path) -> None:
    bad = _write(tmp_path / "bad.json", "{")
    with pytest.raises(CodexLifecycleDoctorError, match="matrix_json_path_invalid_json"):
        build_lifecycle_doctor_report(_ready_request(tmp_path, matrix_json_path=bad))


def test_non_authority_posture_fields_are_true(tmp_path: Path) -> None:
    report = build_lifecycle_doctor_report(_ready_request(tmp_path))
    assert report["non_authority_posture"]
    assert all(value is True for value in report["non_authority_posture"].values())


def _index(path: Path, **role_paths: str) -> str:
    artifacts = []
    for role in ("matrix", "pre_commit_finalizer", "pr_metadata_finalizer", "pr_metadata_guard", "lifecycle_summary", "doctor_report", "test_provenance"):
        role_path = role_paths.get(role)
        artifacts.append({"role": role, "path": role_path, "exists": bool(role_path and Path(role_path).exists()), "readable_json": bool(role_path and Path(role_path).exists())})
    payload = {
        "evidence_index_id": "codex_landing_evidence_index_test",
        "artifact_roles_present": [a["role"] for a in artifacts if a["readable_json"]],
        "artifact_roles_missing": [a["role"] for a in artifacts if not a["readable_json"]],
        "artifacts": artifacts,
        "aggregate_hints": {"matrix_status": "passed", "required_failure_count": 0},
        "non_authority_posture": {"index_does_not_decide_readiness": True},
    }
    return _write(path, payload)


def test_doctor_uses_evidence_index_for_omitted_paths(tmp_path: Path) -> None:
    request = _ready_request(tmp_path)
    index = _index(
        tmp_path / "index.json",
        matrix=request.matrix_json_path or "",
        pre_commit_finalizer=request.pre_commit_finalizer_json or "",
        pr_metadata_finalizer=request.pr_metadata_finalizer_json or "",
        pr_metadata_guard=request.pr_metadata_guard_json or "",
        lifecycle_summary=request.lifecycle_summary_json or "",
        test_provenance=request.test_provenance_json or "",
    )
    report = build_lifecycle_doctor_report(CodexLifecycleDoctorRequest(title=TITLE, intended_commit_title=TITLE, evidence_index_json=index))
    assert report["overall_doctor_status"] == "doctor_ready"
    assert report["evidence_inputs"]["matrix_json_path"] == request.matrix_json_path
    assert "matrix" in report["evidence_index_summary"]["used_roles"]
    assert report["non_authority_posture"]["doctor_uses_index_only_as_manifest"] is True
    assert report["non_authority_posture"]["doctor_reads_underlying_artifacts"] is True
    assert report["non_authority_posture"]["doctor_does_not_trust_index_hints_as_authority"] is True


def test_explicit_paths_override_evidence_index_paths(tmp_path: Path) -> None:
    index_request = _ready_request(tmp_path / "indexed")
    explicit_matrix = _write(tmp_path / "explicit_matrix.json", _matrix(required_failure_count=1, results=[{"label": "explicit", "required": True, "proof_required": True, "proof_status": "proof-failed"}]))
    index = _index(tmp_path / "index.json", matrix=index_request.matrix_json_path or "")
    report = build_lifecycle_doctor_report(CodexLifecycleDoctorRequest(title=TITLE, intended_commit_title=TITLE, matrix_json_path=explicit_matrix, evidence_index_json=index))
    assert report["overall_doctor_status"] == "doctor_blocked"
    assert report["evidence_inputs"]["matrix_json_path"] == explicit_matrix
    assert report["evidence_index_summary"]["overridden_roles"] == ["matrix"]


def test_index_hints_do_not_override_underlying_artifact_content(tmp_path: Path) -> None:
    blocked_matrix = _write(tmp_path / "blocked_matrix.json", _matrix(required_failure_count=1, results=[{"label": "underlying", "required": True, "proof_required": True, "proof_status": "proof-failed"}]))
    index = _index(tmp_path / "index.json", matrix=blocked_matrix)
    report = build_lifecycle_doctor_report(CodexLifecycleDoctorRequest(title=TITLE, intended_commit_title=TITLE, evidence_index_json=index))
    assert report["overall_doctor_status"] == "doctor_blocked"
    assert report["matrix_summary"]["required_failure_count"] == 1


def test_index_missing_matrix_is_incomplete(tmp_path: Path) -> None:
    index = _index(tmp_path / "index.json", matrix=str(tmp_path / "missing_matrix.json"))
    report = build_lifecycle_doctor_report(CodexLifecycleDoctorRequest(title=TITLE, intended_commit_title=TITLE, evidence_index_json=index))
    assert report["overall_doctor_status"] == "doctor_incomplete"
    assert "matrix_json_path" in report["missing_evidence"]
    assert report["evidence_index_summary"]["unusable_roles"][0]["role"] == "matrix"


def test_invalid_evidence_index_json_fails_cleanly(tmp_path: Path) -> None:
    bad = _write(tmp_path / "bad_index.json", "{")
    with pytest.raises(CodexLifecycleDoctorError, match="evidence_index_json_invalid_json"):
        build_lifecycle_doctor_report(CodexLifecycleDoctorRequest(title=TITLE, intended_commit_title=TITLE, evidence_index_json=bad))


def test_matrix_path_required_without_evidence_index(tmp_path: Path) -> None:
    report = build_lifecycle_doctor_report(CodexLifecycleDoctorRequest(title=TITLE, intended_commit_title=TITLE))
    assert report["overall_doctor_status"] == "doctor_incomplete"
    assert report["missing_evidence"] == ["matrix_json_path"]
