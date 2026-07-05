from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_operator_consent_request_presentation_contract import INPUT_SPECS, build_codex_workcell_storage_operator_consent_request_presentation_contract, omitted_input as omitted_contract_input
from sentientos.codex_workcell_storage_operator_consent_request_presentation_verifier import OPTIONAL_INPUT_IDS, omitted_input, read_json_input, render_codex_workcell_storage_operator_consent_request_presentation_verifier_markdown, verify_codex_workcell_storage_operator_consent_request_presentation_contract


def _contract() -> dict[str, object]:
    return build_codex_workcell_storage_operator_consent_request_presentation_contract(input_summaries={k: omitted_contract_input(k) for k in INPUT_SPECS}, commit="abc", pr="9")


def _report(contract: dict[str, object] | None = None) -> dict[str, object]:
    return verify_codex_workcell_storage_operator_consent_request_presentation_contract(contract=contract or _contract(), contract_summary={"input_id": "presentation_contract_json", "provided": True, "path": "contract.json", "digest_algo": "sha256", "digest": "abc", "byte_size": 10, "readable_json": True, "error": None}, optional_reports={}, optional_summaries={k: omitted_input(k) for k in OPTIONAL_INPUT_IDS})


def test_verifier_accepts_landed_contract_shape_and_preserves_non_authority():
    report = _report()
    assert report["verification_status"] == "storage_operator_consent_request_presentation_contract_verified"
    assert report["violation_summary"]["violation_count"] == 0
    for key in ("metadata_only", "verifier_only", "presentation_not_performed", "request_not_presented", "ui_not_rendered", "message_not_sent", "external_delivery_not_performed", "response_artifact_not_created", "response_not_collected", "consent_not_collected", "consent_not_implied", "runtime_binding_not_performed"):
        assert report[key] is True
    for key in ("operator_consent_present", "active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed"):
        assert report[key] is False


def test_denied_inferences_gaps_hygiene_mounts_and_future_requirements():
    report = _report()
    assert report["denied_inference_results"]["passed"] is True
    assert "operator_silence_implies_consent" in report["denied_inference_results"]["denied_inference_ids"]
    assert report["missing_presentation_gap_results"]["passed"] is True
    assert "presentation_mechanism_missing" in report["missing_presentation_gap_results"]["gap_ids"]
    assert report["reviewer_hygiene_summary"]["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert report["reviewer_hygiene_summary"]["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    assert set(report["sentientos_mount_alignment"]) == {"/ledger", "/glow", "/vow", "/pulse", "/daemon"}
    assert all(row["future_only"] is True and row["met"] is False and row["active"] is False for row in report["future_activation_requirements"])


def test_verifier_reports_structure_failures_without_taking_action():
    contract = _contract()
    contract["message_not_sent"] = False
    contract["denied_inferences"] = []
    report = _report(contract)
    assert report["verification_status"] == "storage_operator_consent_request_presentation_contract_failed"
    assert "message_not_sent_true" in report["violation_summary"]["violation_check_ids"]
    assert "required_denied_inferences_denied" in report["violation_summary"]["violation_check_ids"]
    assert report["violation_summary"]["no_action_taken"] is True


def test_read_json_input_records_raw_digest_and_rejects_bad_json(tmp_path: Path):
    path = tmp_path / "contract.json"
    raw = json.dumps(_contract(), sort_keys=True).encode()
    path.write_bytes(raw)
    summary, loaded = read_json_input(str(path), "presentation_contract_json")
    assert loaded["metadata_only"] is True
    assert summary["digest"] == hashlib.sha256(raw).hexdigest()
    assert summary["byte_size"] == len(raw)
    markdown = render_codex_workcell_storage_operator_consent_request_presentation_verifier_markdown(_report())
    assert "Verification status" in markdown
    bad = tmp_path / "bad.json"
    bad.write_text("[]")
    with pytest.raises(ValueError):
        read_json_input(str(bad), "presentation_contract_json")
