from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_pulse_contract import (
    CATEGORIES,
    SEVERITY_HINTS,
    CodexWorkcellPulseContractError,
    CodexWorkcellPulseContractRequest,
    build_codex_workcell_pulse_contract,
    render_codex_workcell_pulse_contract_markdown,
)

REQUIRED_SIGNAL_IDS = {
    "missing_architecture_map",
    "missing_matrix_evidence",
    "missing_finalizer_evidence",
    "missing_pr_metadata_guard_evidence",
    "missing_evidence_index",
    "missing_lifecycle_doctor",
    "missing_appendix_sidecar",
    "missing_doctrine_map",
    "matrix_required_failure_observed",
    "matrix_diagnostic_failure_observed",
    "finalizer_rerun_required_observed",
    "stale_evidence_refresh_observed",
    "generated_artifact_cleanup_incomplete_observed",
    "authority_status_absent",
    "provenance_absent",
    "doctrine_context_absent",
    "future_integration_unwired",
    "federation_consensus_absent",
    "daemon_repair_not_active",
    "pulse_watch_not_active",
}


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def test_required_signal_ids_categories_and_severities_are_present() -> None:
    contract = build_codex_workcell_pulse_contract()
    catalog = contract["signal_catalog"]
    ids = {item["signal_id"] for item in catalog}
    assert REQUIRED_SIGNAL_IDS <= ids
    assert {item["category"] for item in catalog} <= set(CATEGORIES)
    assert {item["severity_hint"] for item in catalog} <= set(SEVERITY_HINTS)


def test_indexes_are_internally_consistent() -> None:
    contract = build_codex_workcell_pulse_contract()
    by_id = {item["signal_id"]: item for item in contract["signal_catalog"]}
    for category, ids in contract["category_index"].items():
        assert category in CATEGORIES
        assert ids == sorted(ids)
        assert all(by_id[signal_id]["category"] == category for signal_id in ids)
    for severity, ids in contract["severity_index"].items():
        assert severity in SEVERITY_HINTS
        assert ids == sorted(ids)
        assert all(by_id[signal_id]["severity_hint"] == severity for signal_id in ids)


def test_non_authority_posture_and_future_requirements_are_bounded() -> None:
    contract = build_codex_workcell_pulse_contract()
    assert contract["not_runtime_authority"] is True
    assert contract["not_watcher"] is True
    assert contract["not_scheduler"] is True
    assert contract["not_daemon_action"] is True
    assert all(value is True for value in contract["non_authority_posture"].values())
    assert all(item["status"] == "future_only" and item["met"] is False and item["active"] is False for item in contract["future_activation_requirements"])


def test_no_signal_grants_readiness_daemon_or_schedule_authority() -> None:
    contract = build_codex_workcell_pulse_contract()
    forbidden = ("ready_to_commit", "ready_for_pr_metadata", "pr_metadata_guard_ready")
    for signal in contract["signal_catalog"]:
        text = json.dumps(signal, sort_keys=True).lower()
        assert all(term not in text for term in forbidden)
        assert "trigger daemon" in text
        assert "schedule tasks" in text
        assert "does not decide readiness" in text


def test_health_snapshot_omitted_summary_is_not_provided() -> None:
    summary = build_codex_workcell_pulse_contract()["health_snapshot_input_summary"]
    assert summary == {"provided": False, "path": None, "digest": None, "byte_size": None}


def test_health_snapshot_digest_size_and_observed_mapping(tmp_path: Path) -> None:
    snapshot = {
        "workcell_health_snapshot_id": "codex_workcell_health_snapshot.v1",
        "missing_inputs": ["architecture_json", "matrix_json", "beneficial_trait_doctrine_json"],
        "proof_summary": {"required_failure_count": 1, "diagnostic_failure_count": 1},
        "authority_summary": {"pre_commit_rerun_required": True, "pre_commit_terminal_refresh_status": "stale"},
        "doctrine_summary": {"provided": False},
        "provenance_summary": {"appendix_provenance_digest_version": None},
        "future_integration_snapshot": [{"integration": "pulse stale-evidence watch", "active_authority": False}, {"integration": "daemon repair recommendation", "active_authority": False}, {"integration": "federation drift consensus", "active_authority": False}],
        "observed_pressure_signals": [{"signal": "matrix_required_failures"}, {"signal": "unknown_pressure", "value": 7}],
    }
    path = _write_json(tmp_path / "snapshot.json", snapshot)
    raw = path.read_bytes()
    contract = build_codex_workcell_pulse_contract(CodexWorkcellPulseContractRequest(health_snapshot_json=str(path)))
    summary = contract["health_snapshot_input_summary"]
    assert summary["provided"] is True
    assert summary["digest"] == hashlib.sha256(raw).hexdigest()
    assert summary["byte_size"] == len(raw)
    assert summary["observed_pressure_signal_count"] == 2
    assert summary["missing_inputs_count"] == 3
    observed = contract["observed_signal_summary"]
    assert "missing_architecture_map" in observed["observed_signal_ids"]
    assert "matrix_required_failure_observed" in observed["observed_signal_ids"]
    assert "finalizer_rerun_required_observed" in observed["observed_signal_ids"]
    assert observed["unmatched_health_snapshot_pressure_signals"] == [{"signal": "unknown_pressure", "value": 7}]
    assert observed["missing_contract_signal_ids"] == []
    assert observed["observation_only"] is True


def test_invalid_and_missing_health_snapshot_fail_cleanly(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(CodexWorkcellPulseContractError, match="invalid_health_snapshot_json"):
        build_codex_workcell_pulse_contract(CodexWorkcellPulseContractRequest(health_snapshot_json=str(bad)))
    with pytest.raises(CodexWorkcellPulseContractError, match="missing_health_snapshot_json"):
        build_codex_workcell_pulse_contract(CodexWorkcellPulseContractRequest(health_snapshot_json=str(tmp_path / "missing.json")))


def test_json_and_markdown_are_deterministic_and_markdown_escapes_cells(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "snapshot.json", {"observed_pressure_signals": [{"signal": "weird|pipe\nnewline"}], "missing_inputs": []})
    req = CodexWorkcellPulseContractRequest(health_snapshot_json=str(path))
    first = build_codex_workcell_pulse_contract(req)
    second = build_codex_workcell_pulse_contract(req)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    md1 = render_codex_workcell_pulse_contract_markdown(first)
    md2 = render_codex_workcell_pulse_contract_markdown(first)
    assert md1 == md2
    assert md1.startswith("# Codex Workcell Pulse Contract")
    assert "weird\\|pipe<br>newline" in md1
