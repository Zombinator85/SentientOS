from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_landing_evidence_index import CodexLandingEvidenceIndexRequest, build_landing_evidence_index

TITLE = "[codex:landing] add Codex landing evidence index"


def _write(path: Path, payload: dict[str, object] | str) -> str:
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True), encoding="utf-8")
    return str(path)


def _digest(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _request(tmp_path: Path, **overrides: str | None) -> CodexLandingEvidenceIndexRequest:
    paths: dict[str, str | None] = {
        "matrix_json_path": _write(tmp_path / "matrix.json", {"status": "passed", "required_failure_count": 0, "results": []}),
        "pre_commit_finalizer_json": _write(tmp_path / "pre.json", {"decision": {"status": "ready_to_commit"}}),
        "pr_metadata_finalizer_json": _write(tmp_path / "pr.json", {"decision": {"status": "ready_for_pr_metadata"}}),
        "pr_metadata_guard_json": _write(tmp_path / "guard.json", {"status": "pr_metadata_guard_ready"}),
        "lifecycle_summary_json": _write(tmp_path / "life.json", {"overall_lifecycle_status": "codex_lifecycle_ready"}),
        "doctor_report_json": _write(tmp_path / "doctor.json", {"overall_doctor_status": "doctor_ready"}),
        "test_provenance_json": _write(tmp_path / "prov.json", {"exit_reason": "tests-passed", "provenance_hash": "abc"}),
    }
    paths.update(overrides)
    return CodexLandingEvidenceIndexRequest(title=TITLE, intended_commit_title=TITLE, **paths)


def test_building_index_records_all_roles_and_digests(tmp_path: Path) -> None:
    request = _request(tmp_path)
    index = build_landing_evidence_index(request)
    assert index["artifact_count"] == 7
    assert index["artifact_roles_missing"] == []
    assert set(index["artifact_roles_present"]) == {"matrix", "pre_commit_finalizer", "pr_metadata_finalizer", "pr_metadata_guard", "lifecycle_summary", "doctor_report", "test_provenance"}
    by_role = {artifact["role"]: artifact for artifact in index["artifacts"]}
    assert by_role["matrix"]["digest"] == _digest(request.matrix_json_path or "")
    assert by_role["matrix"]["digest_algo"] == "sha256"
    assert by_role["pr_metadata_guard"]["status_hint"] == "pr_metadata_guard_ready"


def test_missing_optional_paths_are_recorded_without_crashing(tmp_path: Path) -> None:
    index = build_landing_evidence_index(_request(tmp_path, doctor_report_json=None, test_provenance_json=str(tmp_path / "missing.json")))
    by_role = {artifact["role"]: artifact for artifact in index["artifacts"]}
    assert by_role["doctor_report"]["error"] == "path_not_provided"
    assert by_role["test_provenance"]["error"] == "path_missing"
    assert "doctor_report" in index["artifact_roles_missing"]
    assert "test_provenance" in index["artifact_roles_missing"]


def test_invalid_json_is_unreadable_but_digest_is_recorded(tmp_path: Path) -> None:
    invalid = _write(tmp_path / "invalid.json", "{")
    index = build_landing_evidence_index(_request(tmp_path, pr_metadata_guard_json=invalid))
    guard = {artifact["role"]: artifact for artifact in index["artifacts"]}["pr_metadata_guard"]
    assert guard["exists"] is True
    assert guard["readable_json"] is False
    assert guard["digest"] == _digest(invalid)
    assert str(guard["error"]).startswith("invalid_json:")


def test_aggregate_hints_are_extracted_without_deciding_readiness(tmp_path: Path) -> None:
    index = build_landing_evidence_index(_request(tmp_path))
    assert index["aggregate_hints"] == {
        "matrix_status": "passed",
        "required_failure_count": 0,
        "doctor_status": "doctor_ready",
        "lifecycle_status": "codex_lifecycle_ready",
        "pre_commit_finalizer_status": "ready_to_commit",
        "pr_metadata_finalizer_status": "ready_for_pr_metadata",
        "pr_metadata_guard_status": "pr_metadata_guard_ready",
        "test_provenance_exit_reason": "tests-passed",
    }
    assert "ready_to_commit" not in index
    assert index["non_authority_posture"]["index_does_not_decide_readiness"] is True


def test_non_authority_posture_fields_are_present_and_true(tmp_path: Path) -> None:
    posture = build_landing_evidence_index(_request(tmp_path))["non_authority_posture"]
    assert posture
    assert all(value is True for value in posture.values())


def test_index_output_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    request = _request(tmp_path)
    assert build_landing_evidence_index(request) == build_landing_evidence_index(request)
