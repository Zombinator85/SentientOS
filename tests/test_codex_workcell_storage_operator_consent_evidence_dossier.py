from __future__ import annotations

import hashlib

import pytest

from sentientos.codex_workcell_storage_operator_consent_evidence_dossier import (
    BLOCKING_GAP_IDS,
    INPUT_SPECS,
    NON_AUTHORITY_POSTURE,
    WORKCELL_STORAGE_OPERATOR_CONSENT_EVIDENCE_DOSSIER_ID,
    build_codex_workcell_storage_operator_consent_evidence_dossier,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_evidence_dossier_markdown,
)

pytestmark = pytest.mark.no_legacy_skip

EXPECTED = {
    "storage_operator_consent_response_verifier_json": "storage_operator_consent_response_contract_verified",
    "storage_operator_consent_request_packet_verifier_json": "storage_operator_consent_request_packet_verified",
    "storage_operator_consent_verifier_json": "storage_operator_consent_contract_verified",
    "storage_runtime_authority_verifier_json": "storage_runtime_authority_contract_verified",
    "storage_execution_dossier_verifier_json": "storage_execution_dossier_verified",
    "storage_transaction_plan_verifier_json": "storage_transaction_plan_verified",
    "storage_policy_verifier_json": "storage_policy_contract_verified",
}


def _summaries_reports(tmp_path, overrides=None):
    summaries = {}
    reports = {}
    overrides = overrides or {}
    for input_id in INPUT_SPECS:
        report = {"report_id": input_id, "metadata_only": True, "non_authority_posture": {"x": True}}
        if input_id in EXPECTED:
            report["verification_status"] = EXPECTED[input_id]
        report.update(overrides.get(input_id, {}))
        path = tmp_path / f"{input_id}.json"
        import json
        path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        summaries[input_id], reports[input_id] = read_json_input(str(path), input_id)
    return summaries, reports


def test_required_flags_and_omitted_inputs_incomplete() -> None:
    dossier = build_codex_workcell_storage_operator_consent_evidence_dossier(input_summaries={k: omitted_input(k) for k in INPUT_SPECS})
    assert dossier["storage_operator_consent_evidence_dossier_id"] == WORKCELL_STORAGE_OPERATOR_CONSENT_EVIDENCE_DOSSIER_ID
    for key in ["metadata_only", "evidence_dossier_only", "consent_design_evidence_only", "response_artifact_not_created", "consent_request_not_presented", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed"]:
        assert dossier[key] is True
    for key in ["operator_response_present", "operator_consent_present", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed"]:
        assert dossier[key] is False
    assert dossier["consent_evidence_status"] == "storage_operator_consent_evidence_dossier_incomplete"
    assert all(v is True for v in dossier["non_authority_posture"].values())
    assert dossier["non_authority_posture"] == NON_AUTHORITY_POSTURE
    assert all(r["inventory_status"] == "missing" and r["provided"] is False for r in dossier["consent_ladder_inventory"])


def test_all_required_reports_can_complete_while_real_world_gaps_remain(tmp_path) -> None:
    summaries, reports = _summaries_reports(tmp_path)
    dossier = build_codex_workcell_storage_operator_consent_evidence_dossier(input_summaries=summaries, input_reports=reports, commit_sha="abc", pr_number="7", pr_title="title")
    assert dossier["consent_evidence_status"] == "storage_operator_consent_evidence_dossier_complete"
    assert dossier["evidence_dossier_context"]["commit_sha"] == "abc"
    summary = dossier["consent_design_evidence_summary"]
    assert summary["all_required_design_reports_supplied"] is True
    assert summary["all_supplied_verifiers_passed"] is True
    assert summary["future_consent_design_evidence_complete"] is True
    assert summary["response_artifact_created_detected"] is False
    assert summary["operator_response_detected"] is False
    missing = dossier["missing_real_world_consent_summary"]
    assert missing["operator_response_present"] is False
    assert all(gap in missing["blocking_gap_ids"] for gap in BLOCKING_GAP_IDS)
    assert all(r["status"] == "future_only" and r["met"] is False and r["active"] is False for r in dossier["future_activation_requirements"])
    assert any(r["prerequisite_id"] == "active_storage_disallowed" and r["passed"] is True for r in dossier["consent_prerequisite_results"])


@pytest.mark.parametrize("input_id", [
    "storage_operator_consent_response_verifier_json",
    "storage_operator_consent_request_packet_verifier_json",
    "storage_operator_consent_verifier_json",
    "storage_runtime_authority_verifier_json",
])
def test_failed_verifier_status_fails_dossier(tmp_path, input_id) -> None:
    summaries, reports = _summaries_reports(tmp_path, {input_id: {"verification_status": "failed"}})
    dossier = build_codex_workcell_storage_operator_consent_evidence_dossier(input_summaries=summaries, input_reports=reports)
    assert dossier["consent_evidence_status"] == "storage_operator_consent_evidence_dossier_failed"
    row = next(r for r in dossier["consent_ladder_inventory"] if r["input_id"] == input_id)
    assert row["inventory_status"] == "failed"


def test_active_authority_signal_fails_but_output_never_grants_authority(tmp_path) -> None:
    summaries, reports = _summaries_reports(tmp_path, {"storage_policy_contract_json": {"active_storage_allowed_now": True}})
    dossier = build_codex_workcell_storage_operator_consent_evidence_dossier(input_summaries=summaries, input_reports=reports)
    assert dossier["consent_evidence_status"] == "storage_operator_consent_evidence_dossier_failed"
    assert dossier["active_storage_allowed_now"] is False
    assert dossier["operator_consent_present"] is False
    assert dossier["operator_response_present"] is False
    assert dossier["response_artifact_not_created"] is True


def test_digest_byte_size_summary_hygiene_and_markdown_escape(tmp_path) -> None:
    payload = b'{"note":"a|b\\nc"}'
    path = tmp_path / "one.json"
    path.write_bytes(payload)
    summary, report = read_json_input(str(path), "storage_policy_contract_json")
    dossier = build_codex_workcell_storage_operator_consent_evidence_dossier(input_summaries={"storage_policy_contract_json": summary}, input_reports={"storage_policy_contract_json": report}, pr_title="a|b\nc")
    inv = next(r for r in dossier["consent_ladder_inventory"] if r["input_id"] == "storage_policy_contract_json")
    assert inv["source_digest"] == hashlib.sha256(payload).hexdigest()
    assert inv["source_byte_size"] == len(payload)
    assert dossier["input_summaries"]["storage_operator_consent_response_contract_json"]["provided"] is False
    assert dossier["reviewer_hygiene_summary"]["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert dossier["reviewer_hygiene_summary"]["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    md1 = render_codex_workcell_storage_operator_consent_evidence_dossier_markdown(dossier)
    md2 = render_codex_workcell_storage_operator_consent_evidence_dossier_markdown(dossier)
    assert md1 == md2
    assert "a\\|b" in md1 and "<br>" in md1


def test_no_readiness_or_runtime_actions_are_granted() -> None:
    dossier = build_codex_workcell_storage_operator_consent_evidence_dossier(input_summaries={})
    posture = dossier["non_authority_posture"]
    for suffix in ["does_not_decide_readiness", "does_not_present_request", "does_not_render_ui", "does_not_send_messages", "does_not_create_response_artifact", "does_not_collect_response", "does_not_collect_consent", "does_not_imply_consent", "does_not_bind_runtime_authority", "does_not_write_ledger", "does_not_archive_glow", "does_not_modify_memory", "does_not_trigger_daemon", "does_not_create_tasks", "does_not_schedule_tasks"]:
        assert posture[f"storage_operator_consent_evidence_dossier_{suffix}"] is True
