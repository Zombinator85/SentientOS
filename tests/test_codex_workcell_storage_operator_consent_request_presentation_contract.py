from __future__ import annotations

import json

import pytest


pytestmark = pytest.mark.no_legacy_skip
from sentientos.codex_workcell_storage_operator_consent_request_presentation_contract import (
    DELIVERY_SCOPE_REQUIREMENTS,
    DENIED_INFERENCES,
    FUTURE_ACTIVATION_REQUIREMENTS,
    INPUT_SPECS,
    MISSING_GAPS,
    NON_AUTHORITY_POSTURE,
    OPERATOR_ATTENTION_REQUIREMENTS,
    PRESENTATION_AUTHORITY_REQUIREMENTS,
    PRESENTATION_SURFACES,
    REQUEST_PACKET_INTEGRITY_REQUIREMENTS,
    RESPONSE_PATH_REQUIREMENTS,
    WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PRESENTATION_CONTRACT_ID,
    build_codex_workcell_storage_operator_consent_request_presentation_contract,
    omitted_input,
    render_codex_workcell_storage_operator_consent_request_presentation_contract_markdown,
)


def _contract():
    summaries = {key: omitted_input(key) for key in INPUT_SPECS}
    return build_codex_workcell_storage_operator_consent_request_presentation_contract(input_summaries=summaries, commit="abc", pr="123")


def test_contract_flags_and_no_active_authority():
    contract = _contract()
    assert contract["storage_operator_consent_request_presentation_contract_id"] == WORKCELL_STORAGE_OPERATOR_CONSENT_REQUEST_PRESENTATION_CONTRACT_ID
    for key in ("metadata_only", "contract_only", "future_only", "presentation_not_performed", "request_not_presented", "ui_not_rendered", "message_not_sent", "external_delivery_not_performed", "response_artifact_not_created", "response_not_collected", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed"):
        assert contract[key] is True
    for key in ("operator_consent_present", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed"):
        assert contract[key] is False
    for key in ("not_presentation_runner", "not_ui_renderer", "not_message_sender", "not_external_delivery_system", "not_response_artifact_creator", "not_response_collector", "not_consent_collector", "not_runtime_authority", "not_memory_writer", "not_ledger_writer", "not_glow_archiver", "not_watcher", "not_scheduler", "not_executor", "not_daemon_action", "not_task_creator", "not_alerting_system", "not_model_training", "not_reinforcement_learning"):
        assert contract[key] is True


def test_boundary_context_denies_readiness_and_presentation_inferences():
    context = _contract()["presentation_boundary_context"]
    assert context["commit"] == "abc"
    assert context["pr"] == "123"
    assert context["no_request_presentation_action_occurred"] is True
    separated = set(context["presentation_authority_separate_from"])
    for item in ["request_packet_existence", "packet_verification", "evidence_dossier_completeness", "dossier_verification", "response_schema_existence", "response_verifier_success", "finalizer_readiness", "pr_metadata_guard_readiness", "matrix_passage", "daemon_recommendations", "federation_state", "runtime_authority_contract_presence", "storage_policy_evidence"]:
        assert item in separated


def test_required_inventories_are_future_only_unsatisfied_or_denied():
    contract = _contract()
    surfaces = {row["surface_id"]: row for row in contract["presentation_surface_inventory"]}
    assert set(PRESENTATION_SURFACES) <= set(surfaces)
    assert all(row["future_only"] is True and row["active_now"] is False for row in surfaces.values())
    for key, expected in [("required_presentation_authority_requirements", PRESENTATION_AUTHORITY_REQUIREMENTS), ("required_operator_attention_requirements", OPERATOR_ATTENTION_REQUIREMENTS), ("required_delivery_scope_requirements", DELIVERY_SCOPE_REQUIREMENTS), ("required_request_packet_integrity_requirements", REQUEST_PACKET_INTEGRITY_REQUIREMENTS), ("required_response_path_requirements", RESPONSE_PATH_REQUIREMENTS)]:
        rows = {row["requirement_id"]: row for row in contract[key]}
        assert set(expected) <= set(rows)
        assert all(row["currently_satisfied"] is False for row in rows.values())
    denied = {row["inference_id"]: row for row in contract["denied_inferences"]}
    assert set(DENIED_INFERENCES) <= set(denied)
    assert all(row["denied"] is True for row in denied.values())
    gaps = {row["gap_id"]: row for row in contract["missing_real_world_presentation_summary"]}
    assert set(MISSING_GAPS) <= set(gaps)
    assert all(row["present"] is True and row["severity"] == "blocking" and row["active"] is False for row in gaps.values())


def test_hygiene_mount_future_requirements_and_non_authority_posture():
    contract = _contract()
    hygiene = contract["reviewer_hygiene_summary"]
    assert hygiene["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert hygiene["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    assert set(contract["sentientos_mount_alignment"]) == {"/ledger", "/glow", "/vow", "/pulse", "/daemon"}
    assert "no ledger write" in contract["sentientos_mount_alignment"]["/ledger"]
    futures = {row["requirement"]: row for row in contract["future_activation_requirements"]}
    assert set(FUTURE_ACTIVATION_REQUIREMENTS) <= set(futures)
    assert all(row["future_only"] is True and row["met"] is False and row["active"] is False for row in futures.values())
    assert contract["non_authority_posture"] == NON_AUTHORITY_POSTURE
    assert all(contract["non_authority_posture"].values())


def test_omitted_inputs_and_deterministic_json_and_markdown_escaping():
    contract = _contract()
    assert set(contract["input_summaries"]) == set(INPUT_SPECS)
    assert all(summary["provided"] is False and summary["digest"] is None for summary in contract["input_summaries"].values())
    assert json.dumps(contract, sort_keys=True) == json.dumps(_contract(), sort_keys=True)
    contract["input_summaries"]["storage_operator_consent_request_packet_json"]["path"] = "pipe|newline\nvalue"
    markdown = render_codex_workcell_storage_operator_consent_request_presentation_contract_markdown(contract)
    assert "Codex Workcell Storage Operator Consent Request Presentation Boundary Contract" in markdown
    assert "\\|" in markdown or "<br>" in markdown
