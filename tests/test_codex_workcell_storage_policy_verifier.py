from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_legacy_skip

import hashlib
import json

from sentientos.codex_workcell_storage_policy_contract import build_codex_workcell_storage_policy_contract
from sentientos.codex_workcell_storage_policy_verifier import (
    NON_AUTHORITY_POSTURE,
    render_codex_workcell_storage_policy_verifier_markdown,
    verify_codex_workcell_storage_policy_contract,
)


def _report(contract=None, raw=b'{"ok":true}'):
    c = build_codex_workcell_storage_policy_contract() if contract is None else contract
    summary = {"provided": True, "path": "policy.json", "digest_algo": "sha256", "digest": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "readable_json": True, "error": None}
    return verify_codex_workcell_storage_policy_contract(c, summary)


def _mutate(**changes):
    c = build_codex_workcell_storage_policy_contract()
    for path, value in changes.items():
        target = c
        bits = path.split(".")
        for bit in bits[:-1]:
            target = target[bit]
        if value == "__delete__":
            target.pop(bits[-1], None)
        else:
            target[bits[-1]] = value
    return c


def _failed_ids(report):
    return set(report["violation_summary"]["violation_check_ids"])


def test_valid_storage_policy_contract_verifies_and_is_non_authority():
    report = _report()
    assert report["verification_status"] == "storage_policy_verified"
    assert report["violation_summary"]["violation_count"] == 0
    assert report["not_ledger_writer"] is True
    assert report["not_glow_archiver"] is True
    assert report["not_daemon_action"] is True
    assert report["non_authority_posture"] == dict(sorted(NON_AUTHORITY_POSTURE.items()))
    assert all(report["non_authority_posture"].values())


def test_missing_metadata_only_fails():
    report = _report(_mutate(metadata_only="__delete__"))
    assert "storage_policy_declares_metadata_only" in _failed_ids(report)


def test_policy_only_false_fails():
    report = _report(_mutate(storage_policy_contract_only=False))
    assert "storage_policy_declares_policy_only" in _failed_ids(report)


def test_active_storage_allowed_now_true_fails():
    report = _report(_mutate(storage_activation_gap_summary={"active_storage_allowed_now": True, "ledger_write_performed": False, "glow_archive_performed": False, "memory_mutation_performed": False}))
    assert "storage_policy_declares_active_storage_not_allowed_now" in _failed_ids(report)
    assert "activation_gap_summary_blocks_active_storage" in _failed_ids(report)


def test_ledger_policy_missing_fails():
    report = _report(_mutate(ledger_storage_policy="__delete__"))
    assert report["ledger_policy_results"]["present"] is False
    assert "ledger_policy_present" in _failed_ids(report)


def test_glow_policy_missing_fails():
    report = _report(_mutate(glow_storage_policy="__delete__"))
    assert report["glow_policy_results"]["present"] is False
    assert "glow_policy_present" in _failed_ids(report)


def test_missing_required_ledger_record_types_fail():
    c = build_codex_workcell_storage_policy_contract()
    c["ledger_storage_policy"]["allowed_record_types"] = []
    report = _report(c)
    assert report["ledger_policy_results"]["missing_record_types"]
    assert "ledger_policy_has_allowed_record_types" in _failed_ids(report)


def test_missing_required_glow_archive_item_types_fail():
    c = build_codex_workcell_storage_policy_contract()
    c["glow_storage_policy"]["allowed_archive_item_types"] = []
    report = _report(c)
    assert report["glow_policy_results"]["missing_archive_item_types"]
    assert "glow_policy_has_allowed_archive_item_types" in _failed_ids(report)


def test_missing_digest_parent_retention_and_path_policy_ids_fail():
    c = build_codex_workcell_storage_policy_contract()
    c["digest_verification_policy"] = []
    c["parent_chain_validation_policy"] = []
    c["retention_policy"] = []
    c["path_scope_policy"] = []
    report = _report(c)
    assert report["digest_policy_results"]["missing_digest_policy_ids"]
    assert report["parent_chain_policy_results"]["missing_parent_chain_policy_ids"]
    assert report["retention_policy_results"]["missing_retention_policy_ids"]
    assert report["path_scope_policy_results"]["missing_path_scope_policy_ids"]
    assert {"digest_policy_present", "parent_chain_policy_present", "retention_policy_present", "path_scope_policy_present"} <= _failed_ids(report)


def test_ledger_write_and_glow_archive_performed_false_required():
    c = build_codex_workcell_storage_policy_contract()
    c["ledger_storage_policy"]["write_not_performed"] = False
    c["glow_storage_policy"]["archive_not_performed"] = False
    report = _report(c)
    assert "ledger_policy_declares_write_not_performed" in _failed_ids(report)
    assert "glow_policy_declares_archive_not_performed" in _failed_ids(report)


def test_activation_gap_summary_must_keep_no_active_effects():
    c = build_codex_workcell_storage_policy_contract()
    c["storage_activation_gap_summary"]["ledger_write_performed"] = True
    report = _report(c)
    assert report["activation_gap_results"]["passed"] is False
    assert "activation_gap_summary_blocks_active_storage" in _failed_ids(report)


def test_future_activation_requirements_are_future_only_inactive():
    report = _report()
    assert all(item == {"requirement": item["requirement"], "status": "future_only", "met": False, "active": False} for item in report["future_activation_requirements"])


def test_input_summaries_digest_byte_size_and_omitted_optional_context():
    raw = b'{"storage_policy_contract_id":"x"}'
    report = _report(raw=raw)
    summary = report["input_summaries"]["storage_policy_contract_json"]
    assert summary["digest"] == hashlib.sha256(raw).hexdigest()
    assert summary["byte_size"] == len(raw)
    assert report["input_summaries"]["vow_boundary_contract_json"]["provided"] is False
    assert report["optional_context_summary"]["vow_boundary_contract_json"]["context_only"] is True


def test_reviewer_hygiene_summary_contains_bad_and_correct_urls():
    hygiene = _report()["reviewer_hygiene_summary"]
    assert hygiene["bad_repo_url"] == "https://github.com/" + "OpenAI" + "/SentientOS.git"
    assert hygiene["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"


def test_json_and_markdown_are_deterministic_and_escape_cells():
    report = _report()
    assert json.dumps(report, sort_keys=True) == json.dumps(_report(), sort_keys=True)
    report["reviewer_hygiene_summary"]["pipe"] = "a|b\nc"
    md1 = render_codex_workcell_storage_policy_verifier_markdown(report)
    md2 = render_codex_workcell_storage_policy_verifier_markdown(report)
    assert md1 == md2
    assert "a\\|b<br>c" in md1


def test_verifier_does_not_grant_readiness_or_runtime_authority():
    report = _report()
    assert report["verification_status"] == "storage_policy_verified"
    assert report["not_runtime_authority"] is True
    assert report["non_authority_posture"]["storage_policy_verifier_does_not_decide_readiness"] is True
    assert report["non_authority_posture"]["storage_policy_verifier_does_not_authorize_commit"] is True
    assert report["non_authority_posture"]["storage_policy_verifier_does_not_authorize_pr_creation"] is True
    assert report["non_authority_posture"]["storage_policy_verifier_does_not_create_tasks"] is True
    assert report["non_authority_posture"]["storage_policy_verifier_does_not_schedule_tasks"] is True
