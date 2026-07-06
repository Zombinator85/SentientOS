from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_operator_consent_request_presentation_contract import INPUT_SPECS, build_codex_workcell_storage_operator_consent_request_presentation_contract, omitted_input as omitted_contract_input
from sentientos.codex_workcell_storage_operator_consent_request_presentation_verifier import OPTIONAL_INPUT_IDS, omitted_input, read_json_input, render_codex_workcell_storage_operator_consent_request_presentation_verifier_markdown, verify_codex_workcell_storage_operator_consent_request_presentation_contract

REQUIRED_TOP_LEVEL = """storage_operator_consent_request_presentation_verifier_id metadata_only verifier_only presentation_not_performed request_not_presented ui_not_rendered message_not_sent external_delivery_not_performed response_artifact_not_created response_not_collected consent_not_collected consent_not_implied operator_consent_present runtime_binding_not_performed active_storage_allowed_now execution_performed writes_performed archives_performed memory_mutation_performed not_presentation_runner not_ui_renderer not_message_sender not_external_delivery_system not_response_artifact_creator not_response_collector not_consent_collector not_runtime_authority not_memory_writer not_ledger_writer not_glow_archiver not_watcher not_scheduler not_executor not_daemon_action not_task_creator not_alerting_system not_model_training not_reinforcement_learning input_summaries presentation_contract_summary optional_context_summary verification_status verification_checks presentation_surface_results presentation_authority_requirement_results operator_attention_requirement_results delivery_scope_requirement_results request_packet_integrity_requirement_results response_path_requirement_results denied_inference_results missing_real_world_presentation_results reviewer_hygiene_summary violation_summary sentientos_mount_alignment future_activation_requirements non_authority_posture""".split()
REQUIRED_CHECKS = """presentation_contract_is_object presentation_contract_id_matches presentation_contract_declares_metadata_only presentation_contract_declares_contract_only presentation_contract_declares_future_only presentation_not_performed_true request_not_presented_true ui_not_rendered_true message_not_sent_true external_delivery_not_performed_true response_artifact_not_created_true response_not_collected_true consent_not_collected_true consent_not_implied_true operator_consent_present_false runtime_binding_not_performed_true active_storage_allowed_now_false execution_performed_false writes_performed_false archives_performed_false memory_mutation_performed_false presentation_boundary_context_present presentation_authority_separated_from_packet_and_evidence presentation_surface_inventory_present presentation_surface_inventory_complete presentation_surfaces_future_only_and_inactive presentation_authority_requirements_present presentation_authority_requirements_unsatisfied operator_attention_requirements_present operator_attention_requirements_unsatisfied delivery_scope_requirements_present delivery_scope_requirements_unsatisfied request_packet_integrity_requirements_present request_packet_integrity_requirements_unsatisfied response_path_requirements_present response_path_requirements_unsatisfied denied_inferences_present denied_inferences_all_denied missing_real_world_presentation_summary_present required_presentation_gap_ids_present future_activation_requirements_inactive reviewer_hygiene_bad_openai_repo_url_absent non_authority_posture_present non_authority_posture_true""".split()
RESULT_SECTIONS = """presentation_surface_results presentation_authority_requirement_results operator_attention_requirement_results delivery_scope_requirement_results request_packet_integrity_requirement_results response_path_requirement_results denied_inference_results missing_real_world_presentation_results""".split()

def _contract() -> dict[str, object]:
    return build_codex_workcell_storage_operator_consent_request_presentation_contract(input_summaries={k: omitted_contract_input(k) for k in INPUT_SPECS}, commit="abc", pr="9")

def _summary() -> dict[str, object]:
    return {"input_id": "presentation_contract_json", "provided": True, "path": "contract.json", "digest_algo": "sha256", "digest": "abc", "byte_size": 10, "readable_json": True, "error": None}

def _report(contract: dict[str, object] | None = None, optional_reports: dict[str, dict[str, object]] | None = None) -> dict[str, object]:
    return verify_codex_workcell_storage_operator_consent_request_presentation_contract(contract=contract or _contract(), contract_summary=_summary(), optional_reports=optional_reports or {}, optional_summaries={k: omitted_input(k) for k in OPTIONAL_INPUT_IDS})

def test_verifier_output_contract_is_hardened_and_non_authoritative():
    report = _report()
    assert report["verification_status"] == "storage_operator_consent_request_presentation_contract_verified"
    assert set(REQUIRED_TOP_LEVEL) <= set(report)
    assert report["missing_real_world_presentation_results"] is report["missing_presentation_gap_results"]
    assert {c["check_id"] for c in report["verification_checks"]} >= set(REQUIRED_CHECKS)
    assert all({"check_id", "passed", "severity", "details", "authority_boundary"} <= set(c) for c in report["verification_checks"])
    assert set(RESULT_SECTIONS) <= set(report)
    for key in ("metadata_only", "verifier_only", "presentation_not_performed", "request_not_presented", "ui_not_rendered", "message_not_sent", "external_delivery_not_performed", "response_artifact_not_created", "response_not_collected", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed", "not_runtime_authority", "not_ledger_writer", "not_glow_archiver", "not_daemon_action", "not_scheduler"):
        assert report[key] is True
    for key in ("operator_consent_present", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed"):
        assert report[key] is False

def test_summary_optional_context_violation_and_result_shapes():
    report = _report(optional_reports={"storage_operator_consent_request_packet_json": {"storage_operator_consent_request_packet_id": "packet.v1"}})
    pcs = report["presentation_contract_summary"]
    assert pcs["storage_operator_consent_request_presentation_contract_id"]
    assert pcs["source_digest"] == "abc" and pcs["source_digest_algo"] == "sha256" and pcs["source_byte_size"] == 10
    optional = report["optional_context_summary"]
    assert all({"input_id", "provided", "detected_report_id", "source_digest", "source_digest_algo", "source_byte_size", "relevant_status_or_digest", "context_only"} <= set(row) for row in optional)
    assert any(row["detected_report_id"] == "packet.v1" for row in optional)
    vs = report["violation_summary"]
    assert {"violation_count", "warning_count", "info_count", "violation_check_ids", "warning_check_ids", "verifier_only", "no_action_taken"} <= set(vs)
    assert vs["violation_count"] == 0 and vs["warning_count"] == 0 and vs["verifier_only"] is True and vs["no_action_taken"] is True
    assert report["denied_inference_results"]["all_denied"] is True
    assert report["missing_real_world_presentation_results"]["request_presented_is_false"] is True

def test_failed_and_incomplete_statuses_are_deterministic():
    failed = _contract(); failed["message_not_sent"] = False
    report = _report(failed)
    assert report["verification_status"] == "storage_operator_consent_request_presentation_contract_failed"
    assert "message_not_sent_true" in report["violation_summary"]["violation_check_ids"]
    incomplete = _contract(); incomplete["denied_inferences"] = {}
    incomplete_report = _report(incomplete)
    assert incomplete_report["verification_status"] == "storage_operator_consent_request_presentation_contract_incomplete"

def test_read_json_and_markdown_are_deterministic_and_escaped(tmp_path: Path):
    path = tmp_path / "contract.json"
    raw = json.dumps(_contract(), sort_keys=True).encode()
    path.write_bytes(raw)
    summary, loaded = read_json_input(str(path), "presentation_contract_json")
    assert loaded["metadata_only"] is True
    assert summary["digest"] == hashlib.sha256(raw).hexdigest()
    report = _report(); report["reviewer_hygiene_summary"]["pipe\nkey"] = "a|b\nc"
    md1 = render_codex_workcell_storage_operator_consent_request_presentation_verifier_markdown(report)
    md2 = render_codex_workcell_storage_operator_consent_request_presentation_verifier_markdown(report)
    assert md1 == md2
    for section in ("Presentation contract summary", "Optional context summary", "Presentation surface results", "Denied inference results", "Missing real-world presentation results", "SentientOS mount alignment", "Future activation requirements", "Non-authority posture"):
        assert section in md1
    assert "a\\|b<br>c" in md1 or "pipe<br>key" in md1
    bad = tmp_path / "bad.json"; bad.write_text("[]")
    with pytest.raises(ValueError):
        read_json_input(str(bad), "presentation_contract_json")
