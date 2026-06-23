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


def _doctrine() -> dict[str, object]:
    return {
        "doctrine_map_id": "doctrine.vtest",
        "metadata_only": True,
        "doctrine_only": True,
        "not_model_training": True,
        "not_reinforcement_learning": True,
        "trait_catalog": {
            "a_trait": "Alpha | line\nbreak.",
            "b_trait": "Beta definition.",
        },
        "rail_mappings": [
            {"rail_id": "z_rail", "rail_name": "Z rail | name", "enforced_traits": ["b_trait"], "reviewer_summary": "Z summary\nline."},
            {"rail_id": "a_rail", "rail_name": "A rail", "enforced_traits": ["a_trait", "b_trait"], "reviewer_summary": "A summary."},
        ],
        "trait_to_rails_index": {"b_trait": ["a_rail", "z_rail"], "a_trait": ["a_rail"]},
        "non_authority_posture": {
            "doctrine_map_does_not_decide_readiness": True,
            "doctrine_map_does_not_authorize_commit": True,
            "doctrine_map_does_not_authorize_pr_creation": True,
            "doctrine_map_does_not_train_or_modify_models": True,
        },
    }


def _render_with_doctrine(tmp_path: Path, doctrine: dict[str, object]) -> tuple[str, dict[str, object]]:
    doctrine_path = _write(tmp_path / "doctrine.json", doctrine)
    return build_landing_evidence_appendix(CodexLandingEvidenceAppendixRequest(TITLE, TITLE, output=str(tmp_path / "out.md"), doctrine_map_json=doctrine_path))


def test_appendix_renders_successfully_without_doctrine_map(tmp_path: Path) -> None:
    markdown, metadata = _render(tmp_path)
    assert "## Beneficial Trait Doctrine" in markdown
    assert "Beneficial trait doctrine map JSON was not provided" in markdown
    assert metadata["doctrine_map_json_path"] is None
    assert metadata["appendix_does_not_use_doctrine_as_authority"] is True


def test_appendix_renders_doctrine_section_when_map_is_supplied(tmp_path: Path) -> None:
    markdown, metadata = _render_with_doctrine(tmp_path, _doctrine())
    assert "### Doctrine posture" in markdown
    assert "### Trait catalog summary" in markdown
    assert "### Rail-to-trait summary" in markdown
    assert "### Trait-to-rails index" in markdown
    assert "doctrine map does not decide readiness" in markdown
    assert metadata["doctrine_map_id"] == "doctrine.vtest"


def test_invalid_doctrine_json_fails_cleanly(tmp_path: Path) -> None:
    bad = _write(tmp_path / "bad_doctrine.json", "{")
    with pytest.raises(CodexLandingEvidenceAppendixError, match="doctrine_map_json_invalid_json"):
        build_landing_evidence_appendix(CodexLandingEvidenceAppendixRequest(TITLE, TITLE, doctrine_map_json=bad))


def test_missing_provided_doctrine_json_path_fails_cleanly(tmp_path: Path) -> None:
    with pytest.raises(CodexLandingEvidenceAppendixError, match="doctrine_map_json_missing"):
        build_landing_evidence_appendix(CodexLandingEvidenceAppendixRequest(TITLE, TITLE, doctrine_map_json=str(tmp_path / "missing_doctrine.json")))


def test_doctrine_tables_are_deterministic_and_safely_escaped(tmp_path: Path) -> None:
    markdown, _metadata = _render_with_doctrine(tmp_path, _doctrine())
    assert "| a_trait | Alpha \\| line<br>break. |" in markdown
    assert markdown.index("| a_rail | A rail") < markdown.index("| z_rail | Z rail \\| name")
    assert "Z summary<br>line." in markdown
    assert markdown.index("| a_trait | a_rail |") < markdown.index("| b_trait | a_rail, z_rail |")


def test_doctrine_json_sidecar_fields_are_deterministic(tmp_path: Path) -> None:
    _markdown, first = _render_with_doctrine(tmp_path, _doctrine())
    _markdown, second = _render_with_doctrine(tmp_path, _doctrine())
    assert first["doctrine_trait_count"] == 2
    assert first["doctrine_rail_mapping_count"] == 2
    assert first["doctrine_traits_rendered"] == ["a_trait", "b_trait"]
    assert first["doctrine_rails_rendered"] == ["a_rail", "z_rail"]
    assert first["doctrine_non_authority_posture_seen"] is True
    assert first["appendix_renders_doctrine_as_review_context_only"] is True
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_appendix_output_does_not_include_doctrine_as_readiness_authority(tmp_path: Path) -> None:
    markdown, metadata = _render_with_doctrine(tmp_path, _doctrine())
    assert "does not use doctrine as readiness authority" not in markdown  # only absent from provided-map section
    assert "doctrine map does not decide readiness" in markdown
    assert metadata["appendix_does_not_use_doctrine_as_authority"] is True


def test_sidecar_includes_input_provenance_for_omitted_inputs(tmp_path: Path) -> None:
    _markdown, metadata = _render(tmp_path)
    provenance = metadata["input_provenance"]  # type: ignore[index]
    for key in ("evidence_index_json", "doctor_report_json", "doctrine_map_json"):
        item = provenance[key]
        assert item["provided"] is False
        assert item["path"] is None
        assert item["digest"] is None
        assert item["byte_size"] is None
        assert item["digest_algo"] == "sha256"


def test_sidecar_records_raw_byte_input_digests_for_all_inputs(tmp_path: Path) -> None:
    import hashlib

    index_text = '{"z":2, "a":1}\n'
    doctor_text = '{"doctor_report_id":"doctor", "overall_doctor_status":"ready_to_commit"}\n'
    doctrine_text = '{"doctrine_map_id":"d", "trait_catalog":{}, "rail_mappings":[]}\n'
    index_path = tmp_path / "index_raw.json"
    doctor_path = tmp_path / "doctor_raw.json"
    doctrine_path = tmp_path / "doctrine_raw.json"
    index_path.write_text(index_text, encoding="utf-8")
    doctor_path.write_text(doctor_text, encoding="utf-8")
    doctrine_path.write_text(doctrine_text, encoding="utf-8")

    _markdown, metadata = build_landing_evidence_appendix(
        CodexLandingEvidenceAppendixRequest(
            TITLE,
            TITLE,
            output=str(tmp_path / "out.md"),
            evidence_index_json=str(index_path),
            doctor_report_json=str(doctor_path),
            doctrine_map_json=str(doctrine_path),
        )
    )
    provenance = metadata["input_provenance"]  # type: ignore[index]
    for key, path, text in (
        ("evidence_index_json", index_path, index_text),
        ("doctor_report_json", doctor_path, doctor_text),
        ("doctrine_map_json", doctrine_path, doctrine_text),
    ):
        item = provenance[key]
        raw = text.encode("utf-8")
        assert item["provided"] is True
        assert item["path"] == str(path)
        assert item["exists"] is True
        assert item["readable_json"] is True
        assert item["digest_algo"] == "sha256"
        assert item["digest"] == hashlib.sha256(raw).hexdigest()
        assert item["byte_size"] == len(raw)
        assert item["digest"] != hashlib.sha256(json.dumps(json.loads(text), sort_keys=True).encode("utf-8")).hexdigest()


def test_sidecar_records_rendered_markdown_digest_and_avoids_self_reference(tmp_path: Path) -> None:
    import hashlib

    markdown, metadata = _render(tmp_path, index=_index(), doctor=_doctor())
    output = metadata["output_provenance"]  # type: ignore[index]
    raw = markdown.encode("utf-8")
    assert output["markdown_digest_algo"] == "sha256"
    assert output["markdown_digest"] == hashlib.sha256(raw).hexdigest()
    assert output["markdown_byte_size"] == len(raw)
    assert output["json_sidecar_digest"] is None
    assert "avoid embedding" in output["json_sidecar_self_digest_note"]


def test_provenance_flags_are_non_authoritative_and_do_not_add_readiness_decisions(tmp_path: Path) -> None:
    _markdown, metadata = _render(tmp_path, index=_index(), doctor=_doctor())
    for key in (
        "appendix_provenance_is_metadata_only",
        "appendix_provenance_is_read_only",
        "appendix_provenance_does_not_verify_authority",
        "appendix_provenance_does_not_decide_readiness",
        "appendix_provenance_does_not_authorize_commit",
        "appendix_provenance_does_not_authorize_pr_creation",
    ):
        assert metadata[key] is True
    provenance_json = json.dumps({"input_provenance": metadata["input_provenance"], "output_provenance": metadata["output_provenance"]}, sort_keys=True)
    assert "ready_to_commit" not in provenance_json
    assert "pr_metadata_guard_ready" not in provenance_json
