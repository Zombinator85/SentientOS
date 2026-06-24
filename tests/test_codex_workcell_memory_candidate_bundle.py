from __future__ import annotations

import hashlib
import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_memory_candidate_bundle import (
    INPUT_IDS,
    NON_AUTHORITY_POSTURE,
    CodexWorkcellMemoryCandidateBundleRequest,
    build_codex_workcell_memory_candidate_bundle,
    render_codex_workcell_memory_candidate_bundle_markdown,
)


def _write(tmp_path, name: str, data: dict) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def test_omitted_inputs_produce_no_candidates() -> None:
    bundle = build_codex_workcell_memory_candidate_bundle()
    assert all(not bundle["input_summaries"][key]["provided"] for key in INPUT_IDS)
    assert bundle["candidate_ledger_entries"] == []
    assert bundle["candidate_glow_items"] == []
    assert bundle["contract_summary"]["provided"] is False


def test_supplied_inputs_create_expected_candidate_records(tmp_path) -> None:
    paths = {
        "matrix_json": _write(tmp_path, "matrix.json", {"matrix_status": "passed", "commit_sha": "abc"}),
        "pre_commit_finalizer_json": _write(tmp_path, "pre.json", {"status": "ready_to_commit"}),
        "pr_metadata_guard_json": _write(tmp_path, "guard.json", {"pr_metadata_guard_status": "pr_metadata_guard_ready"}),
        "health_snapshot_json": _write(tmp_path, "health.json", {"workcell_health_snapshot_id": "health-1"}),
        "pulse_contract_json": _write(tmp_path, "pulse.json", {"pulse_contract_id": "pulse-1"}),
        "daemon_recommendation_contract_json": _write(tmp_path, "daemon.json", {"daemon_recommendation_contract_id": "daemon-1"}),
        "memory_contract_json": _write(tmp_path, "memory.json", {"workcell_memory_contract_id": "mem-1", "ledger_receipt_chain_contract": {"record_catalog": [{"record_type": "x"}]}, "glow_evidence_archive_contract": {"archive_catalog": [{"archive_item_type": "y"}]}, "source_artifact_alignment": [{}]}),
    }
    bundle = build_codex_workcell_memory_candidate_bundle(CodexWorkcellMemoryCandidateBundleRequest(**paths))
    assert bundle["candidate_chain_summary"]["candidate_ledger_entry_count"] == 7
    assert bundle["candidate_archive_summary"]["candidate_glow_item_count"] == 7
    types = {entry["would_be_record_type"] for entry in bundle["candidate_ledger_entries"]}
    assert {"matrix_receipt", "finalizer_receipt", "pr_metadata_guard_receipt", "health_snapshot_receipt", "pulse_contract_receipt", "daemon_recommendation_contract_receipt", "memory_contract_receipt"} <= types
    glow_types = {item["would_be_archive_item_type"] for item in bundle["candidate_glow_items"]}
    assert {"matrix_report_snapshot", "finalizer_report_snapshot", "pr_metadata_guard_snapshot", "workcell_health_snapshot", "pulse_contract_snapshot", "daemon_recommendation_contract_snapshot", "memory_contract_snapshot"} <= glow_types
    assert bundle["contract_summary"]["workcell_memory_contract_id"] == "mem-1"


def test_raw_digest_size_source_map_and_determinism(tmp_path) -> None:
    path = _write(tmp_path, "matrix.json", {"status": "ok|pipe", "artifact_id": "a\nb"})
    raw = (tmp_path / "matrix.json").read_bytes()
    req = CodexWorkcellMemoryCandidateBundleRequest(matrix_json=path)
    first = build_codex_workcell_memory_candidate_bundle(req)
    second = build_codex_workcell_memory_candidate_bundle(req)
    assert first == second
    summary = first["input_summaries"]["matrix_json"]
    assert summary["digest"] == hashlib.sha256(raw).hexdigest()
    assert summary["byte_size"] == len(raw)
    mapped = first["source_artifact_map"][0]
    assert mapped["input_id"] == "matrix_json"
    assert mapped["candidate_ledger_entry_ids"] == [first["candidate_ledger_entries"][0]["candidate_entry_id"]]
    assert mapped["candidate_glow_item_ids"] == [first["candidate_glow_items"][0]["candidate_glow_item_id"]]
    assert first["candidate_chain_summary"]["parent_links_missing_count"] == 1
    assert first["candidate_archive_summary"]["related_ledger_links_observed_count"] == 1
    md1 = render_codex_workcell_memory_candidate_bundle_markdown(first)
    md2 = render_codex_workcell_memory_candidate_bundle_markdown(second)
    assert md1 == md2
    assert "ok\\|pipe" in md1
    assert "a<br>b" in md1


def test_non_authority_future_mount_flags(tmp_path) -> None:
    bundle = build_codex_workcell_memory_candidate_bundle(CodexWorkcellMemoryCandidateBundleRequest(doctrine_map_json=_write(tmp_path, "doctrine.json", {"status": "context"})))
    assert bundle["candidate_ledger_entries"] == []
    assert bundle["candidate_glow_items"][0]["no_archive_performed"] is True
    assert bundle["not_ledger_writer"] is True
    assert bundle["not_glow_archiver"] is True
    assert bundle["not_daemon_action"] is True
    assert bundle["not_scheduler"] is True
    assert all(bundle["non_authority_posture"][key] is True for key in NON_AUTHORITY_POSTURE)
    assert all(item["status"] == "future_only" and item["active"] is False and item["met"] is False for item in bundle["future_activation_requirements"])
    assert bundle["sentientos_mount_alignment"]["/ledger"].endswith("no ledger write")
