from __future__ import annotations

import hashlib
import json
import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_execution_dossier import INPUT_SPECS, build_codex_workcell_storage_execution_dossier
from sentientos.codex_workcell_storage_execution_dossier_verifier import (
    OPTIONAL_INPUT_IDS,
    render_codex_workcell_storage_execution_dossier_verifier_markdown,
    verify_codex_workcell_storage_execution_dossier,
)


def source_report(report_id: str, status_key: str = "verification_status", status: str = "ok") -> dict[str, object]:
    return {report_id: report_id + ".v1", status_key: status, "non_authority_posture": {"read_only": True}}


def complete_dossier() -> dict[str, object]:
    summaries = {}
    reports = {}
    for input_id, _, _ in INPUT_SPECS:
        raw = json.dumps({"input_id": input_id}, sort_keys=True).encode()
        summaries[input_id] = {"input_id": input_id, "provided": True, "path": f"/{input_id}.json", "digest_algo": "sha256", "digest": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "readable_json": True, "error": None}
        reports[input_id] = {"non_authority_posture": {"x": True}, "digest": summaries[input_id]["digest"]}
    reports["storage_policy_verifier_json"]["verification_status"] = "storage_policy_verified"
    reports["storage_transaction_plan_verifier_json"]["verification_status"] = "storage_transaction_plan_verified"
    reports["memory_candidate_verifier_json"]["verification_status"] = "memory_candidate_verified"
    return build_codex_workcell_storage_execution_dossier(input_summaries=summaries, input_reports=reports)


def verify(dossier: dict[str, object]) -> dict[str, object]:
    raw = json.dumps(dossier, sort_keys=True).encode()
    summary = {"input_id": "storage_execution_dossier_json", "provided": True, "path": "/dossier.json", "digest_algo": "sha256", "digest": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "readable_json": True, "error": None}
    optional_summaries = {i: {"input_id": i, "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None} for i in OPTIONAL_INPUT_IDS}
    return verify_codex_workcell_storage_execution_dossier(storage_execution_dossier=dossier, storage_execution_dossier_summary=summary, optional_reports={}, optional_summaries=optional_summaries)


def check(report: dict[str, object], check_id: str) -> dict[str, object]:
    return next(c for c in report["verification_checks"] if c["check_id"] == check_id)  # type: ignore[index]


def test_valid_complete_dossier_verifies_and_shape() -> None:
    report = verify(complete_dossier())
    assert report["verification_status"] == "storage_execution_dossier_verified"
    assert report["metadata_only"] is True and report["verifier_only"] is True
    assert report["not_ledger_writer"] is True and report["not_glow_archiver"] is True
    assert report["dossier_summary"]["supplied_report_count"] == 10  # type: ignore[index]
    assert report["readiness_evidence_results"]["active_authority_detected"] is False  # type: ignore[index]
    assert report["active_execution_gap_results"]["active_storage_allowed_now_seen"] is False  # type: ignore[index]
    assert report["execution_prerequisite_results"]["no_prerequisite_grants_runtime_authority"] is True  # type: ignore[index]


def test_omitted_source_reports_are_represented() -> None:
    report = verify(complete_dossier())
    assert all(r["provided"] is False for r in report["optional_source_report_summary"])  # type: ignore[index]


def test_input_digest_and_byte_size_recorded() -> None:
    report = verify(complete_dossier())
    summary = report["input_summaries"]["storage_execution_dossier_json"]  # type: ignore[index]
    assert summary["digest"] and summary["byte_size"] > 0


def test_reviewer_hygiene_urls_present_without_runtime_effect() -> None:
    hygiene = verify(complete_dossier())["reviewer_hygiene_summary"]  # type: ignore[index]
    assert hygiene["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    assert hygiene["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert hygiene["no_runtime_effect"] is True


def test_future_activation_requirements_inactive() -> None:
    future = verify(complete_dossier())["future_activation_requirements"]  # type: ignore[index]
    assert all(r["status"] == "future_only" and r["met"] is False and r["active"] is False for r in future)


def test_non_authority_posture_flags_true_and_no_readiness_authority() -> None:
    report = verify(complete_dossier())
    assert all(report["non_authority_posture"].values())  # type: ignore[union-attr]
    assert report["non_authority_posture"]["storage_execution_dossier_verifier_does_not_decide_readiness"] is True  # type: ignore[index]
    assert report["non_authority_posture"]["storage_execution_dossier_verifier_does_not_authorize_commit"] is True  # type: ignore[index]


def test_missing_required_sections_fail() -> None:
    for key, check_id in (("evidence_inventory", "evidence_inventory_present"), ("readiness_evidence_summary", "readiness_evidence_summary_present"), ("active_execution_gap_summary", "active_execution_gap_summary_present"), ("execution_prerequisite_results", "execution_prerequisite_results_present")):
        dossier = complete_dossier(); dossier.pop(key)
        report = verify(dossier)
        assert report["verification_status"] == "storage_execution_dossier_failed"
        assert check(report, check_id)["passed"] is False


def test_boundary_flags_fail() -> None:
    cases = [("metadata_only", False, "dossier_declares_metadata_only"), ("dossier_only", False, "dossier_declares_dossier_only"), ("execution_not_performed", False, "dossier_declares_execution_not_performed"), ("writes_performed", True, "dossier_declares_no_writes_performed"), ("archives_performed", True, "dossier_declares_no_archives_performed"), ("memory_mutation_performed", True, "dossier_declares_no_memory_mutation")]
    for key, value, check_id in cases:
        dossier = complete_dossier(); dossier[key] = value
        report = verify(dossier)
        assert report["verification_status"] == "storage_execution_dossier_failed"
        assert check(report, check_id)["passed"] is False


def test_complete_status_without_required_reports_fails() -> None:
    dossier = complete_dossier(); dossier["dossier_context"]["supplied_report_count"] = 9  # type: ignore[index]
    report = verify(dossier)
    assert check(report, "complete_status_requires_required_reports")["passed"] is False


def test_failed_verifier_status_makes_dossier_fail() -> None:
    dossier = complete_dossier(); dossier["evidence_inventory"][0]["relevant_status"] = "storage_policy_failed"  # type: ignore[index]
    report = verify(dossier)
    assert check(report, "failed_verifier_status_makes_dossier_failed")["passed"] is False


def test_active_execution_gaps_must_remain_blocking() -> None:
    dossier = complete_dossier(); dossier["active_execution_gap_summary"]["blocking_gap_ids"] = []  # type: ignore[index]
    report = verify(dossier)
    assert check(report, "active_execution_gaps_remain_blocking")["passed"] is False
    assert report["active_execution_gap_results"]["required_blocking_gaps_present"] is False  # type: ignore[index]


def test_active_execution_flags_fail() -> None:
    for key, check_id in (("active_storage_allowed_now", "active_storage_allowed_now_false"), ("execution_performed", "execution_performed_false"), ("writes_performed", "writes_performed_false")):
        dossier = complete_dossier(); dossier["active_execution_gap_summary"][key] = True  # type: ignore[index]
        assert check(verify(dossier), check_id)["passed"] is False


def test_non_authority_posture_missing_or_false_fails() -> None:
    dossier = complete_dossier(); dossier["non_authority_posture"] = {"x": False}
    report = verify(dossier)
    assert check(report, "non_authority_posture_true")["passed"] is False


def test_markdown_is_deterministic_and_escapes() -> None:
    dossier = complete_dossier(); dossier["evidence_inventory"][0]["evidence_role"] = "a|b\nc"  # type: ignore[index]
    report = verify(dossier)
    one = render_codex_workcell_storage_execution_dossier_verifier_markdown(report)
    two = render_codex_workcell_storage_execution_dossier_verifier_markdown(report)
    assert one == two
    assert "a\\|b<br>c" in one
