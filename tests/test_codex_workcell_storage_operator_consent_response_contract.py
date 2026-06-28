from __future__ import annotations

import hashlib

import pytest

from sentientos.codex_workcell_storage_operator_consent_response_contract import (
    BLOCKING_GAP_IDS,
    FORBIDDEN_MOUNTS,
    INPUT_SPECS,
    REQUIRED_ACKNOWLEDGEMENT_IDS,
    SCHEMA_FIELD_IDS,
    WORKCELL_STORAGE_OPERATOR_CONSENT_RESPONSE_CONTRACT_ID,
    build_codex_workcell_storage_operator_consent_response_contract,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_response_contract_markdown,
)

pytestmark = pytest.mark.no_legacy_skip


def _contract():
    return build_codex_workcell_storage_operator_consent_response_contract(
        input_summaries={k: omitted_input(k) for k in INPUT_SPECS}, commit_sha="abc", pr_number="1", pr_title="title"
    )


def test_contract_required_flags_and_non_authority() -> None:
    c = _contract()
    assert c["storage_operator_consent_response_contract_id"] == WORKCELL_STORAGE_OPERATOR_CONSENT_RESPONSE_CONTRACT_ID
    for key in ["metadata_only", "response_contract_only", "response_artifact_schema_only", "response_artifact_not_created", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed"]:
        assert c[key] is True
    for key in ["operator_response_present", "operator_consent_present", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed"]:
        assert c[key] is False
    assert all(v is True for v in c["non_authority_posture"].values())
    for required in ["storage_operator_consent_response_contract_does_not_render_ui", "storage_operator_consent_response_contract_does_not_send_messages", "storage_operator_consent_response_contract_does_not_write_ledger", "storage_operator_consent_response_contract_does_not_archive_glow", "storage_operator_consent_response_contract_does_not_trigger_daemon", "storage_operator_consent_response_contract_does_not_create_tasks", "storage_operator_consent_response_contract_does_not_schedule_tasks", "storage_operator_consent_response_contract_does_not_decide_readiness"]:
        assert c["non_authority_posture"][required] is True


def test_schema_policy_gap_and_future_requirements() -> None:
    c = _contract()
    records = c["response_artifact_schema"]
    assert [r["schema_field_id"] for r in records] == SCHEMA_FIELD_IDS
    assert all(r["future_only"] is True and r["currently_satisfied"] is False and r["active"] is False for r in records)
    status = c["response_status_policy"]
    assert status["current_response_status"] == "absent"
    for key in ["absent_status_blocks_storage", "denied_status_blocks_storage", "incomplete_status_blocks_storage", "ambiguous_status_blocks_storage", "expired_status_blocks_storage", "revoked_status_blocks_storage", "invalid_status_blocks_storage", "approved_status_not_present_here"]:
        assert status[key] is True
    allow = c["explicit_allow_policy"]
    assert allow["explicit_allow_ledger_write_required"] is True and allow["explicit_allow_glow_archive_required"] is True
    assert allow["explicit_allow_ledger_write_present"] is False and allow["explicit_allow_glow_archive_present"] is False
    digest = c["digest_acknowledgement_policy"]
    assert digest["required_acknowledgement_ids"] == REQUIRED_ACKNOWLEDGEMENT_IDS
    assert digest["supplied_acknowledgement_ids"] == []
    assert digest["missing_acknowledgement_ids"] == REQUIRED_ACKNOWLEDGEMENT_IDS
    assert digest["acknowledgements_not_collected"] is True
    scope = c["scope_acknowledgement_policy"]
    assert scope["allowed_mounts"] == ["/ledger", "/glow"]
    assert all(x in scope["forbidden_mounts"] for x in FORBIDDEN_MOUNTS)
    assert c["expiration_policy"]["expiration_timestamp_required"] is True
    assert c["expiration_policy"]["expiration_timestamp_present"] is False
    assert c["revocation_policy"]["revocation_terms_acknowledgement_required"] is True
    assert c["revocation_policy"]["revocation_terms_acknowledged"] is False
    assert c["denial_and_ambiguity_policy"]["default_without_response"] == "deny_active_storage"
    boundary = c["response_authority_boundary"]
    for key in ["response_contract_is_not_response_artifact", "response_schema_is_not_operator_approval", "request_packet_is_not_consent", "supplied_evidence_does_not_imply_consent", "finalizer_ready_to_commit_does_not_imply_consent", "pr_metadata_guard_ready_does_not_imply_consent", "daemon_recommendation_does_not_imply_consent", "federation_state_does_not_imply_consent"]:
        assert boundary[key] is True
    assert all(x in c["response_activation_gap_summary"]["blocking_gap_ids"] for x in BLOCKING_GAP_IDS)
    assert all(r["status"] == "future_only" and r["met"] is False and r["active"] is False for r in c["future_activation_requirements"])


def test_inputs_hygiene_mounts_and_markdown_escape(tmp_path) -> None:
    payload = b'{"note":"a|b\\nc"}'
    path = tmp_path / "input.json"
    path.write_bytes(payload)
    summary, report = read_json_input(str(path), "storage_policy_contract_json")
    c = build_codex_workcell_storage_operator_consent_response_contract(input_summaries={"storage_policy_contract_json": summary}, input_reports={"storage_policy_contract_json": report}, pr_title="a|b\nc")
    assert c["input_summaries"]["storage_policy_contract_json"]["digest"] == hashlib.sha256(payload).hexdigest()
    assert c["input_summaries"]["storage_policy_contract_json"]["byte_size"] == len(payload)
    assert c["input_summaries"]["storage_operator_consent_request_packet_json"]["provided"] is False
    assert c["reviewer_hygiene_summary"]["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert c["reviewer_hygiene_summary"]["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    assert c["sentientos_mount_alignment"]["/ledger"].endswith("no ledger write here")
    md1 = render_codex_workcell_storage_operator_consent_response_contract_markdown(c)
    md2 = render_codex_workcell_storage_operator_consent_response_contract_markdown(c)
    assert md1 == md2
    assert "a\\|b" in md1 and "<br>" in md1
