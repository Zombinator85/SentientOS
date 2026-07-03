from __future__ import annotations

import copy
import hashlib
import json
import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_operator_consent_evidence_dossier_verifier import (
    ALL_INPUT_IDS,
    BLOCKING_GAP_IDS,
    NON_AUTHORITY_POSTURE,
    REQUIRED_DOSSIER_INPUT_ID,
    REQUIRED_PREREQUISITE_IDS,
    SUPPORTED_EVIDENCE_ROLES,
    omitted_input,
    verify_codex_workcell_storage_operator_consent_evidence_dossier,
)


def dossier() -> dict[str, object]:
    inv=[]
    for role in SUPPORTED_EVIDENCE_ROLES:
        inv.append({"input_id": f"{role}_json", "provided": True, "evidence_role": role, "source_digest": "a"*64, "source_byte_size": 2, "inventory_status": "supplied", "relevant_status_or_digest": {
            "consent_response_verifier":"storage_operator_consent_response_contract_verified",
            "consent_request_packet_verifier":"storage_operator_consent_request_packet_verified",
            "consent_request_verifier":"storage_operator_consent_contract_verified",
            "runtime_authority_verifier":"storage_runtime_authority_contract_verified",
            "execution_dossier_verifier":"storage_execution_dossier_verified",
            "transaction_plan_verifier":"storage_transaction_plan_verified",
            "storage_policy_verifier":"storage_policy_contract_verified",
        }.get(role, "digest")})
    design={k: True for k in ["consent_request_contract_supplied","consent_request_verifier_supplied","consent_request_packet_supplied","consent_request_packet_verifier_supplied","consent_response_contract_supplied","consent_response_verifier_supplied","runtime_authority_contract_supplied","runtime_authority_verifier_supplied","execution_dossier_supplied","execution_dossier_verifier_supplied","transaction_plan_supplied","transaction_plan_verifier_supplied","storage_policy_contract_supplied","storage_policy_verifier_supplied","vow_boundary_contract_supplied","vow_alignment_attestation_supplied","all_required_design_reports_supplied","all_supplied_verifiers_passed","all_supplied_reports_non_authoritative","future_consent_design_evidence_complete","no_action_taken"]}
    design.update({"response_artifact_created_detected":False,"operator_response_detected":False,"consent_collected_detected":False,"consent_implied_detected":False,"runtime_binding_detected":False,"active_storage_authority_detected":False})
    missing={k: False for k in ["consent_request_presentation_mechanism_present","consent_request_presented","ui_rendered","message_sent","external_delivery_performed","response_artifact_created","operator_response_present","operator_identity_present","operator_timestamp_present","operator_scope_statement_present","response_status_present","explicit_ledger_write_allow_present","explicit_glow_archive_allow_present","digest_acknowledgements_present","expiration_timestamp_present","revocation_terms_acknowledged","response_signature_present","runtime_authority_binding_present","active_storage_allowed_now","execution_performed","writes_performed","archives_performed","memory_mutation_performed"]}
    missing["blocking_gap_ids"] = list(BLOCKING_GAP_IDS)
    return {"storage_operator_consent_evidence_dossier_id":"codex_workcell_storage_operator_consent_evidence_dossier.v1","metadata_only":True,"evidence_dossier_only":True,"consent_design_evidence_only":True,"response_artifact_not_created":True,"operator_response_present":False,"consent_request_not_presented":True,"consent_not_collected":True,"consent_not_implied":True,"operator_consent_present":False,"runtime_binding_not_performed":True,"active_storage_allowed_now":False,"execution_performed":False,"writes_performed":False,"archives_performed":False,"memory_mutation_performed":False,"consent_evidence_status":"storage_operator_consent_evidence_dossier_complete","consent_ladder_inventory":inv,"consent_design_evidence_summary":design,"missing_real_world_consent_summary":missing,"consent_prerequisite_results":[{"prerequisite_id":x,"category":"c","passed":True,"severity":"info","observed_state":"s","evidence_source":"e","authority_boundary":"b"} for x in REQUIRED_PREREQUISITE_IDS],"non_authority_posture": {"x": True}}


def summaries(d: dict[str, object]) -> dict[str, dict[str, object]]:
    raw=json.dumps(d, sort_keys=True).encode()
    s={k: omitted_input(k) for k in ALL_INPUT_IDS}
    s[REQUIRED_DOSSIER_INPUT_ID]={"input_id":REQUIRED_DOSSIER_INPUT_ID,"provided":True,"path":"d.json","digest_algo":"sha256","digest":hashlib.sha256(raw).hexdigest(),"byte_size":len(raw),"readable_json":True,"error":None}
    return s

def verify(d):
    return verify_codex_workcell_storage_operator_consent_evidence_dossier(evidence_dossier=d, input_summaries=summaries(d))


def test_valid_complete_consent_evidence_dossier_verifies_while_gaps_remain():
    r=verify(dossier())
    assert r["verification_status"] == "storage_operator_consent_evidence_dossier_verified"
    assert r["operator_consent_present"] is False
    assert r["missing_real_world_consent_results"]["required_blocking_gap_ids_present"] is True
    assert r["active_storage_allowed_now"] is False


def test_required_top_level_authority_boundaries_fail_when_inverted():
    cases=[("metadata_only", None),("evidence_dossier_only", False),("consent_design_evidence_only", False),("response_artifact_not_created", False),("operator_response_present", True),("consent_request_not_presented", False),("consent_not_collected", False),("consent_not_implied", False),("operator_consent_present", True),("runtime_binding_not_performed", False),("active_storage_allowed_now", True),("execution_performed", True),("writes_performed", True),("archives_performed", True),("memory_mutation_performed", True)]
    for key,value in cases:
        d=dossier();
        if value is None: d.pop(key)
        else: d[key]=value
        assert verify(d)["verification_status"] == "storage_operator_consent_evidence_dossier_failed"


def test_inventory_and_status_failures_are_detected_and_incomplete_allowed():
    d=dossier(); d.pop("consent_ladder_inventory")
    assert verify(d)["verification_status"] == "storage_operator_consent_evidence_dossier_failed"
    d=dossier(); d["consent_ladder_inventory"]=d["consent_ladder_inventory"][:-1]
    assert verify(d)["consent_ladder_inventory_results"]["supported_evidence_roles_present"] is False
    d=dossier(); d["consent_ladder_inventory"][0].pop("source_digest")
    assert verify(d)["consent_ladder_inventory_results"]["supplied_records_have_digest_and_byte_size"] is False
    d=dossier(); d["consent_ladder_inventory"][0]["provided"]=False; d["consent_ladder_inventory"][0]["inventory_status"]="omitted"
    assert verify(d)["consent_ladder_inventory_results"]["omitted_records_have_missing_status"] is False
    d=dossier(); d["consent_ladder_inventory"][1]["relevant_status_or_digest"]="failed"
    assert verify(d)["consent_ladder_inventory_results"]["failed_verifier_status_ids"]
    d=dossier(); d["consent_design_evidence_summary"]["active_storage_authority_detected"]=True
    assert verify(d)["verification_status"] == "storage_operator_consent_evidence_dossier_failed"
    d=dossier(); d["consent_evidence_status"]="storage_operator_consent_evidence_dossier_complete"; d["consent_design_evidence_summary"]["all_required_design_reports_supplied"]=False
    assert verify(d)["verification_status"] == "storage_operator_consent_evidence_dossier_failed"
    d=dossier(); d["consent_design_evidence_summary"]["all_supplied_verifiers_passed"]=False
    assert verify(d)["verification_status"] == "storage_operator_consent_evidence_dossier_failed"
    d=dossier(); d["consent_evidence_status"]="storage_operator_consent_evidence_dossier_incomplete"; d["consent_design_evidence_summary"]["future_consent_design_evidence_complete"]=False
    assert verify(d)["verification_status"] == "storage_operator_consent_evidence_dossier_incomplete"


def test_missing_real_world_consent_prerequisites_posture_future_and_input_summaries():
    d=dossier(); d.pop("missing_real_world_consent_summary")
    assert verify(d)["verification_status"] == "storage_operator_consent_evidence_dossier_failed"
    d=dossier(); d["missing_real_world_consent_summary"]["operator_response_present"]=True
    assert verify(d)["missing_real_world_consent_results"]["operator_response_present_is_false"] is False
    d=dossier(); d["missing_real_world_consent_summary"]["blocking_gap_ids"]=[]
    assert verify(d)["missing_real_world_consent_results"]["required_blocking_gap_ids_present"] is False
    d=dossier(); d["consent_prerequisite_results"]=[]
    assert verify(d)["consent_prerequisite_results"]["required_prerequisite_ids_present"] is False
    d=dossier(); d["non_authority_posture"]={"x":False}
    assert verify(d)["violation_summary"]["violation_count"] > 0
    r=verify(dossier())
    assert all(x["status"]=="future_only" and x["active"] is False and x["met"] is False for x in r["future_activation_requirements"])
    assert all(r["non_authority_posture"].values()) and r["non_authority_posture"] == NON_AUTHORITY_POSTURE
    assert r["input_summaries"][REQUIRED_DOSSIER_INPUT_ID]["digest"] == summaries(dossier())[REQUIRED_DOSSIER_INPUT_ID]["digest"]
    assert r["input_summaries"]["storage_policy_verifier_json"]["provided"] is False
    assert "Zombinator85" in r["reviewer_hygiene_summary"]["correct_repo_url"]
    assert "OpenAI" in r["reviewer_hygiene_summary"]["bad_repo_url"]


def test_verifier_never_grants_runtime_or_delivery_authority():
    r=verify(dossier())
    for key in ["consent_request_not_presented","response_artifact_not_created","consent_not_collected","consent_not_implied","runtime_binding_not_performed","not_ledger_writer","not_glow_archiver","not_daemon_action","not_task_creator","not_scheduler"]:
        assert r[key] is True
    for key in ["operator_response_present","operator_consent_present","active_storage_allowed_now","execution_performed","writes_performed","archives_performed","memory_mutation_performed"]:
        assert r[key] is False
