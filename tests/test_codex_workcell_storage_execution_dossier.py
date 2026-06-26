from __future__ import annotations

import hashlib
import json
import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_execution_dossier import INPUT_SPECS, build_codex_workcell_storage_execution_dossier, omitted_input, render_codex_workcell_storage_execution_dossier_markdown


def _summaries_and_reports(all_inputs=True, policy_status="storage_policy_verified", plan_status="storage_transaction_plan_verified"):
    summaries={}; reports={}
    for input_id, _, _ in INPUT_SPECS:
        if all_inputs:
            raw=json.dumps({"x": input_id}, sort_keys=True).encode()
            summaries[input_id]={"input_id":input_id,"provided":True,"path":f"/{input_id}.json","digest_algo":"sha256","digest":hashlib.sha256(raw).hexdigest(),"byte_size":len(raw),"readable_json":True,"error":None}
            reports[input_id]={"non_authority_posture":{"a":True}}
        else:
            summaries[input_id]=omitted_input(input_id)
    if all_inputs:
        reports["storage_policy_verifier_json"].update({"storage_policy_verifier_id":"codex_workcell_storage_policy_verifier.v1","verification_status":policy_status})
        reports["storage_transaction_plan_verifier_json"].update({"storage_transaction_plan_verifier_id":"codex_workcell_storage_transaction_plan_verifier.v1","verification_status":plan_status})
        reports["memory_candidate_verifier_json"].update({"memory_candidate_verification_status":"memory_candidate_verified"})
        reports["vow_alignment_attestation_json"].update({"failed_attestation_count":0,"warning_attestation_count":1})
    return summaries,reports


def test_omitted_inputs_incomplete_and_no_authority():
    s,r=_summaries_and_reports(False)
    d=build_codex_workcell_storage_execution_dossier(input_summaries=s,input_reports=r)
    assert d["storage_execution_status"]=="future_storage_design_dossier_incomplete"
    gap=d["active_execution_gap_summary"]
    assert gap["active_storage_allowed_now"] is False
    assert gap["execution_performed"] is False
    assert gap["writes_performed"] is False
    assert gap["archives_performed"] is False
    assert gap["memory_mutation_performed"] is False
    assert "active_writer_implementation_missing" in gap["blocking_gap_ids"]


def test_all_required_reports_complete_while_active_gaps_remain():
    s,r=_summaries_and_reports(True)
    d=build_codex_workcell_storage_execution_dossier(input_summaries=s,input_reports=r,commit_sha="abc",pr_number="1",pr_title="t")
    assert d["storage_execution_status"]=="future_storage_design_dossier_complete"
    assert d["dossier_context"]["supplied_report_count"]==len(INPUT_SPECS)
    assert d["readiness_evidence_summary"]["dossier_ready_for_future_design_review"] is True
    assert d["active_execution_gap_summary"]["blocking_gap_ids"]
    assert d["active_execution_gap_summary"]["active_storage_allowed_now"] is False
    assert all(v is True for v in d["non_authority_posture"].values())
    assert all(x["active"] is False and x["met"] is False for x in d["future_activation_requirements"])


def test_failed_verifier_statuses_fail_dossier():
    s,r=_summaries_and_reports(True, policy_status="storage_policy_failed")
    assert build_codex_workcell_storage_execution_dossier(input_summaries=s,input_reports=r)["storage_execution_status"]=="future_storage_design_dossier_failed"
    s,r=_summaries_and_reports(True, plan_status="storage_transaction_plan_failed")
    assert build_codex_workcell_storage_execution_dossier(input_summaries=s,input_reports=r)["storage_execution_status"]=="future_storage_design_dossier_failed"


def test_inventory_digest_hygiene_and_prerequisites():
    s,r=_summaries_and_reports(True)
    d=build_codex_workcell_storage_execution_dossier(input_summaries=s,input_reports=r)
    inv=d["evidence_inventory"][0]
    assert inv["source_digest"]==s[inv["input_id"]]["digest"]
    assert inv["source_byte_size"]==s[inv["input_id"]]["byte_size"]
    assert d["reviewer_hygiene_summary"]["bad_repo_url"]=="https://github.com/" + "OpenAI/" + "SentientOS.git"
    assert d["reviewer_hygiene_summary"]["correct_repo_url"]=="https://github.com/Zombinator85/SentientOS.git"
    assert any(x["severity"]=="blocking_gap" for x in d["execution_prerequisite_results"])


def test_markdown_deterministic_and_escaping():
    s,r=_summaries_and_reports(True)
    s["memory_contract_json"]["path"]="a|b\nc"
    d=build_codex_workcell_storage_execution_dossier(input_summaries=s,input_reports=r)
    assert render_codex_workcell_storage_execution_dossier_markdown(d)==render_codex_workcell_storage_execution_dossier_markdown(d)
    md=render_codex_workcell_storage_execution_dossier_markdown(d)
    assert "a\\|b<br>c" in md
    assert "Codex Workcell Storage Execution Readiness Dossier" in md
