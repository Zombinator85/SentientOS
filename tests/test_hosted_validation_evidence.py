from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.hosted_validation_evidence import (
    REQUIRED_STAGES,
    SCHEMA_VERSION,
    WORKFLOW_FILE,
    verify_hosted_validation_evidence,
)
from sentientos.landing_validation_plan import (
    seal_validation_plan,
    verify_validation_plan,
    verify_validation_plan_transition,
)
from sentientos.codex_pr_metadata_guard import CodexPrMetadataGuardRequest, evaluate_pr_metadata_guard

pytestmark = pytest.mark.no_legacy_skip

BASE_SHA = "a" * 40
CANDIDATE_SHA = "b" * 40
CANDIDATE_TREE = "d" * 40
TITLE = "[codex:developer] bridge cloud landing to hosted validation"
REPOSITORY = "Zombinator85/SentientOS"


def _evidence() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": REPOSITORY,
        "workflow_file": WORKFLOW_FILE,
        "run_id": 123456,
        "run_attempt": 1,
        "event": "pull_request",
        "ref": "refs/pull/1/merge",
        "head_sha": CANDIDATE_SHA,
        "head_tree": CANDIDATE_TREE,
        "status": "completed",
        "conclusion": "success",
        "stages": {stage: {"status": "passed", "exit_code": 0} for stage in REQUIRED_STAGES},
    }


def test_exact_completed_hosted_success_is_bound_to_candidate() -> None:
    proof = verify_hosted_validation_evidence(
        _evidence(), expected_sha=CANDIDATE_SHA, expected_tree=CANDIDATE_TREE, expected_repository=REPOSITORY,
    )
    assert proof["status"] == "hosted_validation_evidence_ready"
    assert set(proof["verified_stage_ids"]) == set(REQUIRED_STAGES)


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        (lambda item: item.update(head_sha=BASE_SHA), "hosted_validation_candidate_sha_mismatch"),
        (lambda item: item.update(head_tree=BASE_SHA), "hosted_validation_candidate_tree_mismatch"),
        (lambda item: item.update(status="in_progress"), "hosted_validation_incomplete"),
        (lambda item: item.update(conclusion="failure"), "hosted_validation_not_successful"),
        (lambda item: item["stages"].update(audit_immutability={"status": "skipped"}), "hosted_validation_stage_not_passed:audit_immutability"),
        (lambda item: item["stages"].update(strict_audits={"status": "passed", "exit_code": 1}), "hosted_validation_stage_not_passed:strict_audits"),
        (lambda item: item.update(run_id=0), "hosted_validation_run_identity_invalid"),
        (lambda item: item.update(event="push", ref="refs/heads/feature"), "hosted_validation_push_ref_invalid"),
    ],
)
def test_stale_incomplete_failed_or_skipped_hosted_evidence_is_rejected(mutation, expected_reason: str) -> None:
    evidence = _evidence()
    mutation(evidence)
    proof = verify_hosted_validation_evidence(
        evidence, expected_sha=CANDIDATE_SHA, expected_tree=CANDIDATE_TREE, expected_repository=REPOSITORY,
    )
    assert proof["status"] == "hosted_validation_evidence_blocked"
    assert expected_reason in proof["reasons"]


def _plan_pair(evidence: dict[str, object] | None):
    common = {
        "requested_profile": "solo", "effective_profile": "solo", "title": TITLE,
        "intended_commit_title": TITLE, "task_acceptance_manifest_digest": None,
        "task_acceptance_provenance_digest": None, "focused_test_command_contract": ["pytest"],
        "targeted_mypy_command_contract": ["mypy"], "conditionally_required_stage_ids": [],
        "skipped_or_deferred_stage_ids": [], "total_validation_duration_seconds": 1,
        "configured_total_budget_seconds": 1200, "remaining_budget_seconds": 1199,
        "exhaustive_matrix_status": "not_requested_for_solo_profile", "exhaustive_matrix_digest": None,
        "hosted_deferred_stage_ids": list(REQUIRED_STAGES),
        "candidate_workspace_identity": "sha256:" + "e" * 64,
        "causal_validation_candidate_sha": BASE_SHA,
        "causal_validation_status": "comparison_incomplete",
        "causal_validation_incomplete_classification": "paired_timeout",
        "causal_validation_command_contract_digest": "sha256:" + "f" * 64,
        "causal_validation_comparison_digest": "sha256:" + "1" * 64,
    }
    pre = seal_validation_plan({
        **common, "repository_sha": BASE_SHA, "phase": "pre-commit", "changed_file_identity": ["src.py"],
        "required_stage_ids": list(REQUIRED_STAGES),
        "stage_results": {stage: {"status": "hosted_deferred", "source": "local"} for stage in REQUIRED_STAGES},
        "hosted_validation_evidence": None,
        "candidate_tree_sha": "",
        "overall_status": "ready_to_commit_pending_hosted_validation",
    })
    post = seal_validation_plan({
        **common, "repository_sha": CANDIDATE_SHA, "phase": "pr-metadata", "changed_file_identity": [],
        "required_stage_ids": list(REQUIRED_STAGES),
        "stage_results": {stage: {"status": "hosted_passed", "source": "hosted_validation_workflow"} for stage in REQUIRED_STAGES},
        "hosted_validation_evidence": evidence,
        "candidate_tree_sha": CANDIDATE_TREE,
        "overall_status": "ready_for_pr_metadata",
    })
    workspace = {"base_head_sha": BASE_SHA, "intended_commit_title": TITLE, "changed_path_manifest_digest": "c" * 64, "matrix_digest": None}
    commit = {"parent_sha": BASE_SHA, "head_sha": CANDIDATE_SHA, "tree_sha": CANDIDATE_TREE, "commit_subject": TITLE, "changed_path_manifest_digest": "c" * 64, "matrix_digest": None}
    return pre, post, workspace, commit


def test_pending_candidate_then_exact_hosted_success_completes_validation_lineage() -> None:
    evidence = verify_hosted_validation_evidence(
        _evidence(), expected_sha=CANDIDATE_SHA, expected_tree=CANDIDATE_TREE, expected_repository=REPOSITORY,
    )
    pre, post, workspace, commit = _plan_pair(evidence)
    assert verify_validation_plan(pre)[0]
    assert verify_validation_plan(post)[0]
    ready, reasons, proof = verify_validation_plan_transition(pre, post, workspace, commit)
    assert ready, reasons
    assert proof["transition_status"] == "validation_plan_transition_ready"


def test_missing_hosted_evidence_prevents_post_commit_readiness() -> None:
    pre, post, workspace, commit = _plan_pair(None)
    ready, reasons, _ = verify_validation_plan_transition(pre, post, workspace, commit)
    assert not ready
    assert "hosted_validation_evidence_missing_or_stale" in reasons


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda item: item.update(head_sha=BASE_SHA), "hosted_validation_candidate_sha_mismatch"),
        (lambda item: item.update(head_tree="f" * 40), "hosted_validation_candidate_tree_mismatch"),
        (lambda item: item.update(status="in_progress"), "hosted_validation_incomplete"),
        (lambda item: item.update(conclusion="failure"), "hosted_validation_not_successful"),
        (lambda item: item["stages"].update(broad_validation={"status": "failed", "exit_code": 124}), "hosted_validation_stage_not_passed:broad_validation"),
    ],
)
def test_hosted_failure_incompleteness_and_wrong_revision_never_advance(mutation, reason: str) -> None:
    evidence = _evidence()
    mutation(evidence)
    proof = verify_hosted_validation_evidence(
        evidence, expected_sha=CANDIDATE_SHA, expected_tree=CANDIDATE_TREE, expected_repository=REPOSITORY,
    )
    assert proof["status"] == "hosted_validation_evidence_blocked"
    assert reason in proof["reasons"]


def test_post_commit_hosted_handoff_binds_exact_candidate_tree_without_claiming_hosted_pass() -> None:
    pre, post, workspace, commit = _plan_pair(None)
    post = seal_validation_plan({
        **{key: value for key, value in post.items() if key != "artifact_digest"},
        "phase": "post-commit",
        "overall_status": "ready_for_hosted_validation",
        "candidate_tree_sha": CANDIDATE_TREE,
        "stage_results": {stage: {"status": "hosted_deferred", "source": "unavailable_local_substrate"} for stage in REQUIRED_STAGES},
    })
    ready, reasons, _ = verify_validation_plan_transition(pre, post, workspace, commit)
    assert ready, reasons

    changed_commit = {**commit, "tree_sha": "f" * 40}
    ready, reasons, _ = verify_validation_plan_transition(pre, post, workspace, changed_commit)
    assert not ready
    assert "hosted_handoff_candidate_tree_mismatch" in reasons


def _write_guard_fixture(tmp_path: Path, evidence: dict[str, object] | None) -> CodexPrMetadataGuardRequest:
    tmp_path.mkdir(parents=True, exist_ok=True)
    pre_plan, post_plan, workspace, commit = _plan_pair(evidence)
    pre = {
        "request": {"title": TITLE, "intended_commit_title": TITLE, "phase": "pre-commit"},
        "decision": {"status": "ready_to_commit_pending_hosted_validation", "reasons": []},
        "landing_validation_plan": pre_plan,
        "workspace_binding": workspace,
        "report": {"artifacts": [{"classification": "clean"}]},
    }
    post = {
        "request": {"title": TITLE, "intended_commit_title": TITLE, "phase": "pr-metadata"},
        "decision": {"status": "ready_for_pr_metadata", "reasons": []},
        "landing_validation_plan": post_plan,
        "commit_binding": commit,
        "report": {"commands": [], "artifacts": [{"classification": "clean"}]},
        "evidence_freshness": {"stale_evidence_refresh_result": "not_required"},
        "dirty_paths": [],
    }
    pre_path, post_path, matrix_path = tmp_path / "pre.json", tmp_path / "post.json", tmp_path / "matrix.json"
    pre_path.write_text(json.dumps(pre)); post_path.write_text(json.dumps(post))
    matrix_path.write_text(json.dumps({"status": "passed", "required_failure_count": 0}))
    return CodexPrMetadataGuardRequest(
        title=TITLE, intended_commit_title=TITLE, pre_commit_finalizer_json=str(pre_path),
        pr_metadata_finalizer_json=str(post_path), matrix_json_path=str(matrix_path),
        workspace_root=str(tmp_path), git_status_lines=(),
    )


def test_pr_metadata_guard_requires_hosted_evidence_before_merge_readiness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        "sentientos.codex_pr_metadata_guard.verify_commit_matches_workspace",
        lambda *a, **k: SimpleNamespace(to_dict=lambda: {"status": "landing_evidence_binding_ready", "reasons": []}),
    )
    exact = verify_hosted_validation_evidence(
        _evidence(), expected_sha=CANDIDATE_SHA, expected_tree=CANDIDATE_TREE, expected_repository=REPOSITORY,
    )
    ready = evaluate_pr_metadata_guard(_write_guard_fixture(tmp_path / "with-evidence", exact))
    assert ready.ready
    assert ready.status == "pr_metadata_guard_ready"

    blocked = evaluate_pr_metadata_guard(_write_guard_fixture(tmp_path / "without-evidence", None))
    assert not blocked.ready
    assert blocked.status != "pr_metadata_guard_ready"
