from __future__ import annotations

import hashlib
import json
import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_runtime_authority_contract import (
    BOUNDARY_SPECS,
    BLOCKING_GAP_IDS,
    FUTURE_REQUIREMENTS,
    INPUT_SPECS,
    WORKCELL_STORAGE_RUNTIME_AUTHORITY_CONTRACT_ID,
    build_codex_workcell_storage_runtime_authority_contract,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_runtime_authority_contract_markdown,
)


def _contract():
    return build_codex_workcell_storage_runtime_authority_contract(
        input_summaries={input_id: omitted_input(input_id) for input_id in INPUT_SPECS},
        commit_sha="abc123",
        pr_number="42",
        pr_title="title",
    )


def test_contract_flags_and_runtime_context_are_non_authoritative():
    report = _contract()
    assert report["storage_runtime_authority_contract_id"] == WORKCELL_STORAGE_RUNTIME_AUTHORITY_CONTRACT_ID
    for key in ("metadata_only", "runtime_authority_contract_only", "runtime_binding_not_performed"):
        assert report[key] is True
    for key in ("active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed"):
        assert report[key] is False
    assert report["runtime_context"] == {"commit_sha": "abc123", "pr_number": "42", "pr_title": "title", "supplied_report_count": 0, "runtime_authority_contract_only": True, "no_action_taken": True}


def test_boundary_catalog_contains_all_required_future_inactive_boundaries():
    report = _contract()
    expected = {boundary_id for boundary_id, _category, _summary in BOUNDARY_SPECS}
    catalog = report["runtime_authority_boundary_catalog"]
    assert {entry["boundary_id"] for entry in catalog} == expected
    for entry in catalog:
        assert entry["required_for_active_storage"] is True
        assert entry["currently_bound"] is False
        assert entry["future_only"] is True
        assert entry["active"] is False
        assert entry["forbidden_inference"]
        assert entry["reviewer_summary"]


def test_policy_sections_keep_authority_absent():
    report = _contract()
    finalizer = report["finalizer_guard_binding_policy"]
    assert finalizer["finalizer_ready_to_commit_is_not_runtime_write_authority"] is True
    assert finalizer["pr_metadata_guard_ready_is_not_runtime_write_authority"] is True
    assert finalizer["currently_bound"] is False
    assert finalizer["binding_not_performed"] is True
    consent = report["operator_consent_policy"]
    assert consent["operator_consent_required"] is True
    assert consent["operator_consent_present"] is False
    assert consent["consent_must_be_scoped_to_mounts"] == ["/ledger", "/glow"]
    storage = report["storage_enforcement_policy"]
    assert storage["active_ledger_writer_present"] is False
    assert storage["active_glow_archiver_present"] is False
    assert "report_status_as_runtime_authority" in storage["forbidden_runtime_write_modes"]
    digest = report["digest_and_parent_runtime_policy"]
    assert digest["digest_verification_runtime_present"] is False
    assert digest["parent_chain_runtime_present"] is False
    assert digest["runtime_verification_not_performed"] is True
    pulse = report["pulse_daemon_runtime_boundary"]
    assert pulse["pulse_watcher_contract_present"] is False
    assert pulse["daemon_action_contract_present"] is False
    assert pulse["daemon_recommendations_are_not_commands"] is True
    federation = report["federation_runtime_boundary"]
    assert federation["federation_consensus_present"] is False
    assert federation["federation_consensus_not_established"] is True


def test_gap_hygiene_future_requirements_and_non_authority_posture():
    report = _contract()
    gaps = report["runtime_activation_gap_summary"]
    for gap in BLOCKING_GAP_IDS:
        assert gap in gaps["blocking_gap_ids"]
    assert gaps["active_storage_allowed_now"] is False
    assert gaps["runtime_binding_not_performed"] is True
    hygiene = report["reviewer_hygiene_summary"]
    assert hygiene["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert hygiene["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    assert hygiene["no_runtime_effect"] is True
    assert {item["requirement"] for item in report["future_activation_requirements"]} == set(FUTURE_REQUIREMENTS)
    for item in report["future_activation_requirements"]:
        assert item["status"] == "future_only"
        assert item["met"] is False
        assert item["active"] is False
    assert all(value is True for value in report["non_authority_posture"].values())
    for key in ("storage_runtime_authority_contract_does_not_decide_readiness", "storage_runtime_authority_contract_does_not_bind_runtime_authority", "storage_runtime_authority_contract_does_not_write_ledger", "storage_runtime_authority_contract_does_not_archive_glow", "storage_runtime_authority_contract_does_not_modify_memory", "storage_runtime_authority_contract_does_not_trigger_daemon", "storage_runtime_authority_contract_does_not_create_tasks", "storage_runtime_authority_contract_does_not_schedule_tasks"):
        assert report["non_authority_posture"][key] is True


def test_input_summaries_record_raw_digest_and_omissions(tmp_path):
    path = tmp_path / "input.json"
    raw = b'{"name":"report"}\n'
    path.write_bytes(raw)
    summary, loaded = read_json_input(str(path), "storage_policy_contract_json")
    assert loaded == {"name": "report"}
    assert summary["digest"] == hashlib.sha256(raw).hexdigest()
    assert summary["byte_size"] == len(raw)
    omitted = omitted_input("storage_execution_dossier_json")
    assert omitted == {"input_id": "storage_execution_dossier_json", "provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}


def test_json_and_markdown_are_deterministic_and_escape_cells():
    report = _contract()
    first = json.dumps(report, sort_keys=True, indent=2)
    second = json.dumps(_contract(), sort_keys=True, indent=2)
    assert first == second
    report["runtime_context"]["pr_title"] = "pipe | newline\nvalue"
    md1 = render_codex_workcell_storage_runtime_authority_contract_markdown(report)
    md2 = render_codex_workcell_storage_runtime_authority_contract_markdown(report)
    assert md1 == md2
    assert "pipe \\| newline<br>value" in md1
    assert md1.startswith("# Codex Workcell Storage Runtime Authority Boundary Contract")
