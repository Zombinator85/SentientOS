from __future__ import annotations

import hashlib
import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_policy_contract import (
    DIGEST_CHECKS,
    GLOW_ARCHIVE_ITEM_TYPES,
    LEDGER_RECORD_TYPES,
    PARENT_CHAIN_CHECKS,
    PATH_SCOPE_IDS,
    RETENTION_CLASSES,
    WORKCELL_STORAGE_POLICY_CONTRACT_ID,
    build_codex_workcell_storage_policy_contract,
    read_json_input,
    render_codex_workcell_storage_policy_contract_markdown,
)


def test_contract_shape_and_required_policy_catalogs() -> None:
    report = build_codex_workcell_storage_policy_contract()
    assert report["storage_policy_contract_id"] == WORKCELL_STORAGE_POLICY_CONTRACT_ID
    for key in ("metadata_only", "storage_policy_contract_only", "not_runtime_authority", "not_memory_writer", "not_ledger_writer", "not_glow_archiver", "not_daemon_action"):
        assert report[key] is True
    assert set(LEDGER_RECORD_TYPES) <= set(report["ledger_storage_policy"]["allowed_record_types"])
    assert set(GLOW_ARCHIVE_ITEM_TYPES) <= set(report["glow_storage_policy"]["allowed_archive_item_types"])
    assert {r["verification_id"] for r in report["digest_verification_policy"]} == set(DIGEST_CHECKS)
    assert {r["validation_id"] for r in report["parent_chain_validation_policy"]} == set(PARENT_CHAIN_CHECKS)
    assert {r["retention_id"] for r in report["retention_policy"]} == set(RETENTION_CLASSES)
    assert {r["path_scope_id"] for r in report["path_scope_policy"]} == set(PATH_SCOPE_IDS)


def test_storage_remains_inactive_and_non_authoritative() -> None:
    report = build_codex_workcell_storage_policy_contract()
    gap = report["storage_activation_gap_summary"]
    assert gap["active_storage_allowed_now"] is False
    assert gap["active_writer_implementation_present"] is False
    assert gap["operator_consent_present"] is False
    assert gap["ledger_write_performed"] is False
    assert gap["glow_archive_performed"] is False
    assert gap["memory_mutation_performed"] is False
    assert all(value is True for value in report["non_authority_posture"].values())
    assert all(item["status"] == "future_only" and item["met"] is False and item["active"] is False for item in report["future_activation_requirements"])


def test_path_scope_blocks_host_network_backdoor_and_temp_paths() -> None:
    report = build_codex_workcell_storage_policy_contract()
    ledger_forbidden = report["ledger_storage_policy"]["forbidden_path_patterns"]
    glow_forbidden = report["glow_storage_policy"]["forbidden_path_patterns"]
    for phrase in ("absolute host paths outside declared mount", "hidden backdoor paths", "network paths"):
        assert phrase in ledger_forbidden
        assert phrase in glow_forbidden
    assert "temp paths as canonical ledger storage" in ledger_forbidden
    assert "temp paths as canonical glow archive" in glow_forbidden


def test_supplied_vow_inputs_record_raw_byte_digest_and_size(tmp_path) -> None:
    boundary = {"vow_boundary_contract_id": "vow", "canonical_vow_digest": "abc", "canonical_vow_digest_algo": "sha256", "canonical_vow_constraints": [{"constraint_id": "c"}], "forbidden_inference_catalog": [{"inference_id": "f"}]}
    attestation = {"vow_alignment_attestation_id": "att", "canonical_vow_digest": "abc", "attestation_records": [{"alignment_status": "attested"}], "attestation_gap_summary": {"failed_attestation_count": 0, "warning_attestation_count": 0}}
    boundary_path = tmp_path / "boundary.json"
    attestation_path = tmp_path / "attestation.json"
    boundary_path.write_text(json.dumps(boundary, sort_keys=True), encoding="utf-8")
    attestation_path.write_text(json.dumps(attestation, sort_keys=True), encoding="utf-8")
    inputs = {
        "vow_boundary_contract_json": read_json_input(str(boundary_path), "vow_boundary_contract_json"),
        "vow_alignment_attestation_json": read_json_input(str(attestation_path), "vow_alignment_attestation_json"),
    }
    report = build_codex_workcell_storage_policy_contract(inputs)
    assert report["input_summaries"]["vow_boundary_contract_json"]["digest"] == hashlib.sha256(boundary_path.read_bytes()).hexdigest()
    assert report["input_summaries"]["vow_boundary_contract_json"]["byte_size"] == len(boundary_path.read_bytes())
    assert report["input_summaries"]["vow_alignment_attestation_json"]["digest"] == hashlib.sha256(attestation_path.read_bytes()).hexdigest()
    assert report["input_summaries"]["vow_alignment_attestation_json"]["byte_size"] == len(attestation_path.read_bytes())
    assert report["vow_adoption_summary"]["vow_boundary_contract"]["canonical_constraint_count"] == 1
    assert report["vow_adoption_summary"]["vow_alignment_attestation"]["attestation_record_count"] == 1


def test_omitted_inputs_are_represented_false() -> None:
    report = build_codex_workcell_storage_policy_contract()
    for summary in report["input_summaries"].values():
        assert summary == {"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}
    assert report["vow_adoption_summary"]["policy_status"] == "future_only_unmet"


def test_contract_does_not_grant_runtime_or_storage_authority() -> None:
    report = build_codex_workcell_storage_policy_contract()
    posture = report["non_authority_posture"]
    for suffix in ("does_not_decide_readiness", "does_not_write_ledger", "does_not_archive_glow", "does_not_modify_memory", "does_not_trigger_daemon", "does_not_create_tasks", "does_not_schedule_tasks"):
        assert posture[f"storage_policy_contract_{suffix}"] is True


def test_markdown_escaping_handles_pipes_and_newlines() -> None:
    report = build_codex_workcell_storage_policy_contract()
    report["sentientos_mount_alignment"]["/ledger"] = "pipe | and\nnewline"
    markdown = render_codex_workcell_storage_policy_contract_markdown(report)
    assert "pipe \\| and<br>newline" in markdown
