from __future__ import annotations

import hashlib
import json

import pytest

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_vow_alignment_attestation import (
    CONSTRAINT_MAP,
    FORBIDDEN_MAP,
    INPUT_IDS,
    NON_AUTHORITY_POSTURE,
    build_codex_workcell_vow_alignment_attestation,
    read_json_input,
    render_codex_workcell_vow_alignment_attestation_markdown,
)
from sentientos.codex_workcell_vow_boundary_contract import build_codex_workcell_vow_boundary_contract


def _vow():
    data = build_codex_workcell_vow_boundary_contract()
    raw = json.dumps(data, sort_keys=True).encode()
    return ({"provided": True, "digest": hashlib.sha256(raw).hexdigest(), "digest_algo": "sha256", "byte_size": len(raw)}, data)


def _summary(data: dict):
    raw = json.dumps(data, sort_keys=True).encode()
    return {"provided": True, "digest": hashlib.sha256(raw).hexdigest(), "digest_algo": "sha256", "byte_size": len(raw), "readable_json": True, "error": None}


def _report(**extra):
    data = {"metadata_only": True, "non_authority_posture": {"x": True}, "sample_report_id": "r1"}
    data.update(extra)
    return data


def _build(input_id: str, data: dict):
    return build_codex_workcell_vow_alignment_attestation(_vow(), {input_id: (_summary(data), data)})


def test_omitted_optional_reports_produce_no_records_and_no_readiness_authority():
    report = build_codex_workcell_vow_alignment_attestation(_vow(), {})
    assert report["attestation_records"] == []
    assert report["attestation_gap_summary"]["not_readiness_authority"] is True
    assert all(value is True for value in report["non_authority_posture"].values())
    assert all(item["status"] == "future_only" and item["active"] is False and item["met"] is False for item in report["future_activation_requirements"])


def test_supplied_vow_contract_digest_is_copied_into_attestations():
    report = _build("architecture_json", _report())
    assert report["attestation_records"][0]["canonical_vow_digest"] == _vow()[1]["canonical_vow_digest"]


def test_missing_vow_contract_digest_fails_record():
    summary, vow = _vow()
    vow = dict(vow)
    vow.pop("canonical_vow_digest")
    report = build_codex_workcell_vow_alignment_attestation((summary, vow), {"architecture_json": (_summary(_report()), _report())})
    assert report["attestation_records"][0]["alignment_status"] == "failed"
    assert "canonical_vow_digest_missing" in report["attestation_records"][0]["violations"]


def test_all_supported_inputs_receive_stable_constraints_and_forbidden_inferences():
    for input_id in INPUT_IDS:
        report = _build(input_id, _report())
        record = report["attestation_records"][0]
        assert record["applicable_constraint_ids"] == list(CONSTRAINT_MAP[input_id])
        assert record["applicable_forbidden_inference_ids"] == list(FORBIDDEN_MAP[input_id])
        assert record["alignment_status"] == "attested"


def test_metadata_only_false_and_false_posture_fail():
    assert _build("health_snapshot_json", _report(metadata_only=False))["attestation_records"][0]["alignment_status"] == "failed"
    assert _build("pulse_contract_json", _report(non_authority_posture={"x": False}))["attestation_records"][0]["alignment_status"] == "failed"


def test_active_authority_flags_fail():
    for key in ("active_writer", "active_daemon", "active_scheduler", "active_task_creator", "active_alerting", "active_federation_consensus", "commit_authority", "pr_authority", "finalizer_bypass", "pr_metadata_guard_bypass"):
        record = _build("daemon_recommendation_contract_json", _report(**{key: True}))["attestation_records"][0]
        assert record["alignment_status"] == "failed"
        assert record["active_authority_detected"] is True


def test_missing_metadata_only_and_posture_warn():
    record = _build("memory_contract_json", {"memory_contract_id": "m"})["attestation_records"][0]
    assert record["alignment_status"] == "warning"
    assert "metadata_only_missing" in record["warnings"]
    assert "non_authority_posture_missing" in record["warnings"]


def test_raw_byte_digest_and_size_recorded_for_supplied_input(tmp_path):
    path = tmp_path / "report.json"
    path.write_text('{"metadata_only":true,"non_authority_posture":{"x":true}}', encoding="utf-8")
    summary, data = read_json_input(str(path), "architecture_json")
    report = build_codex_workcell_vow_alignment_attestation(_vow(), {"architecture_json": (summary, data)})
    record = report["attestation_records"][0]
    assert record["source_digest"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert record["source_byte_size"] == len(path.read_bytes())


def test_markdown_is_deterministic_and_escapes_cells():
    data = _report(sample_report_id="pipe|newline\nvalue")
    report = _build("memory_candidate_bundle_json", data)
    one = render_codex_workcell_vow_alignment_attestation_markdown(report)
    two = render_codex_workcell_vow_alignment_attestation_markdown(report)
    assert one == two
    assert "pipe\\|newline<br>value" in one


def test_non_authority_flags_block_actions():
    report = build_codex_workcell_vow_alignment_attestation(_vow(), {})
    for key in ("vow_alignment_attestation_does_not_write_ledger", "vow_alignment_attestation_does_not_archive_glow", "vow_alignment_attestation_does_not_modify_memory", "vow_alignment_attestation_does_not_trigger_daemon", "vow_alignment_attestation_does_not_create_tasks", "vow_alignment_attestation_does_not_schedule_tasks"):
        assert report["non_authority_posture"][key] is True
    assert set(NON_AUTHORITY_POSTURE) == set(report["non_authority_posture"])
