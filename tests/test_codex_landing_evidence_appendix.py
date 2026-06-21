from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_landing_evidence_appendix import CodexLandingEvidenceAppendixError, CodexLandingEvidenceAppendixRequest, build_landing_evidence_appendix

TITLE = "[codex:landing] render Codex landing evidence appendix"


def _write(path: Path, payload: dict[str, object] | str) -> str:
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True), encoding="utf-8")
    return str(path)


def _index() -> dict[str, object]:
    return {
        "evidence_index_id": "idx",
        "artifact_count": 2,
        "artifact_roles_present": ["matrix"],
        "artifact_roles_missing": ["doctor_report"],
        "aggregate_hints": {"required_failure_count": 0, "pre_commit_finalizer_status": "ready_to_commit", "pr_metadata_guard_status": "pr_metadata_guard_ready"},
        "artifacts": [
            {"role": "matrix", "path": "/tmp/matrix.json", "exists": True, "readable_json": True, "digest": "sha256:abcdef1234567890", "status_hint": "passed", "schema_hint": "work_item_review_packet_matrix"},
            {"role": "doctor|report", "path": "line1\nline2", "exists": False, "readable_json": False, "digest": None, "error": "path|missing"},
        ],
    }


def _doctor(status: str = "doctor_ready") -> dict[str, object]:
    return {
        "doctor_report_id": "doctor",
        "overall_doctor_status": status,
        "readiness_summary": "rendered evidence only",
        "next_safe_action": "no_action_ready",
        "next_safe_action_reason": "doctor field only",
        "missing_evidence": [],
        "matrix_summary": {"required_failure_count": 0, "nonproof_count": 1, "diagnostic_failure_count": 2, "blocked_lane_count": 3},
        "finalizer_summary": {"pre_commit_status": "ready_to_commit", "pr_metadata_status": "ready_for_pr_metadata", "rerun_required": {"pre_commit": False, "pr_metadata": False}, "terminal_refresh_status": {"pre_commit": None, "pr_metadata": "succeeded"}},
        "pr_metadata_guard_summary": {"status": "pr_metadata_guard_ready"},
        "test_provenance_summary": {"run_intent": "targeted", "execution_mode": "pytest", "tests_selected": 2, "tests_executed": 2, "tests_passed": 2, "tests_skipped": 0, "exit_reason": None},
    }


def _render(tmp_path: Path, *, index: dict[str, object] | None = None, doctor: dict[str, object] | None = None) -> tuple[str, dict[str, object]]:
    index_path = _write(tmp_path / "index.json", index) if index is not None else None
    doctor_path = _write(tmp_path / "doctor.json", doctor) if doctor is not None else None
    return build_landing_evidence_appendix(CodexLandingEvidenceAppendixRequest(TITLE, TITLE, output=str(tmp_path / "out.md"), evidence_index_json=index_path, doctor_report_json=doctor_path))


def test_rendering_appendix_from_evidence_index_only(tmp_path: Path) -> None:
    markdown, metadata = _render(tmp_path, index=_index())
    assert "# Codex Landing Evidence Appendix" in markdown
    assert "**evidence_index_id:** idx" in markdown
    assert "| matrix | /tmp/matrix.json | true | true | sha256:abcdef123456" in markdown
    assert "Lifecycle doctor report JSON was not provided." in markdown
    assert metadata["evidence_index_provided"] is True


def test_rendering_appendix_from_doctor_report_only(tmp_path: Path) -> None:
    markdown, metadata = _render(tmp_path, doctor=_doctor())
    assert "Evidence index JSON was not provided." in markdown
    assert "**overall_doctor_status:** doctor_ready" in markdown
    assert "**blocked_lane_count:** 3" in markdown
    assert metadata["doctor_report_provided"] is True


def test_rendering_appendix_from_both_index_and_doctor_report(tmp_path: Path) -> None:
    markdown, _metadata = _render(tmp_path, index=_index(), doctor=_doctor("doctor_blocked"))
    assert "**evidence_index_id:** idx" in markdown
    assert "**overall_doctor_status:** doctor_blocked" in markdown
    assert "**pr_metadata_guard_status:** pr_metadata_guard_ready" in markdown


def test_missing_optional_inputs_render_as_not_provided(tmp_path: Path) -> None:
    markdown, metadata = _render(tmp_path)
    assert "Evidence index JSON was not provided." in markdown
    assert "Lifecycle doctor report JSON was not provided." in markdown
    assert metadata["appendix_is_non_authoritative"] is True


def test_invalid_index_json_fails_cleanly(tmp_path: Path) -> None:
    bad = _write(tmp_path / "bad_index.json", "{")
    with pytest.raises(CodexLandingEvidenceAppendixError, match="evidence_index_json_invalid_json"):
        build_landing_evidence_appendix(CodexLandingEvidenceAppendixRequest(TITLE, TITLE, evidence_index_json=bad))


def test_invalid_doctor_json_fails_cleanly(tmp_path: Path) -> None:
    bad = _write(tmp_path / "bad_doctor.json", "{")
    with pytest.raises(CodexLandingEvidenceAppendixError, match="doctor_report_json_invalid_json"):
        build_landing_evidence_appendix(CodexLandingEvidenceAppendixRequest(TITLE, TITLE, doctor_report_json=bad))


def test_missing_provided_json_path_fails_cleanly(tmp_path: Path) -> None:
    with pytest.raises(CodexLandingEvidenceAppendixError, match="evidence_index_json_missing"):
        build_landing_evidence_appendix(CodexLandingEvidenceAppendixRequest(TITLE, TITLE, evidence_index_json=str(tmp_path / "missing.json")))


def test_artifact_table_escapes_markdown_pipes_and_newlines_safely(tmp_path: Path) -> None:
    markdown, _metadata = _render(tmp_path, index=_index())
    assert "doctor\\|report" in markdown
    assert "line1<br>line2" in markdown
    assert "path\\|missing" in markdown


def test_non_authority_posture_section_is_present(tmp_path: Path) -> None:
    markdown, metadata = _render(tmp_path, doctor=_doctor())
    assert "## Non-authority posture" in markdown
    assert "**appendix_does_not_decide_readiness:** true" in markdown
    assert "**appendix_does_not_authorize_pr_creation:** true" in markdown
    assert metadata["non_authority_posture"]["appendix_does_not_rerun_commands"] is True  # type: ignore[index]


def test_renderer_does_not_decide_readiness_only_renders_evidence_status(tmp_path: Path) -> None:
    markdown, _metadata = _render(tmp_path, doctor=_doctor("doctor_ready"))
    assert "does not grant commit authority" in markdown
    assert "**overall_doctor_status:** doctor_ready" in markdown
    assert "ready_to_commit" in markdown
    assert "appendix_does_not_authorize_commit" in markdown


def test_markdown_output_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    first, _ = _render(tmp_path, index=_index(), doctor=_doctor())
    second, _ = _render(tmp_path, index=_index(), doctor=_doctor())
    assert first == second


def test_json_sidecar_output_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    _, first = _render(tmp_path, index=_index(), doctor=_doctor())
    _, second = _render(tmp_path, index=_index(), doctor=_doctor())
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
