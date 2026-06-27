from __future__ import annotations

import copy
import hashlib
import json

import pytest

from sentientos.codex_workcell_storage_operator_consent_request_packet import INPUT_SPECS, build_codex_workcell_storage_operator_consent_request_packet, omitted_input as packet_omitted
from sentientos.codex_workcell_storage_operator_consent_request_packet_verifier import OPTIONAL_INPUT_IDS, NON_AUTHORITY_POSTURE, omitted_input, read_json_input, render_codex_workcell_storage_operator_consent_request_packet_verifier_markdown, verify_codex_workcell_storage_operator_consent_request_packet

pytestmark = pytest.mark.no_legacy_skip


def _valid_report(tmp_path):
    summaries = {}
    reports = {}
    for input_id in INPUT_SPECS:
        raw = json.dumps({"verification_status": "ok", input_id.replace("_json", "_id"): input_id}, sort_keys=True).encode() + b"\n"
        path = tmp_path / f"{input_id}.json"
        path.write_bytes(raw)
        summary, report = read_json_input(str(path), input_id)
        summaries[input_id] = summary
        reports[input_id] = report
    packet = build_codex_workcell_storage_operator_consent_request_packet(input_summaries=summaries, input_reports=reports, pr_title="Pipe | New\nLine")
    raw = json.dumps(packet, sort_keys=True).encode() + b"\n"
    packet_path = tmp_path / "packet.json"
    packet_path.write_bytes(raw)
    packet_summary, packet_loaded = read_json_input(str(packet_path), "storage_operator_consent_request_packet_json")
    optional = {k: omitted_input(k) for k in OPTIONAL_INPUT_IDS}
    return verify_codex_workcell_storage_operator_consent_request_packet(storage_operator_consent_request_packet=packet_loaded, storage_operator_consent_request_packet_summary=packet_summary, optional_reports={}, optional_summaries=optional), packet, raw


def _status_for_mutation(tmp_path, mutator):
    _, packet, _ = _valid_report(tmp_path)
    packet = copy.deepcopy(packet)
    mutator(packet)
    raw = json.dumps(packet, sort_keys=True).encode()
    summary = {"input_id": "storage_operator_consent_request_packet_json", "provided": True, "path": "packet.json", "digest_algo": "sha256", "digest": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "readable_json": True, "error": None}
    report = verify_codex_workcell_storage_operator_consent_request_packet(storage_operator_consent_request_packet=packet, storage_operator_consent_request_packet_summary=summary, optional_reports={}, optional_summaries={k: omitted_input(k) for k in OPTIONAL_INPUT_IDS})
    return report


def test_valid_operator_consent_request_packet_verifies(tmp_path):
    report, _, raw = _valid_report(tmp_path)
    assert report["verification_status"] == "storage_operator_consent_request_packet_verified"
    assert report["violation_summary"]["violation_count"] == 0
    assert report["request_packet_summary"]["source_digest"] == hashlib.sha256(raw).hexdigest()
    assert report["request_packet_summary"]["source_byte_size"] == len(raw)
    assert report["optional_context_summary"][0]["provided"] is False


@pytest.mark.parametrize(("path", "value"), [
    (("metadata_only",), None), (("request_packet_only",), False), (("consent_request_not_presented",), False),
    (("consent_not_collected",), False), (("consent_not_implied",), False), (("operator_consent_present",), True),
    (("runtime_binding_not_performed",), False), (("active_storage_allowed_now",), True), (("writes_performed",), True),
    (("archives_performed",), True), (("memory_mutation_performed",), True), (("evidence_digest_packet",), []),
    (("operator_request_template",), None), (("operator_request_template", "template_not_presented"), False),
    (("operator_request_template", "response_not_collected"), False), (("operator_request_template", "no_message_sent"), False),
    (("operator_request_template", "no_ui_rendered"), False), (("operator_request_template", "no_external_delivery"), False),
    (("operator_request_template", "requested_scope"), ["/ledger"]), (("required_operator_response_fields", "operator_identity"), "keeper"),
    (("required_operator_response_fields", "explicit_allow_ledger_write"), True), (("required_operator_response_fields", "consent_artifact_created"), True),
    (("consent_digest_binding_statement", "required_digest_bindings"), []), (("consent_digest_binding_statement", "digest_binding_not_acknowledged"), False),
    (("consent_lifetime_statement", "expiration_supplied"), True), (("consent_lifetime_statement", "lifetime_not_started"), False),
    (("consent_revocation_statement", "revocation_terms_acknowledged"), True), (("consent_revocation_statement", "revocation_not_performed"), False),
    (("consent_denial_statement", "default_without_response"), "allow"), (("consent_denial_statement", "remote_or_daemon_response_not_accepted"), False),
    (("consent_authority_boundary_statement", "supplied_evidence_does_not_imply_consent"), False), (("consent_authority_boundary_statement", "finalizer_ready_to_commit_does_not_imply_consent"), False),
    (("consent_authority_boundary_statement", "pr_metadata_guard_ready_does_not_imply_consent"), False), (("consent_authority_boundary_statement", "daemon_recommendation_does_not_imply_consent"), False),
    (("consent_authority_boundary_statement", "federation_state_does_not_imply_consent"), False), (("consent_request_gap_summary", "blocking_gap_ids"), []),
])
def test_required_packet_invariants_fail(tmp_path, path, value):
    def mutate(packet):
        target = packet
        for key in path[:-1]:
            target = target[key]
        if value is None:
            target.pop(path[-1], None)
        else:
            target[path[-1]] = value
    report = _status_for_mutation(tmp_path, mutate)
    assert report["verification_status"] != "storage_operator_consent_request_packet_verified"
    assert report["violation_summary"]["violation_count"] > 0


def test_missing_supported_evidence_role_and_bad_supplied_digest_fail(tmp_path):
    report = _status_for_mutation(tmp_path, lambda p: p["evidence_digest_packet"].pop())
    assert report["evidence_digest_packet_results"]["passed"] is False
    report = _status_for_mutation(tmp_path, lambda p: p["evidence_digest_packet"][0].pop("source_digest"))
    assert report["evidence_digest_packet_results"]["supplied_records_have_digest_and_byte_size"] is False


def test_forbidden_scope_missing_path_classes_fails(tmp_path):
    report = _status_for_mutation(tmp_path, lambda p: p["operator_request_template"]["forbidden_scope"].remove("/vow"))
    assert report["operator_request_template_results"]["forbidden_scope_complete"] is False


def test_non_authority_and_future_requirements(tmp_path):
    report, _, _ = _valid_report(tmp_path)
    assert report["non_authority_posture"] == NON_AUTHORITY_POSTURE
    assert all(report["non_authority_posture"].values())
    assert all(r["status"] == "future_only" and r["active"] is False and r["met"] is False for r in report["future_activation_requirements"])
    for key in ("consent_request_not_presented", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed", "not_ledger_writer", "not_glow_archiver", "not_daemon_action", "not_task_creator"):
        assert report[key] is True
    assert report["operator_consent_present"] is False
    assert report["active_storage_allowed_now"] is False


def test_reviewer_hygiene_summary_and_markdown_escape(tmp_path):
    report, _, _ = _valid_report(tmp_path)
    assert report["reviewer_hygiene_summary"]["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    assert report["reviewer_hygiene_summary"]["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    one = render_codex_workcell_storage_operator_consent_request_packet_verifier_markdown(report)
    two = render_codex_workcell_storage_operator_consent_request_packet_verifier_markdown(report)
    assert one == two
    assert one.startswith("# Codex Workcell Storage Operator Consent Request Packet Verifier")
    assert "Pipe \\| New<br>Line" in one
