from __future__ import annotations

import copy

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_policy_contract import build_codex_workcell_storage_policy_contract
from sentientos.codex_workcell_storage_transaction_plan import NON_AUTHORITY_POSTURE, build_codex_workcell_storage_transaction_plan, render_codex_workcell_storage_transaction_plan_markdown


def _policy() -> dict:
    return build_codex_workcell_storage_policy_contract()


def _verifier(status: str = "storage_policy_verified") -> dict:
    return {"verification_status": status}


def _candidate_verifier(status: str = "memory_candidate_bundle_verified") -> dict:
    return {"verification_status": status}


def _bundle() -> dict:
    return {
        "candidate_ledger_entries": [{"candidate_entry_id": "e1", "source_input_id": "matrix_json", "would_be_record_type": "matrix_receipt", "source_artifact_digest": "abc", "source_artifact_digest_algo": "sha256", "source_artifact_byte_size": 9, "parent_entry_id": "p1", "parent_entry_digest": "pd"}],
        "candidate_glow_items": [{"candidate_glow_item_id": "g1", "source_input_id": "matrix_json", "would_be_archive_item_type": "matrix_report_snapshot", "source_digest": "def", "source_digest_algo": "sha256", "byte_size": 8, "related_candidate_ledger_entry_id": "e1"}],
    }


def _plan(**overrides) -> dict:
    kwargs = {"storage_policy_contract": _policy(), "storage_policy_verifier": _verifier(), "memory_candidate_bundle": _bundle(), "memory_candidate_verifier": _candidate_verifier(), "vow_boundary_contract": {"canonical_vow_digest": "vow123"}, "vow_alignment_attestation": {"failed_attestation_count": 0, "warning_attestation_count": 0, "active_authority_detected": False}, "commit_sha": "abc123"}
    kwargs.update(overrides)
    return build_codex_workcell_storage_transaction_plan(**kwargs)


def test_minimal_valid_supplied_reports_produce_deterministic_dry_run_output() -> None:
    first = _plan()
    second = _plan()
    assert first == second
    assert first["storage_transaction_plan_id"] == "codex_workcell_storage_transaction_plan.v1"
    assert first["dry_run_only"] is True
    assert first["writes_performed"] is False
    assert first["archives_performed"] is False
    assert first["memory_mutation_performed"] is False


def test_ledger_candidate_entries_and_glow_items_become_transaction_plans() -> None:
    plan = _plan()
    assert plan["ledger_transaction_plan"][0]["source_candidate_entry_id"] == "e1"
    assert plan["ledger_transaction_plan"][0]["transaction_kind"] == "ledger_write_candidate"
    assert plan["glow_transaction_plan"][0]["source_candidate_glow_item_id"] == "g1"
    assert plan["glow_transaction_plan"][0]["related_planned_ledger_transaction_id"] == plan["ledger_transaction_plan"][0]["transaction_id"]


@pytest.mark.parametrize(("kwargs", "expected"), [({"commit_sha": "c1", "pr_number": "99", "canonical_vow_digest": "v1"}, "/ledger/codex/workcell/c1/matrix_receipt.json"), ({"commit_sha": None, "pr_number": "99", "canonical_vow_digest": "v1"}, "/ledger/codex/workcell/99/matrix_receipt.json"), ({"commit_sha": None, "pr_number": None, "canonical_vow_digest": "v1", "vow_boundary_contract": {}}, "/ledger/codex/workcell/v1/matrix_receipt.json")])
def test_planned_ledger_paths_prefer_commit_then_pr_then_vow(kwargs: dict, expected: str) -> None:
    assert _plan(**kwargs)["ledger_transaction_plan"][0]["planned_path"] == expected


@pytest.mark.parametrize(("kwargs", "expected"), [({"commit_sha": "c1", "pr_number": "99", "canonical_vow_digest": "v1"}, "/glow/codex/workcell/c1/matrix_report_snapshot.json"), ({"commit_sha": None, "pr_number": "99", "canonical_vow_digest": "v1"}, "/glow/codex/workcell/99/matrix_report_snapshot.json"), ({"commit_sha": None, "pr_number": None, "canonical_vow_digest": "v1", "vow_boundary_contract": {}}, "/glow/codex/workcell/v1/matrix_report_snapshot.json")])
def test_planned_glow_paths_prefer_commit_then_pr_then_vow(kwargs: dict, expected: str) -> None:
    assert _plan(**kwargs)["glow_transaction_plan"][0]["planned_path"] == expected


def test_missing_commit_pr_or_vow_digest_produces_blocking_path_gap() -> None:
    plan = _plan(commit_sha=None, pr_number=None, canonical_vow_digest=None, vow_boundary_contract={})
    assert plan["ledger_transaction_plan"][0]["planned_path"] is None
    assert "missing_commit_pr_or_vow_digest_for_path" in plan["transaction_gap_summary"]["blocking_gap_ids"]


def test_forbidden_host_network_temp_backdoor_paths_are_never_produced() -> None:
    policy = _policy()
    policy["ledger_storage_policy"]["allowed_path_patterns"] = ["/tmp/{commit_sha}/{record_type}.json", "https://evil/{record_type}", "/ledger/.backdoor/{record_type}.json"]
    plan = _plan(storage_policy_contract=policy)
    assert plan["ledger_transaction_plan"][0]["planned_path"] is None
    assert plan["transaction_path_validation"]["forbidden_path_detected"] is True


def test_source_digests_are_propagated_and_missing_source_digest_blocks() -> None:
    plan = _plan()
    assert plan["ledger_transaction_plan"][0]["source_artifact_digest"] == "abc"
    assert plan["glow_transaction_plan"][0]["source_digest"] == "def"
    bundle = _bundle()
    del bundle["candidate_ledger_entries"][0]["source_artifact_digest"]
    del bundle["candidate_glow_items"][0]["source_digest"]
    missing = _plan(memory_candidate_bundle=bundle)
    assert "missing_source_digest" in missing["transaction_gap_summary"]["blocking_gap_ids"]
    assert len(missing["transaction_digest_validation"]["missing_digest_transaction_ids"]) == 2


def test_parent_context_is_planned_but_not_written_and_missing_parent_blocks_active_write_only() -> None:
    bundle = _bundle()
    del bundle["candidate_ledger_entries"][0]["parent_entry_id"]
    plan = _plan(memory_candidate_bundle=bundle)
    assert plan["transaction_parent_chain_plan"]["no_parent_chain_written"] is True
    assert plan["transaction_parent_chain_plan"]["missing_parent_context_blocks_active_write"] is True
    assert "missing_parent_context" in plan["transaction_gap_summary"]["blocking_gap_ids"]
    assert plan["dry_run_only"] is True


def test_unverified_inputs_and_failed_vow_attestation_produce_blocking_gaps() -> None:
    plan = _plan(storage_policy_verifier=_verifier("storage_policy_failed"), memory_candidate_verifier=_candidate_verifier("failed"), vow_alignment_attestation={"failed_attestation_count": 1, "active_authority_detected": True})
    assert {"storage_policy_not_verified", "memory_candidate_bundle_not_verified", "vow_alignment_failed"} <= set(plan["transaction_gap_summary"]["blocking_gap_ids"])
    assert plan["transaction_vow_alignment"]["vow_alignment_blocks_active_write"] is True


def test_non_authority_posture_future_requirements_and_hygiene_are_present() -> None:
    plan = _plan()
    assert plan["transaction_gap_summary"]["active_storage_allowed_now"] is False
    assert plan["reviewer_hygiene_summary"]["bad_repo_url"] == "https://github.com/" + "OpenAI" + "/SentientOS.git"
    assert plan["reviewer_hygiene_summary"]["correct_repo_url"] == "https://github.com/Zombinator85/SentientOS.git"
    assert plan["non_authority_posture"] == NON_AUTHORITY_POSTURE
    assert all(plan["non_authority_posture"].values())
    assert all(item["active"] is False and item["met"] is False and item["status"] == "future_only" for item in plan["future_activation_requirements"])


def test_planner_does_not_grant_readiness_or_write_archive_modify_trigger_or_schedule() -> None:
    plan = _plan()
    assert "ready" not in plan
    assert plan["not_daemon_action"] is True
    assert plan["not_task_creator"] is True
    assert plan["not_scheduler"] is True
    assert plan["writes_performed"] is False
    assert plan["archives_performed"] is False
    assert plan["memory_mutation_performed"] is False


def test_markdown_output_is_deterministic_and_escapes_pipes_newlines() -> None:
    plan = _plan(pr_title="has | pipe\nand newline")
    first = render_codex_workcell_storage_transaction_plan_markdown(plan)
    second = render_codex_workcell_storage_transaction_plan_markdown(copy.deepcopy(plan))
    assert first == second
    assert "has \\| pipe<br>and newline" in first
    assert first.startswith("# Codex Workcell Storage Transaction Dry-Run Plan")
