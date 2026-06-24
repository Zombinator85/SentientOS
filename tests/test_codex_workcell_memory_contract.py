from __future__ import annotations

import hashlib

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_memory_contract import (
    FUTURE_ACTIVATION_REQUIREMENTS,
    GLOW_ARCHIVE_ITEM_TYPES,
    LEDGER_RECORD_TYPES,
    NON_AUTHORITY_POSTURE,
    SOURCE_ARTIFACT_FAMILIES,
    CodexWorkcellMemoryContractRequest,
    build_codex_workcell_memory_contract,
    render_codex_workcell_memory_contract_markdown,
)


def test_required_ledger_record_types_and_index_are_consistent() -> None:
    contract = build_codex_workcell_memory_contract()
    catalog = contract["ledger_receipt_chain_contract"]["record_catalog"]
    assert {item["record_type"] for item in catalog} >= set(LEDGER_RECORD_TYPES)
    assert set(contract["ledger_record_type_index"]) == {item["record_type"] for item in catalog}
    for record_type, entry in contract["ledger_record_type_index"].items():
        assert catalog[entry["position"]]["record_type"] == record_type


def test_required_glow_archive_item_types_and_index_are_consistent() -> None:
    contract = build_codex_workcell_memory_contract()
    catalog = contract["glow_evidence_archive_contract"]["archive_catalog"]
    assert {item["archive_item_type"] for item in catalog} >= set(GLOW_ARCHIVE_ITEM_TYPES)
    assert set(contract["glow_archive_item_type_index"]) == {item["archive_item_type"] for item in catalog}
    for item_type, entry in contract["glow_archive_item_type_index"].items():
        assert catalog[entry["position"]]["archive_item_type"] == item_type


def test_source_artifact_alignment_includes_required_families() -> None:
    contract = build_codex_workcell_memory_contract()
    assert {item["artifact_family"] for item in contract["source_artifact_alignment"]} >= set(SOURCE_ARTIFACT_FAMILIES)
    assert all(item["source_digest_expected"] is True for item in contract["source_artifact_alignment"])


def test_non_authority_posture_flags_are_present_and_true() -> None:
    contract = build_codex_workcell_memory_contract()
    assert set(NON_AUTHORITY_POSTURE) <= set(contract["non_authority_posture"])
    assert all(contract["non_authority_posture"][key] is True for key in NON_AUTHORITY_POSTURE)
    assert contract["not_ledger_writer"] is True
    assert contract["not_glow_archiver"] is True
    assert contract["not_memory_writer"] is True


def test_future_activation_requirements_are_future_only_inactive_unmet() -> None:
    contract = build_codex_workcell_memory_contract()
    assert {item["requirement"] for item in contract["future_activation_requirements"]} == set(FUTURE_ACTIVATION_REQUIREMENTS)
    assert all(item["status"] == "future_only" and item["met"] is False and item["active"] is False for item in contract["future_activation_requirements"])


def test_contract_does_not_grant_runtime_or_readiness_authority() -> None:
    contract = build_codex_workcell_memory_contract()
    posture = contract["non_authority_posture"]
    assert posture["memory_contract_does_not_decide_readiness"] is True
    assert posture["memory_contract_does_not_authorize_commit"] is True
    assert posture["memory_contract_does_not_authorize_pr_creation"] is True
    assert posture["memory_contract_does_not_bypass_finalizer"] is True
    assert posture["memory_contract_does_not_bypass_pr_metadata_guard"] is True


def test_contract_does_not_write_ledger_archive_glow_modify_memory_or_trigger_actions() -> None:
    contract = build_codex_workcell_memory_contract()
    posture = contract["non_authority_posture"]
    for key in (
        "memory_contract_does_not_write_ledger",
        "memory_contract_does_not_archive_glow",
        "memory_contract_does_not_modify_memory",
        "memory_contract_does_not_trigger_daemon",
        "memory_contract_does_not_create_tasks",
        "memory_contract_does_not_schedule_tasks",
        "memory_contract_does_not_send_alerts",
    ):
        assert posture[key] is True
    assert contract["ledger_receipt_chain_contract"]["writes_ledger_entries"] is False
    assert contract["glow_evidence_archive_contract"]["archives_evidence"] is False


def test_omitted_inputs_produce_provided_false_summaries() -> None:
    contract = build_codex_workcell_memory_contract()
    for summary in contract["input_summaries"].values():
        assert summary == {"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}


def test_supplied_json_inputs_record_raw_byte_digest_and_size(tmp_path) -> None:
    payload = b'{"alpha": true, "text": "pipe|newline\\n"}'
    path = tmp_path / "input.json"
    path.write_bytes(payload)
    contract = build_codex_workcell_memory_contract(CodexWorkcellMemoryContractRequest(health_snapshot_json=str(path)))
    summary = contract["input_summaries"]["health_snapshot_json"]
    assert summary["provided"] is True
    assert summary["digest"] == hashlib.sha256(payload).hexdigest()
    assert summary["byte_size"] == len(payload)
    assert summary["readable_json"] is True


def test_json_output_is_deterministic_for_same_inputs(tmp_path) -> None:
    path = tmp_path / "input.json"
    path.write_text('{"stable": true}\n', encoding="utf-8")
    request = CodexWorkcellMemoryContractRequest(pulse_contract_json=str(path))
    assert build_codex_workcell_memory_contract(request) == build_codex_workcell_memory_contract(request)


def test_markdown_output_is_deterministic_and_escapes_tables() -> None:
    contract = build_codex_workcell_memory_contract()
    contract["input_summaries"]["health_snapshot_json"] = {"provided": True, "path": "a|b\nc", "digest": "d|e", "byte_size": 1, "readable_json": True, "error": None}
    first = render_codex_workcell_memory_contract_markdown(contract)
    second = render_codex_workcell_memory_contract_markdown(contract)
    assert first == second
    assert "a\\|b<br>c" in first
    assert "d\\|e" in first
