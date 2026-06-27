from __future__ import annotations

import hashlib

import pytest

from sentientos.codex_workcell_storage_operator_consent_request_packet import (
    BLOCKING_GAP_IDS,
    FORBIDDEN_SCOPE,
    INPUT_SPECS,
    NON_AUTHORITY_POSTURE,
    REQUIRED_DIGEST_BINDINGS,
    build_codex_workcell_storage_operator_consent_request_packet,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_operator_consent_request_packet_markdown,
)

pytestmark = pytest.mark.no_legacy_skip


def _packet(tmp_path):
    raw = b'{"storage_policy_contract_id":"policy.v1","verification_status":"passed"}\n'
    p = tmp_path / "policy.json"
    p.write_bytes(raw)
    summary, report = read_json_input(str(p), "storage_policy_contract_json")
    summaries = {k: omitted_input(k) for k in INPUT_SPECS}
    summaries["storage_policy_contract_json"] = summary
    reports = {"storage_policy_contract_json": report}
    return build_codex_workcell_storage_operator_consent_request_packet(
        input_summaries=summaries,
        input_reports=reports,
        commit_sha="abc",
        pr_number="7",
        pr_title="Pipe | New\nLine",
    ), raw


def test_packet_required_non_authority_flags_and_context(tmp_path):
    packet, _ = _packet(tmp_path)
    assert packet["storage_operator_consent_request_packet_id"] == "codex_workcell_storage_operator_consent_request_packet.v1"
    for key in ("metadata_only", "request_packet_only", "consent_request_not_presented", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed"):
        assert packet[key] is True
    for key in ("operator_consent_present", "active_storage_allowed_now", "writes_performed", "archives_performed", "memory_mutation_performed", "execution_performed"):
        assert packet[key] is False
    assert packet["request_packet_context"] == {
        "commit_sha": "abc", "pr_number": "7", "pr_title": "Pipe | New\nLine", "supplied_report_count": 1,
        "request_packet_only": True, "consent_request_not_presented": True, "consent_not_collected": True, "no_action_taken": True,
    }


def test_evidence_records_supplied_digest_byte_size_and_omissions(tmp_path):
    packet, raw = _packet(tmp_path)
    evidence = {r["input_id"]: r for r in packet["evidence_digest_packet"]}
    supplied = evidence["storage_policy_contract_json"]
    assert supplied["provided"] is True
    assert supplied["source_digest"] == hashlib.sha256(raw).hexdigest()
    assert supplied["source_byte_size"] == len(raw)
    assert supplied["detected_report_id"] == "policy.v1"
    omitted = evidence["vow_boundary_contract_json"]
    assert omitted["provided"] is False
    assert omitted["missing_reason"] == "optional_input_not_supplied"
    assert packet["input_summaries"]["vow_boundary_contract_json"]["provided"] is False


def test_template_scope_response_fields_and_policy_statements(tmp_path):
    packet, _ = _packet(tmp_path)
    template = packet["operator_request_template"]
    assert template["template_not_presented"] is True
    assert template["response_not_collected"] is True
    assert template["requested_scope"] == ["/ledger", "/glow"]
    assert all(scope in template["forbidden_scope"] for scope in FORBIDDEN_SCOPE)
    assert template["no_message_sent"] and template["no_ui_rendered"] and template["no_external_delivery"]
    assert all(v in (None, False) for v in packet["required_operator_response_fields"].values())
    assert packet["consent_scope_statement"]["allowed_mounts"] == ["/ledger", "/glow"]
    assert packet["consent_scope_statement"]["daemon_action_not_authorized"] is True


def test_digest_lifetime_revocation_denial_authority_gaps(tmp_path):
    packet, _ = _packet(tmp_path)
    digest = packet["consent_digest_binding_statement"]
    assert digest["required_digest_bindings"] == REQUIRED_DIGEST_BINDINGS
    assert digest["supplied_digest_bindings"]["storage_policy_contract_digest"]
    assert "canonical_vow_digest" in digest["missing_digest_bindings"]
    assert digest["digest_binding_not_acknowledged"] is True
    assert packet["consent_lifetime_statement"]["expiration_required"] is True
    assert packet["consent_lifetime_statement"]["lifetime_not_started"] is True
    assert packet["consent_revocation_statement"]["revocation_terms_required"] is True
    assert packet["consent_revocation_statement"]["revocation_not_performed"] is True
    assert packet["consent_denial_statement"]["default_without_response"] == "deny_active_storage"
    boundary = packet["consent_authority_boundary_statement"]
    for key in ("request_packet_is_not_consent", "request_template_is_not_consent", "supplied_evidence_does_not_imply_consent", "finalizer_ready_to_commit_does_not_imply_consent", "pr_metadata_guard_ready_does_not_imply_consent", "daemon_recommendation_does_not_imply_consent", "federation_state_does_not_imply_consent"):
        assert boundary[key] is True
    assert all(gap in packet["consent_request_gap_summary"]["blocking_gap_ids"] for gap in BLOCKING_GAP_IDS)


def test_hygiene_mount_future_and_non_authority_posture(tmp_path):
    packet, _ = _packet(tmp_path)
    hygiene = packet["reviewer_hygiene_summary"]
    assert hygiene["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    assert hygiene["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert packet["sentientos_mount_alignment"]["/ledger"] == "future requested consent scope; no ledger write here"
    assert all(item["status"] == "future_only" and item["met"] is False and item["active"] is False for item in packet["future_activation_requirements"])
    assert packet["non_authority_posture"] == NON_AUTHORITY_POSTURE
    assert all(packet["non_authority_posture"].values())


def test_markdown_deterministic_and_escaped(tmp_path):
    packet, _ = _packet(tmp_path)
    one = render_codex_workcell_storage_operator_consent_request_packet_markdown(packet)
    two = render_codex_workcell_storage_operator_consent_request_packet_markdown(packet)
    assert one == two
    assert one.startswith("# Codex Workcell Storage Operator Consent Request Packet")
    assert "Pipe \\| New<br>Line" in one


def test_packet_does_not_grant_readiness_or_runtime_authority(tmp_path):
    packet, _ = _packet(tmp_path)
    posture = packet["non_authority_posture"]
    assert posture["storage_operator_consent_request_packet_does_not_decide_readiness"] is True
    assert posture["storage_operator_consent_request_packet_does_not_bind_runtime_authority"] is True
    assert posture["storage_operator_consent_request_packet_does_not_write_ledger"] is True
    assert posture["storage_operator_consent_request_packet_does_not_archive_glow"] is True
    assert posture["storage_operator_consent_request_packet_does_not_modify_memory"] is True
    assert posture["storage_operator_consent_request_packet_does_not_trigger_daemon"] is True
    assert posture["storage_operator_consent_request_packet_does_not_create_tasks"] is True
    assert posture["storage_operator_consent_request_packet_does_not_schedule_tasks"] is True
