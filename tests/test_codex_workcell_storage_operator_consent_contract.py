from __future__ import annotations

import hashlib

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_operator_consent_contract import (
    BLOCKING_GAP_IDS,
    INPUT_SPECS,
    NON_AUTHORITY_POSTURE,
    REQUIRED_EVIDENCE_IDS,
    SCHEMA_IDS,
    build_codex_workcell_storage_operator_consent_contract,
    omitted_input,
    read_json_input,
)


def _summaries():
    return {input_id: omitted_input(input_id) for input_id in INPUT_SPECS}


def test_contract_emits_required_flags_and_no_authority():
    report = build_codex_workcell_storage_operator_consent_contract(input_summaries=_summaries())
    assert report["storage_operator_consent_contract_id"] == "codex_workcell_storage_operator_consent_contract.v1"
    for key in ("metadata_only", "consent_contract_only", "consent_request_shape_only", "consent_not_collected", "runtime_binding_not_performed"):
        assert report[key] is True
    for key in ("operator_consent_present", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed"):
        assert report[key] is False
    assert all(report["non_authority_posture"][key] is True for key in NON_AUTHORITY_POSTURE)


def test_schema_evidence_scope_digest_lifetime_revocation_denial_and_boundary():
    report = build_codex_workcell_storage_operator_consent_contract(input_summaries=_summaries())
    schema = {row["schema_field_id"]: row for row in report["consent_request_schema"]}
    assert set(SCHEMA_IDS) <= set(schema)
    assert all(row["future_only"] is True and row["currently_satisfied"] is False and row["active"] is False for row in schema.values())
    evidence = report["required_consent_evidence"]
    assert evidence["required_evidence_ids"] == list(REQUIRED_EVIDENCE_IDS)
    assert evidence["evidence_collection_not_performed"] is True
    scope = report["consent_scope_policy"]
    assert scope["allowed_mounts"] == ["/ledger", "/glow"]
    assert set(scope["forbidden_mounts"]) >= {"/vow", "/pulse", "/daemon", "host_absolute_paths", "network_paths", "temp_paths_as_canonical", "hidden_backdoor_paths"}
    digest = report["consent_digest_binding_policy"]
    assert digest["canonical_vow_digest_required"] and digest["storage_policy_digest_required"] and digest["transaction_plan_digest_required"] and digest["execution_dossier_digest_required"] and digest["runtime_authority_digest_required"]
    assert digest["digest_algorithm"] == "sha256"
    lifetime = report["consent_lifetime_policy"]
    assert lifetime["expiration_required"] and lifetime["renewal_required_for_new_vow_digest"] and lifetime["renewal_required_for_changed_mount_scope"]
    revocation = report["consent_revocation_policy"]
    assert revocation["revocation_must_block_new_writes"] and revocation["revocation_must_block_new_archives"] and revocation["revocation_must_not_delete_existing_receipts"]
    assert report["consent_denial_policy"]["default_without_consent"] == "deny_active_storage"
    boundary = report["consent_authority_boundary"]
    assert boundary["consent_contract_is_not_consent"] and boundary["consent_schema_is_not_operator_approval"]
    assert boundary["supplied_reports_do_not_imply_consent"] and boundary["finalizer_ready_to_commit_does_not_imply_consent"]
    assert boundary["pr_metadata_guard_ready_does_not_imply_consent"] and boundary["daemon_recommendation_does_not_imply_consent"] and boundary["federation_state_does_not_imply_consent"]


def test_activation_gaps_hygiene_mounts_and_future_requirements():
    report = build_codex_workcell_storage_operator_consent_contract(input_summaries=_summaries())
    assert set(BLOCKING_GAP_IDS) <= set(report["consent_activation_gap_summary"]["blocking_gap_ids"])
    hygiene = report["reviewer_hygiene_summary"]
    assert hygiene["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    assert hygiene["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert report["sentientos_mount_alignment"]["/ledger"] == "future consent scope target; no ledger write here"
    assert report["sentientos_mount_alignment"]["/glow"] == "future consent scope target; no archive write here"
    assert all(item["status"] == "future_only" and item["met"] is False and item["active"] is False for item in report["future_activation_requirements"])


def test_input_summaries_record_digest_and_omissions(tmp_path):
    supplied = tmp_path / "policy.json"
    raw = b'{"ok": true}\n'
    supplied.write_bytes(raw)
    summaries = _summaries()
    summaries["storage_policy_contract_json"], _ = read_json_input(str(supplied), "storage_policy_contract_json")
    report = build_codex_workcell_storage_operator_consent_contract(input_summaries=summaries, commit_sha="abc", pr_number="5", pr_title="title")
    summary = report["input_summaries"]["storage_policy_contract_json"]
    assert summary["provided"] is True
    assert summary["digest"] == hashlib.sha256(raw).hexdigest()
    assert summary["byte_size"] == len(raw)
    assert report["input_summaries"]["storage_runtime_authority_contract_json"]["provided"] is False
    assert report["consent_context"]["supplied_report_count"] == 1
    assert report["consent_context"]["commit_sha"] == "abc"
    assert "storage_policy_contract_digest" in report["required_consent_evidence"]["supplied_evidence_ids"]
