from __future__ import annotations

import copy
import hashlib
import json

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_policy_contract import build_codex_workcell_storage_policy_contract
from sentientos.codex_workcell_storage_transaction_plan import build_codex_workcell_storage_transaction_plan
from sentientos.codex_workcell_storage_transaction_plan_verifier import NON_AUTHORITY_POSTURE, render_codex_workcell_storage_transaction_plan_verifier_markdown, verify_codex_workcell_storage_transaction_plan


def _plan() -> dict:
    return build_codex_workcell_storage_transaction_plan(
        storage_policy_contract=build_codex_workcell_storage_policy_contract(),
        storage_policy_verifier={"verification_status": "storage_policy_verified"},
        memory_candidate_bundle={"candidate_ledger_entries": [{"candidate_entry_id": "e1", "source_input_id": "matrix_json", "would_be_record_type": "matrix_receipt", "source_artifact_digest": "abc", "parent_entry_id": "p1", "parent_entry_digest": "pd"}], "candidate_glow_items": [{"candidate_glow_item_id": "g1", "source_input_id": "matrix_json", "would_be_archive_item_type": "matrix_report_snapshot", "source_digest": "def", "related_candidate_ledger_entry_id": "e1"}]},
        memory_candidate_verifier={"verification_status": "memory_candidate_bundle_verified"},
        vow_boundary_contract={"canonical_vow_digest": "vow"},
        vow_alignment_attestation={"failed_attestation_count": 0, "warning_attestation_count": 0, "active_authority_detected": False},
        commit_sha="abc123",
    )


def _summary(data: dict) -> dict:
    raw = json.dumps(data, sort_keys=True).encode()
    return {"input_id": "storage_transaction_plan", "provided": True, "path": "plan.json", "digest_algo": "sha256", "digest": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "readable_json": True, "error": None}


def _verify(plan: dict) -> dict:
    return verify_codex_workcell_storage_transaction_plan(storage_transaction_plan=plan, storage_transaction_plan_summary=_summary(plan))


def _check(report: dict, check_id: str) -> dict:
    return next(c for c in report["verification_checks"] if c["check_id"] == check_id)


def test_valid_transaction_plan_verifies_and_has_required_shape() -> None:
    report = _verify(_plan())
    assert report["verification_status"] == "storage_transaction_plan_verified"
    for key in ("input_summaries", "transaction_plan_summary", "optional_context_summary", "ledger_transaction_results", "glow_transaction_results", "path_validation_results", "digest_validation_results", "parent_chain_results", "vow_alignment_results", "transaction_gap_results", "reviewer_hygiene_summary", "violation_summary", "sentientos_mount_alignment", "future_activation_requirements", "non_authority_posture"):
        assert key in report
    assert report["ledger_transaction_results"][0]["passed"] is True
    assert report["glow_transaction_results"][0]["passed"] is True


@pytest.mark.parametrize(("field", "value", "check_id"), [("metadata_only", None, "transaction_plan_declares_metadata_only"), ("dry_run_only", False, "transaction_plan_declares_dry_run_only"), ("transaction_plan_only", False, "transaction_plan_declares_transaction_plan_only"), ("writes_performed", True, "transaction_plan_declares_no_writes_performed"), ("archives_performed", True, "transaction_plan_declares_no_archives_performed"), ("memory_mutation_performed", True, "transaction_plan_declares_no_memory_mutation")])
def test_top_level_posture_failures_fail(field: str, value: object, check_id: str) -> None:
    plan = _plan()
    if value is None:
        plan.pop(field)
    else:
        plan[field] = value
    report = _verify(plan)
    assert report["verification_status"] == "storage_transaction_plan_failed"
    assert _check(report, check_id)["passed"] is False


def test_ledger_write_and_glow_archive_performed_fail() -> None:
    plan = _plan()
    plan["ledger_transaction_plan"][0]["write_performed"] = True
    plan["glow_transaction_plan"][0]["archive_performed"] = True
    report = _verify(plan)
    assert report["ledger_transaction_results"][0]["passed"] is False
    assert report["glow_transaction_results"][0]["passed"] is False


@pytest.mark.parametrize(("kind", "path"), [("ledger", "/glow/wrong.json"), ("glow", "/ledger/wrong.json")])
def test_transactions_outside_mount_fail(kind: str, path: str) -> None:
    plan = _plan()
    key = "ledger_transaction_plan" if kind == "ledger" else "glow_transaction_plan"
    plan[key][0]["planned_path"] = path
    report = _verify(plan)
    assert report[f"{kind}_transaction_results"][0]["passed"] is False
    assert report["path_validation_results"]["passed"] is False


@pytest.mark.parametrize("path", ["/tmp/x.json", "/etc/passwd", "https://example.test/x", "../escape", "/ledger/backdoor/x.json"])
def test_host_network_temp_backdoor_paths_fail(path: str) -> None:
    plan = _plan()
    plan["ledger_transaction_plan"][0]["planned_path"] = path
    report = _verify(plan)
    assert report["path_validation_results"]["passed"] is False
    assert report["path_validation_results"]["forbidden_path_detected"] is True


def test_missing_source_digest_and_missing_canonical_vow_digest_fail() -> None:
    plan = _plan()
    plan["ledger_transaction_plan"][0]["source_artifact_digest"] = None
    plan["glow_transaction_plan"][0]["canonical_vow_digest"] = None
    plan["ledger_transaction_plan"][0]["canonical_vow_digest"] = None
    report = _verify(plan)
    assert report["digest_validation_results"]["passed"] is False
    assert "missing_source_digest" in report["digest_validation_results"]["violations"]
    assert "missing_canonical_vow_digest" in report["digest_validation_results"]["violations"]


def test_parent_chain_gaps_are_recorded_and_do_not_write_parent_chain() -> None:
    plan = _plan()
    plan["ledger_transaction_plan"][0]["parent_entry_id"] = None
    report = _verify(plan)
    assert report["parent_chain_results"]["transactions_missing_parent_context"]
    assert report["parent_chain_results"]["no_parent_chain_written"] is True
    assert report["parent_chain_results"]["missing_parent_context_blocks_active_write"] is True


def test_active_storage_allowed_now_true_fails() -> None:
    plan = _plan()
    plan["transaction_gap_summary"]["active_storage_allowed_now"] = True
    report = _verify(plan)
    assert report["verification_status"] == "storage_transaction_plan_failed"
    assert _check(report, "active_storage_allowed_now_false")["passed"] is False


def test_non_authority_future_requirements_hygiene_and_no_readiness_authority() -> None:
    report = _verify(_plan())
    assert report["non_authority_posture"] == NON_AUTHORITY_POSTURE
    assert all(report["non_authority_posture"].values())
    assert all(x["status"] == "future_only" and x["active"] is False and x["met"] is False for x in report["future_activation_requirements"])
    assert report["reviewer_hygiene_summary"]["bad_repo_url"] == "https://github.com/" + "OpenAI" + "/SentientOS.git"
    assert report["reviewer_hygiene_summary"]["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert "ready" not in report
    assert report["not_ledger_writer"] is True and report["not_glow_archiver"] is True and report["not_daemon_action"] is True and report["not_task_creator"] is True and report["not_scheduler"] is True


def test_input_summaries_and_omitted_optional_context() -> None:
    plan = _plan()
    report = _verify(plan)
    assert report["input_summaries"]["storage_transaction_plan"]["digest"] == _summary(plan)["digest"]
    assert report["input_summaries"]["storage_transaction_plan"]["byte_size"] == _summary(plan)["byte_size"]
    assert report["input_summaries"]["storage_policy_contract"]["provided"] is False
    assert report["optional_context_summary"][0]["provided"] is False


def test_json_and_markdown_are_deterministic_and_escape_cells() -> None:
    plan = _plan()
    plan["ledger_transaction_plan"][0]["planned_path"] = "/ledger/pipe|and\nnewline.json"
    first = _verify(plan)
    second = _verify(copy.deepcopy(plan))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    md1 = render_codex_workcell_storage_transaction_plan_verifier_markdown(first)
    md2 = render_codex_workcell_storage_transaction_plan_verifier_markdown(second)
    assert md1 == md2
    assert "pipe\\|and<br>newline" in md1
    assert md1.startswith("# Codex Workcell Storage Transaction Plan Verifier")
