from __future__ import annotations

import hashlib
import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_memory_activation_preflight import (
    NON_AUTHORITY_POSTURE,
    build_codex_workcell_memory_activation_preflight,
    render_codex_workcell_memory_activation_preflight_markdown,
)
from sentientos.codex_workcell_memory_candidate_verifier import verify_codex_workcell_memory_candidate_bundle
from sentientos.codex_workcell_memory_contract import build_codex_workcell_memory_contract
from tests.test_codex_workcell_memory_candidate_verifier import _add_glow, _add_ledger, _bundle, _summary


def _input_summary(name: str, data: dict) -> dict:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return {"provided": True, "path": f"{name}.json", "digest_algo": "sha256", "digest": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "readable_json": True, "error": None}


def _omitted() -> dict:
    return {"provided": False, "path": None, "digest": None, "byte_size": None, "readable_json": False, "error": None}


def _valid_inputs() -> tuple[dict, dict, dict]:
    contract = build_codex_workcell_memory_contract()
    bundle = _add_glow(_add_ledger(_bundle()))
    verifier = verify_codex_workcell_memory_candidate_bundle(bundle, _summary(bundle), contract, _input_summary("contract", contract))
    assert verifier["verification_status"] == "memory_candidate_bundle_verified"
    return contract, bundle, verifier


def _report(contract: dict | None = None, bundle: dict | None = None, verifier: dict | None = None) -> dict:
    return build_codex_workcell_memory_activation_preflight(
        contract, _input_summary("contract", contract) if contract else _omitted(),
        bundle, _input_summary("bundle", bundle) if bundle else _omitted(),
        verifier, _input_summary("verifier", verifier) if verifier else _omitted(),
    )


def test_omitted_inputs_produce_incomplete() -> None:
    report = _report()
    assert report["activation_preflight_status"] == "activation_prerequisites_incomplete"
    assert report["activation_not_performed"] is True


def test_valid_inputs_can_satisfy_future_design_while_writer_gaps_remain_visible() -> None:
    report = _report(*_valid_inputs())
    assert report["activation_preflight_status"] == "activation_prerequisites_satisfied_for_future_design"
    assert report["activation_gap_summary"]["future_writer_requirements_unmet"] is True
    for gap in ["operator_consent_not_present", "writer_implementation_not_present", "storage_policy_not_present", "federation_consensus_not_present", "vow_digest_boundary_not_present"]:
        result = next(item for item in report["activation_prerequisite_results"] if item["prerequisite_id"] == gap)
        assert result["severity"] == "blocking_gap"
        assert result["passed"] is False


def test_verifier_violations_produce_failed() -> None:
    contract, bundle, verifier = _valid_inputs()
    verifier["violation_summary"]["violation_count"] = 1
    report = _report(contract, bundle, verifier)
    assert report["activation_preflight_status"] == "activation_prerequisites_failed"


@pytest.mark.parametrize("missing", ["contract", "bundle", "verifier"])
def test_missing_required_artifact_is_incomplete(missing: str) -> None:
    contract, bundle, verifier = _valid_inputs()
    report = _report(None if missing == "contract" else contract, None if missing == "bundle" else bundle, None if missing == "verifier" else verifier)
    assert report["activation_preflight_status"] == "activation_prerequisites_incomplete"


def test_active_memory_is_never_performed_and_no_authority_flags_true() -> None:
    report = _report(*_valid_inputs())
    assert report["activation_not_performed"] is True
    assert report["not_ledger_writer"] is True
    assert report["not_glow_archiver"] is True
    assert report["not_daemon_action"] is True
    assert report["not_task_creator"] is True
    assert report["not_scheduler"] is True
    assert all(report["non_authority_posture"].get(key) is True for key in NON_AUTHORITY_POSTURE)
    assert report["non_authority_posture"]["memory_activation_preflight_does_not_decide_readiness"] is True


def test_future_requirements_are_future_only_inactive_unmet() -> None:
    report = _report(*_valid_inputs())
    assert all(item["status"] == "future_only" and item["active"] is False and item["met"] is False for item in report["future_activation_requirements"])


def test_input_summaries_record_digest_and_size() -> None:
    contract, bundle, verifier = _valid_inputs()
    report = _report(contract, bundle, verifier)
    summary = report["input_summaries"]["memory_contract_json"]
    raw = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    assert summary["digest"] == hashlib.sha256(raw).hexdigest()
    assert summary["byte_size"] == len(raw)


def test_json_and_markdown_are_deterministic_and_escape_cells() -> None:
    report = _report(*_valid_inputs())
    report["activation_prerequisite_results"][0]["observed_state"] = "a|b\nc"
    first_json = json.dumps(report, sort_keys=True)
    second_json = json.dumps(report, sort_keys=True)
    assert first_json == second_json
    first_md = render_codex_workcell_memory_activation_preflight_markdown(report)
    second_md = render_codex_workcell_memory_activation_preflight_markdown(report)
    assert first_md == second_md
    assert "a\\|b<br>c" in first_md


def test_preflight_does_not_grant_readiness_authority() -> None:
    report = _report(*_valid_inputs())
    assert "commit_readiness" not in report
    assert "pr_metadata_readiness" not in report
    assert report["non_authority_posture"]["memory_activation_preflight_does_not_authorize_commit"] is True
    assert report["non_authority_posture"]["memory_activation_preflight_does_not_authorize_pr_creation"] is True
