from __future__ import annotations

import copy
import hashlib
import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_memory_candidate_verifier import (
    NON_AUTHORITY_POSTURE,
    render_codex_workcell_memory_candidate_verifier_markdown,
    verify_codex_workcell_memory_candidate_bundle,
)
from sentientos.codex_workcell_memory_contract import build_codex_workcell_memory_contract


def _summary(bundle: dict) -> dict:
    raw = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
    return {"provided": True, "path": "bundle.json", "digest_algo": "sha256", "digest": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "readable_json": True, "error": None}


def _bundle() -> dict:
    return {
        "memory_candidate_bundle_id": "codex_workcell_memory_candidate_bundle.v1",
        "metadata_only": True,
        "candidate_bundle_only": True,
        "not_ledger_writer": True,
        "not_glow_archiver": True,
        "input_summaries": {"matrix_json": {"provided": True, "path": "m.json", "digest": "d", "byte_size": 1, "readable_json": True, "error": None}},
        "candidate_ledger_entries": [],
        "candidate_glow_items": [],
        "source_artifact_map": [],
        "candidate_chain_summary": {"candidate_ledger_entry_count": 0, "no_ledger_write_performed": True},
        "candidate_archive_summary": {"candidate_glow_item_count": 0, "no_glow_archive_performed": True},
        "future_activation_requirements": [{"requirement": "explicit ledger writer implementation", "status": "future_only", "met": False, "active": False}],
        "non_authority_posture": {k.replace("memory_candidate_verifier", "memory_candidate_bundle"): True for k in NON_AUTHORITY_POSTURE},
    }


def _verify(bundle: dict, contract: dict | None = None) -> dict:
    return verify_codex_workcell_memory_candidate_bundle(bundle, _summary(bundle), contract, {"provided": bool(contract), "path": "contract.json" if contract else None, "digest": "c" if contract else None, "byte_size": 1 if contract else None, "readable_json": bool(contract), "error": None})


def _add_ledger(bundle: dict, **overrides) -> dict:
    entry = {"candidate_entry_id": "e1", "source_input_id": "matrix_json", "would_be_record_type": "matrix_receipt", "candidate_only": True, "no_write_performed": True, "source_artifact_digest": "d"}
    entry.update(overrides)
    bundle["candidate_ledger_entries"] = [entry]
    bundle["candidate_chain_summary"]["candidate_ledger_entry_count"] = 1
    bundle["source_artifact_map"] = [{"input_id": "matrix_json", "provided": True, "candidate_ledger_entry_ids": [entry["candidate_entry_id"]], "candidate_glow_item_ids": []}]
    return bundle


def _add_glow(bundle: dict, **overrides) -> dict:
    item = {"candidate_glow_item_id": "g1", "source_input_id": "matrix_json", "would_be_archive_item_type": "matrix_report_snapshot", "candidate_only": True, "no_archive_performed": True, "source_digest": "d", "related_candidate_ledger_entry_id": None}
    item.update(overrides)
    bundle["candidate_glow_items"] = [item]
    bundle["candidate_archive_summary"]["candidate_glow_item_count"] = 1
    if not bundle["source_artifact_map"]:
        bundle["source_artifact_map"] = [{"input_id": "matrix_json", "provided": True, "candidate_ledger_entry_ids": [], "candidate_glow_item_ids": [item["candidate_glow_item_id"]]}]
    else:
        bundle["source_artifact_map"][0]["candidate_glow_item_ids"] = [item["candidate_glow_item_id"]]
    return bundle


def test_valid_minimal_candidate_bundle_verifies_with_no_entries_items() -> None:
    report = _verify(_bundle())
    assert report["verification_status"] == "memory_candidate_bundle_verified"
    assert report["violation_summary"]["violation_count"] == 0


def test_supplied_candidate_ledger_entry_referencing_provided_input_passes() -> None:
    report = _verify(_add_ledger(_bundle()))
    assert report["candidate_ledger_entry_results"][0]["passed"] is True


def test_supplied_candidate_glow_item_referencing_provided_input_passes() -> None:
    report = _verify(_add_glow(_bundle()))
    assert report["candidate_glow_item_results"][0]["passed"] is True


def test_ledger_entry_referencing_missing_input_fails() -> None:
    report = _verify(_add_ledger(_bundle(), source_input_id="missing"))
    assert "ledger_entries_reference_provided_inputs" in report["violation_summary"]["violation_check_ids"]


def test_glow_item_referencing_missing_input_fails() -> None:
    report = _verify(_add_glow(_bundle(), source_input_id="missing"))
    assert "glow_items_reference_provided_inputs" in report["violation_summary"]["violation_check_ids"]


def test_duplicate_candidate_ledger_entry_ids_fail() -> None:
    b = _add_ledger(_bundle())
    b["candidate_ledger_entries"].append(copy.deepcopy(b["candidate_ledger_entries"][0]))
    b["candidate_chain_summary"]["candidate_ledger_entry_count"] = 2
    report = _verify(b)
    assert "candidate_ledger_entry_ids_unique" in report["violation_summary"]["violation_check_ids"]


def test_duplicate_candidate_glow_item_ids_fail() -> None:
    b = _add_glow(_bundle())
    b["candidate_glow_items"].append(copy.deepcopy(b["candidate_glow_items"][0]))
    b["candidate_archive_summary"]["candidate_glow_item_count"] = 2
    report = _verify(b)
    assert "candidate_glow_item_ids_unique" in report["violation_summary"]["violation_check_ids"]


def test_source_artifact_map_linked_ids_must_exist() -> None:
    b = _bundle()
    b["source_artifact_map"] = [{"input_id": "matrix_json", "provided": True, "candidate_ledger_entry_ids": ["missing"], "candidate_glow_item_ids": ["missing"]}]
    report = _verify(b)
    assert "source_artifact_map_links_existing_ledger_ids" in report["violation_summary"]["violation_check_ids"]
    assert "source_artifact_map_links_existing_glow_ids" in report["violation_summary"]["violation_check_ids"]


def test_chain_summary_count_mismatch_fails() -> None:
    b = _add_ledger(_bundle())
    b["candidate_chain_summary"]["candidate_ledger_entry_count"] = 0
    assert "candidate_chain_summary_counts_match" in _verify(b)["violation_summary"]["violation_check_ids"]


def test_archive_summary_count_mismatch_fails() -> None:
    b = _add_glow(_bundle())
    b["candidate_archive_summary"]["candidate_glow_item_count"] = 0
    assert "candidate_archive_summary_counts_match" in _verify(b)["violation_summary"]["violation_check_ids"]


def test_missing_candidate_only_on_entries_items_fails() -> None:
    b = _add_glow(_add_ledger(_bundle(), candidate_only=False), candidate_only=False)
    ids = _verify(b)["violation_summary"]["violation_check_ids"]
    assert "ledger_entries_have_candidate_only_true" in ids
    assert "glow_items_have_candidate_only_true" in ids


def test_missing_no_write_or_archive_flags_fail() -> None:
    b = _add_glow(_add_ledger(_bundle(), no_write_performed=False), no_archive_performed=False)
    ids = _verify(b)["violation_summary"]["violation_check_ids"]
    assert "ledger_entries_have_no_write_true" in ids
    assert "glow_items_have_no_archive_true" in ids


def test_future_activation_requirements_must_be_inactive() -> None:
    b = _bundle(); b["future_activation_requirements"][0]["active"] = True
    assert "future_activation_requirements_inactive" in _verify(b)["violation_summary"]["violation_check_ids"]


def test_non_authority_posture_flags_present_and_true() -> None:
    report = _verify(_bundle())
    assert all(report["non_authority_posture"].values())
    b = _bundle(); b["non_authority_posture"] = {}
    assert "non_authority_posture_true" in _verify(b)["violation_summary"]["violation_check_ids"]


def test_supplied_memory_contract_validates_known_types_and_unknown_fails() -> None:
    contract = build_codex_workcell_memory_contract()
    assert _verify(_add_glow(_add_ledger(_bundle())), contract)["verification_status"] == "memory_candidate_bundle_verified"
    b = _add_glow(_add_ledger(_bundle(), would_be_record_type="strange"), would_be_archive_item_type="odd")
    ids = _verify(b, contract)["violation_summary"]["violation_check_ids"]
    assert "contract_record_types_known_when_contract_supplied" in ids
    assert "contract_glow_item_types_known_when_contract_supplied" in ids


def test_json_and_markdown_are_deterministic_and_escape_tables() -> None:
    b = _add_ledger(_bundle(), candidate_entry_id="pipe|newline\nentry")
    first = _verify(b); second = _verify(b)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    md1 = render_codex_workcell_memory_candidate_verifier_markdown(first)
    md2 = render_codex_workcell_memory_candidate_verifier_markdown(second)
    assert md1 == md2
    assert "pipe\\|newline<br>entry" in md1


def test_verifier_does_not_grant_authority_or_write_or_trigger() -> None:
    report = _verify(_bundle())
    assert report["not_ledger_writer"] is True
    assert report["not_glow_archiver"] is True
    assert report["not_memory_writer"] is True
    assert report["not_daemon_action"] is True
    assert report["not_task_creator"] is True
    assert report["not_scheduler"] is True
    assert report["non_authority_posture"]["memory_candidate_verifier_does_not_decide_readiness"] is True
    assert report["violation_summary"]["no_action_taken"] is True
