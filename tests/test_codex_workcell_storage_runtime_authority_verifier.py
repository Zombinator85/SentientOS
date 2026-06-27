from __future__ import annotations

import copy
import hashlib
import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_runtime_authority_contract import INPUT_SPECS, build_codex_workcell_storage_runtime_authority_contract, omitted_input as contract_omitted
from sentientos.codex_workcell_storage_runtime_authority_verifier import (
    FUTURE_REQUIREMENT_NAMES,
    NON_AUTHORITY_POSTURE,
    OPTIONAL_INPUT_IDS,
    REQUIRED_BOUNDARY_IDS,
    REQUIRED_BLOCKING_GAP_IDS,
    WORKCELL_STORAGE_RUNTIME_AUTHORITY_VERIFIER_ID,
    omitted_input,
    read_json_input,
    render_codex_workcell_storage_runtime_authority_verifier_markdown,
    verify_codex_workcell_storage_runtime_authority_contract,
)


def _contract() -> dict[str, object]:
    return build_codex_workcell_storage_runtime_authority_contract(input_summaries={i: contract_omitted(i) for i in INPUT_SPECS})


def _summary(tmp_path, data):
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return read_json_input(str(path), "storage_runtime_authority_contract_json")


def _verify(data, tmp_path):
    summary, loaded = _summary(tmp_path, data)
    return verify_codex_workcell_storage_runtime_authority_contract(
        storage_runtime_authority_contract=loaded,
        storage_runtime_authority_contract_summary=summary,
        optional_reports={},
        optional_summaries={i: omitted_input(i) for i in OPTIONAL_INPUT_IDS},
    )


def _failed(data, tmp_path, check_id: str):
    report = _verify(data, tmp_path)
    assert report["verification_status"] == "storage_runtime_authority_contract_failed"
    assert check_id in {c["check_id"] for c in report["verification_checks"] if not c["passed"]}


def test_valid_runtime_authority_contract_verifies(tmp_path):
    report = _verify(_contract(), tmp_path)
    assert report["storage_runtime_authority_verifier_id"] == WORKCELL_STORAGE_RUNTIME_AUTHORITY_VERIFIER_ID
    assert report["verification_status"] == "storage_runtime_authority_contract_verified"
    assert report["boundary_catalog_results"]["passed"] is True
    assert report["finalizer_guard_binding_results"]["passed"] is True
    assert report["operator_consent_results"]["passed"] is True
    assert report["storage_enforcement_results"]["passed"] is True
    assert report["digest_parent_runtime_results"]["passed"] is True
    assert report["pulse_daemon_boundary_results"]["passed"] is True
    assert report["federation_boundary_results"]["passed"] is True
    assert report["runtime_activation_gap_results"]["passed"] is True


@pytest.mark.parametrize(("key", "value", "check"), [
    ("metadata_only", None, "runtime_authority_contract_declares_metadata_only"),
    ("runtime_authority_contract_only", False, "runtime_authority_contract_declares_contract_only"),
    ("runtime_binding_not_performed", False, "runtime_binding_not_performed_true"),
    ("active_storage_allowed_now", True, "active_storage_allowed_now_false"),
    ("execution_performed", True, "execution_performed_false"),
    ("writes_performed", True, "writes_performed_false"),
    ("archives_performed", True, "archives_performed_false"),
    ("memory_mutation_performed", True, "memory_mutation_performed_false"),
])
def test_top_level_boundary_flags_fail(tmp_path, key, value, check):
    data = _contract()
    if value is None:
        data.pop(key)
    else:
        data[key] = value
    _failed(data, tmp_path, check)


def test_boundary_catalog_failures(tmp_path):
    data = _contract(); data.pop("runtime_authority_boundary_catalog")
    _failed(data, tmp_path, "boundary_catalog_present")
    for field, value, check in (("boundary_id", "missing", "boundary_catalog_required_ids_present"), ("currently_bound", True, "boundaries_currently_bound_false"), ("future_only", False, "boundaries_future_only"), ("active", True, "boundaries_active_false")):
        data = _contract()
        if field == "boundary_id":
            data["runtime_authority_boundary_catalog"] = [b for b in data["runtime_authority_boundary_catalog"] if b["boundary_id"] != REQUIRED_BOUNDARY_IDS[0]]
        else:
            data["runtime_authority_boundary_catalog"][0][field] = value
        _failed(data, tmp_path, check)


def test_policy_sections_fail_when_authority_appears(tmp_path):
    cases = [
        ("finalizer_guard_binding_policy", "finalizer_ready_to_commit_is_not_runtime_write_authority", False, "finalizer_guard_readiness_not_runtime_authority"),
        ("finalizer_guard_binding_policy", "binding_not_performed", False, "finalizer_guard_binding_not_performed"),
        ("operator_consent_policy", "operator_consent_present", True, "operator_consent_absent"),
        ("storage_enforcement_policy", "active_ledger_writer_present", True, "active_writer_absent"),
        ("storage_enforcement_policy", "active_glow_archiver_present", True, "active_archiver_absent"),
        ("storage_enforcement_policy", "enforcement_not_performed", False, "storage_enforcement_not_performed"),
        ("digest_and_parent_runtime_policy", "digest_verification_runtime_present", True, "digest_runtime_absent"),
        ("digest_and_parent_runtime_policy", "parent_chain_runtime_present", True, "parent_chain_runtime_absent"),
        ("pulse_daemon_runtime_boundary", "pulse_watcher_contract_present", True, "pulse_watcher_contract_absent"),
        ("pulse_daemon_runtime_boundary", "daemon_action_contract_present", True, "daemon_action_contract_absent"),
        ("pulse_daemon_runtime_boundary", "daemon_self_authorization_forbidden", False, "daemon_self_authorization_forbidden"),
        ("federation_runtime_boundary", "federation_consensus_present", True, "federation_consensus_absent"),
    ]
    for section, key, value, check in cases:
        data = _contract(); data[section][key] = value
        _failed(data, tmp_path, check)


def test_operator_consent_scope_and_blocking_gap_failures(tmp_path):
    data = _contract(); data["operator_consent_policy"]["consent_must_be_scoped_to_mounts"] = ["/ledger"]
    report = _verify(data, tmp_path)
    assert "consent_scope_includes_ledger_glow" in report["operator_consent_results"]["violations"]
    data = _contract(); data["runtime_activation_gap_summary"]["blocking_gap_ids"] = [x for x in REQUIRED_BLOCKING_GAP_IDS if x != REQUIRED_BLOCKING_GAP_IDS[0]]
    _failed(data, tmp_path, "required_blocking_gap_ids_present")


def test_future_requirements_posture_inputs_hygiene_and_determinism(tmp_path):
    data = _contract(); report = _verify(data, tmp_path)
    assert {r["requirement"] for r in report["future_activation_requirements"]} == set(FUTURE_REQUIREMENT_NAMES)
    assert all(r["status"] == "future_only" and r["met"] is False and r["active"] is False for r in report["future_activation_requirements"])
    assert report["non_authority_posture"] == NON_AUTHORITY_POSTURE
    assert all(report["non_authority_posture"].values())
    assert all(not report[k] for k in ("active_storage_allowed_now", "execution_performed", "writes_performed", "archives_performed", "memory_mutation_performed"))
    assert report["runtime_binding_not_performed"] is True
    assert report["reviewer_hygiene_summary"]["bad_repo_url"] == "https://github.com/" + "OpenAI/" + "SentientOS.git"
    assert report["reviewer_hygiene_summary"]["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    for input_id in OPTIONAL_INPUT_IDS:
        assert report["input_summaries"][input_id]["provided"] is False
    raw_path = tmp_path / "raw.json"; raw = b'{"pipe":"a|b","line":"x\\ny"}\n'; raw_path.write_bytes(raw)
    summary, loaded = read_json_input(str(raw_path), "storage_policy_contract_json")
    assert summary["digest"] == hashlib.sha256(raw).hexdigest(); assert summary["byte_size"] == len(raw); assert loaded["pipe"] == "a|b"
    assert json.dumps(report, sort_keys=True, indent=2) == json.dumps(_verify(data, tmp_path), sort_keys=True, indent=2)
    report["runtime_authority_contract_summary"]["storage_runtime_authority_contract_id"] = "pipe | newline\nvalue"
    md1 = render_codex_workcell_storage_runtime_authority_verifier_markdown(report); md2 = render_codex_workcell_storage_runtime_authority_verifier_markdown(report)
    assert md1 == md2 and "pipe \\| newline<br>value" in md1


def test_missing_contract_posture_fails(tmp_path):
    data = _contract(); data["non_authority_posture"] = {"x": True, "y": False}
    _failed(data, tmp_path, "non_authority_posture_true")
    data = _contract(); data["future_activation_requirements"][0]["active"] = True
    _failed(data, tmp_path, "future_activation_requirements_inactive")
