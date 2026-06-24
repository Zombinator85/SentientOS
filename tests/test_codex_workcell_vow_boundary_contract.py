from __future__ import annotations

import hashlib
import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_vow_boundary_contract import (
    INPUT_IDS,
    NON_AUTHORITY_POSTURE,
    build_codex_workcell_vow_boundary_contract,
    canonical_vow_constraints,
    compute_canonical_vow_digest,
    forbidden_inference_catalog,
    render_codex_workcell_vow_boundary_contract_markdown,
)

REQUIRED_CONSTRAINT_IDS = {
    "finalizer_authority_only_for_commit_readiness", "pr_metadata_guard_authority_only_for_pr_metadata", "reports_do_not_create_runtime_authority", "recommendations_are_not_commands", "pulse_signals_are_not_actions", "health_snapshots_are_not_decisions", "memory_candidates_are_not_writes", "memory_verification_is_not_readiness", "activation_preflight_is_not_activation", "ledger_schema_is_not_ledger_write", "glow_schema_is_not_glow_archive", "evidence_indexes_are_not_authority", "appendices_are_review_context_only", "doctrine_maps_do_not_train_models", "provenance_digests_do_not_verify_authority", "future_integrations_are_inactive_without_explicit_contract", "daemon_must_not_self_authorize", "federation_consensus_not_implied", "no_skipped_or_nonexecuted_tests_as_required_proof", "no_runtime_or_host_action_without_explicit_boundary", "no_backdoor_or_hidden_authority", "operator_consent_required_for_active_watchers_or_daemons", "storage_policy_required_for_memory_writes", "vow_digest_required_for_future_active_writers",
}
REQUIRED_INFERENCE_IDS = {
    "architecture_map_implies_runtime_authority", "health_snapshot_implies_readiness", "pulse_contract_implies_action", "daemon_recommendation_implies_command", "memory_contract_implies_storage_write", "memory_candidate_bundle_implies_ledger_write", "memory_candidate_bundle_implies_glow_archive", "memory_candidate_verifier_implies_readiness", "memory_activation_preflight_implies_activation", "matrix_diagnostic_nonproof_implies_required_proof", "evidence_index_implies_authority", "appendix_implies_authority", "doctrine_map_implies_model_training", "provenance_digest_implies_trust_without_source", "future_integration_implies_active_behavior",
}

def _summary(raw: bytes, path: str = "x.json") -> dict[str, object]:
    return {"provided": True, "path": path, "digest_algo": "sha256", "digest": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "readable_json": True, "error": None}

def test_canonical_constraint_ids_are_present() -> None:
    assert REQUIRED_CONSTRAINT_IDS <= {item["constraint_id"] for item in canonical_vow_constraints()}

def test_canonical_vow_digest_is_deterministic_and_changes_with_constraints() -> None:
    first = compute_canonical_vow_digest()
    assert first == compute_canonical_vow_digest(list(reversed(canonical_vow_constraints())))
    changed = [dict(item) for item in canonical_vow_constraints()]
    changed[0]["canonical_statement"] += " changed"
    assert compute_canonical_vow_digest(changed) != first

def test_canonical_vow_digest_independent_of_inputs() -> None:
    raw1 = b'{"metadata_only":true,"non_authority_posture":{"x":true}}'
    raw2 = b'{"metadata_only":true,"non_authority_posture":{"x":true},"extra":"changed"}'
    report1 = build_codex_workcell_vow_boundary_contract({"health_snapshot_json": (_summary(raw1, "a.json"), json.loads(raw1))})
    report2 = build_codex_workcell_vow_boundary_contract({"health_snapshot_json": (_summary(raw2, "b.json"), json.loads(raw2))})
    assert report1["canonical_vow_digest"] == report2["canonical_vow_digest"] == compute_canonical_vow_digest()

def test_forbidden_inference_catalog_contains_required_ids() -> None:
    assert REQUIRED_INFERENCE_IDS <= {item["inference_id"] for item in forbidden_inference_catalog()}

def test_omitted_inputs_are_not_supplied() -> None:
    report = build_codex_workcell_vow_boundary_contract()
    assert {item["alignment_status"] for item in report["report_alignment_results"]} == {"not_supplied"}
    assert report["vow_gap_summary"]["not_supplied_report_count"] == len(INPUT_IDS)

def test_supplied_metadata_only_non_authority_report_aligns_and_records_digest() -> None:
    data = {"metadata_only": True, "non_authority_posture": {"safe": True}, "health_snapshot_id": "h"}
    raw = json.dumps(data, sort_keys=True).encode()
    report = build_codex_workcell_vow_boundary_contract({"health_snapshot_json": (_summary(raw, "pipe|newline\nvalue.json"), data)})
    result = next(item for item in report["report_alignment_results"] if item["input_id"] == "health_snapshot_json")
    assert result["alignment_status"] == "aligned"
    assert result["source_digest"] == hashlib.sha256(raw).hexdigest()
    assert result["source_byte_size"] == len(raw)

def test_supplied_report_lacking_metadata_only_warns() -> None:
    data = {"non_authority_posture": {"safe": True}}
    raw = json.dumps(data).encode()
    result = next(item for item in build_codex_workcell_vow_boundary_contract({"pulse_contract_json": (_summary(raw), data)})["report_alignment_results"] if item["input_id"] == "pulse_contract_json")
    assert result["alignment_status"] == "warning"

def test_false_non_authority_posture_fails_alignment() -> None:
    data = {"metadata_only": True, "non_authority_posture": {"safe": False}}
    raw = json.dumps(data).encode()
    report = build_codex_workcell_vow_boundary_contract({"memory_contract_json": (_summary(raw), data)})
    assert report["vow_gap_summary"]["failed_report_count"] == 1
    assert report["vow_gap_summary"]["active_authority_detected"] is True

def test_active_writer_daemon_or_scheduler_authority_fails_alignment() -> None:
    for flag in ("active_writer", "daemon_action", "scheduler"):
        data = {"metadata_only": True, "non_authority_posture": {"safe": True}, flag: True}
        raw = json.dumps(data).encode()
        report = build_codex_workcell_vow_boundary_contract({"daemon_recommendation_contract_json": (_summary(raw), data)})
        assert next(item for item in report["report_alignment_results"] if item["provided"])["alignment_status"] == "failed"

def test_json_and_markdown_are_deterministic_and_escape_cells() -> None:
    data = {"metadata_only": True, "non_authority_posture": {"safe": True}, "note": "pipe | newline\nvalue"}
    raw = json.dumps(data).encode()
    report = build_codex_workcell_vow_boundary_contract({"architecture_json": (_summary(raw, "pipe|newline\nvalue.json"), data)})
    assert json.dumps(report, sort_keys=True) == json.dumps(build_codex_workcell_vow_boundary_contract({"architecture_json": (_summary(raw, "pipe|newline\nvalue.json"), data)}), sort_keys=True)
    md1 = render_codex_workcell_vow_boundary_contract_markdown(report)
    md2 = render_codex_workcell_vow_boundary_contract_markdown(report)
    assert md1 == md2
    assert "\\|" in render_codex_workcell_vow_boundary_contract_markdown({**report, "vow_gap_summary": {"x": "a|b\nc"}})
    assert "<br>" in render_codex_workcell_vow_boundary_contract_markdown({**report, "vow_gap_summary": {"x": "a|b\nc"}})

def test_contract_does_not_grant_authority_or_write_memory() -> None:
    report = build_codex_workcell_vow_boundary_contract()
    for key in ("not_runtime_authority", "not_memory_writer", "not_ledger_writer", "not_glow_archiver", "not_daemon_action", "not_task_creator", "not_scheduler"):
        assert report[key] is True
    assert all(NON_AUTHORITY_POSTURE.values())
    assert all(report["non_authority_posture"].values())
    assert "ready" not in report

def test_future_activation_requirements_are_future_only_inactive() -> None:
    report = build_codex_workcell_vow_boundary_contract()
    assert report["future_activation_requirements"]
    assert all(item["status"] == "future_only" and item["met"] is False and item["active"] is False for item in report["future_activation_requirements"])
