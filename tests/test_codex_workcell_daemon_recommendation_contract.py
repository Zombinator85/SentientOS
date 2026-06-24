import hashlib
import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_daemon_recommendation_contract import (
    NON_AUTHORITY_POSTURE,
    RECOMMENDATION_TYPES,
    SEVERITY_FLOORS,
    CodexWorkcellDaemonRecommendationContractRequest,
    _cell,
    build_codex_workcell_daemon_recommendation_contract,
    render_codex_workcell_daemon_recommendation_contract_markdown,
)
from sentientos.codex_workcell_pulse_contract import _signal_catalog

REQUIRED_IDS = {
    "provide_architecture_evidence", "provide_matrix_evidence", "provide_finalizer_evidence",
    "provide_pr_metadata_guard_evidence", "provide_evidence_index", "provide_lifecycle_doctor",
    "provide_appendix_sidecar", "provide_doctrine_map", "inspect_required_matrix_failures",
    "inspect_diagnostic_nonproof_lanes", "inspect_finalizer_rerun_signal", "inspect_stale_evidence_refresh",
    "inspect_generated_artifact_cleanup", "preserve_unmatched_pressure_signal", "document_future_integration_gap",
    "preserve_daemon_inactive_boundary", "require_explicit_watcher_activation_contract",
    "require_explicit_scheduler_activation_contract", "require_explicit_daemon_action_contract",
    "require_federation_consensus_contract", "require_ledger_glow_storage_policy", "require_vow_digest_boundary_check",
}


def test_required_recommendations_indexes_and_known_types():
    contract = build_codex_workcell_daemon_recommendation_contract()
    catalog = contract["recommendation_catalog"]
    ids = {item["recommendation_id"] for item in catalog}
    assert REQUIRED_IDS <= ids
    known_signals = {item["signal_id"] for item in _signal_catalog()}
    for item in catalog:
        assert item["recommendation_type"] in RECOMMENDATION_TYPES
        assert item["severity_floor"] in SEVERITY_FLOORS
        assert set(item["source_signal_ids"]) <= known_signals
        assert "does not" in item["forbidden_action"].lower() or "must not" in item["forbidden_action"].lower()
        text = json.dumps(item).lower()
        assert "authorize commit" in text
        assert "trigger daemon action" in text
        assert "create tasks" in text
        assert "schedule" in text
        assert "send alerts" in text
    by_type = {kind: sorted(i["recommendation_id"] for i in catalog if i["recommendation_type"] == kind) for kind in RECOMMENDATION_TYPES}
    assert contract["recommendation_type_index"] == by_type
    source_index = {}
    for item in catalog:
        for signal in item["source_signal_ids"]:
            source_index.setdefault(signal, []).append(item["recommendation_id"])
    assert contract["source_signal_index"] == {k: sorted(v) for k, v in sorted(source_index.items())}


def test_non_authority_and_future_requirements_are_inactive():
    contract = build_codex_workcell_daemon_recommendation_contract()
    assert set(NON_AUTHORITY_POSTURE) <= set(contract["non_authority_posture"])
    assert all(contract["non_authority_posture"].values())
    assert all(item["status"] == "future_only" and item["met"] is False and item["active"] is False for item in contract["future_activation_requirements"])
    assert contract["not_runtime_authority"] is True
    assert contract["not_daemon_action"] is True
    assert contract["not_task_creator"] is True
    assert contract["not_scheduler"] is True
    assert contract["not_alerting_system"] is True


def test_omitted_inputs_have_false_summaries():
    contract = build_codex_workcell_daemon_recommendation_contract()
    for key in ("pulse_contract_input_summary", "health_snapshot_input_summary"):
        summary = contract[key]
        assert summary["provided"] is False
        assert summary["path"] is None
        assert summary["digest"] is None
        assert summary["byte_size"] is None
        assert summary["readable_json"] is False
        assert summary["error"] is None
    assert contract["observed_recommendation_summary"]["provided"] is False
    assert contract["observed_recommendation_summary"]["applicable_recommendation_ids"] == []


def test_supplied_inputs_digest_size_and_observed_mapping(tmp_path):
    pulse_raw = b'{"pulse_contract_id":"pulse","category_index":{"a":[]},"severity_index":{"b":[]},"observed_signal_summary":{"observed_signal_ids":["missing_matrix_evidence","unknown_signal"],"unmatched_health_snapshot_pressure_signals":["x"]}}'
    health_raw = b'{"workcell_health_snapshot_id":"health","observed_pressure_signals":["p"],"missing_inputs":["m"]}'
    pulse = tmp_path / "pulse.json"
    health = tmp_path / "health.json"
    pulse.write_bytes(pulse_raw)
    health.write_bytes(health_raw)
    contract = build_codex_workcell_daemon_recommendation_contract(CodexWorkcellDaemonRecommendationContractRequest(str(pulse), str(health)))
    assert contract["pulse_contract_input_summary"]["digest"] == hashlib.sha256(pulse_raw).hexdigest()
    assert contract["pulse_contract_input_summary"]["byte_size"] == len(pulse_raw)
    assert contract["pulse_contract_input_summary"]["observed_signal_count"] == 2
    assert contract["health_snapshot_input_summary"]["digest"] == hashlib.sha256(health_raw).hexdigest()
    assert contract["health_snapshot_input_summary"]["byte_size"] == len(health_raw)
    observed = contract["observed_recommendation_summary"]
    assert "provide_matrix_evidence" in observed["applicable_recommendation_ids"]
    assert observed["unmatched_observed_signal_ids"] == ["unknown_signal"]
    assert observed["recommendation_only"] is True
    assert observed["no_action_taken"] is True


def test_json_and_markdown_are_deterministic_and_escape_cells():
    first = build_codex_workcell_daemon_recommendation_contract()
    second = build_codex_workcell_daemon_recommendation_contract()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert render_codex_workcell_daemon_recommendation_contract_markdown(first) == render_codex_workcell_daemon_recommendation_contract_markdown(second)
    assert _cell("a|b\nc") == "a\\|b<br>c"
