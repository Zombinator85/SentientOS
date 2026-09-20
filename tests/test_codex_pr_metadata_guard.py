from __future__ import annotations

import json
import hashlib
import pytest
from pathlib import Path
from types import SimpleNamespace

from sentientos.codex_pr_metadata_guard import CodexPrMetadataGuardRequest, evaluate_pr_metadata_guard, result_json
from sentientos.landing_validation_plan import seal_validation_plan, verify_validation_plan


@pytest.mark.no_legacy_skip
def test_solo_profile_metadata_preserves_validation_profile() -> None:
    plan = seal_validation_plan({"requested_profile": "solo", "effective_profile": "solo", "repository_sha": "a" * 40, "phase": "pre-commit", "title": "x", "intended_commit_title": "x", "changed_file_identity": [], "task_acceptance_manifest_digest": None, "task_acceptance_provenance_digest": None, "focused_test_command_contract": [], "targeted_mypy_command_contract": [], "required_stage_ids": [], "conditionally_required_stage_ids": [], "skipped_or_deferred_stage_ids": ["matrix_summary"], "stage_results": {}, "total_validation_duration_seconds": 1, "configured_total_budget_seconds": 1200, "remaining_budget_seconds": 1199, "exhaustive_matrix_status": "not_requested_for_solo_profile", "exhaustive_matrix_digest": None, "overall_status": "ready_to_commit"})
    assert verify_validation_plan(plan)[0]
    assert plan["requested_profile"] == plan["effective_profile"] == "solo"

TITLE = "[codex:developer] harden blocked bootstrap and PR metadata gates"


def _finalizer(path: Path, *, decision: str, phase: str = "pr-metadata", title: str = TITLE, stale: str = "not_required", dirty: bool = False) -> Path:
    path.write_text(
        json.dumps(
            {
                "request": {"title": title, "intended_commit_title": title, "phase": phase},
                "decision": {"status": decision, "reasons": []},
                "report": {
                    "commands": [
                        {"stage": "pr_landing_gate", "exit_code": 0, "command": "gate", "required": True},
                        {"stage": "landing_supervisor", "exit_code": 0, "command": "supervisor", "required": True},
                    ],
                    "artifacts": [{"path": "dirty.py" if dirty else "", "classification": "intended_task_change" if dirty else "clean", "action": "block" if dirty else "none"}],
                },
                "evidence_freshness": {"stale_evidence_refresh_result": stale},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _matrix(path: Path, *, status: str = "passed") -> Path:
    path.write_text(json.dumps({"status": status, "required_failure_count": 0 if status == "passed" else 1}, sort_keys=True), encoding="utf-8")
    return path


def _request(tmp_path: Path, **overrides: object) -> CodexPrMetadataGuardRequest:
    pre = _finalizer(tmp_path / "pre.json", decision="ready_to_commit", phase="pre-commit")
    pr = _finalizer(tmp_path / "pr.json", decision="ready_for_pr_metadata")
    matrix = _matrix(tmp_path / "matrix.json")
    data: dict[str, object] = {
        "title": TITLE,
        "intended_commit_title": TITLE,
        "pre_commit_finalizer_json": str(pre),
        "pr_metadata_finalizer_json": str(pr),
        "matrix_json_path": str(matrix),
        "git_status_lines": (),
    }
    data.update(overrides)
    return CodexPrMetadataGuardRequest(**data)  # type: ignore[arg-type]


def _transition_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, profile: str = "solo"
) -> tuple[CodexPrMetadataGuardRequest, Path, Path]:
    request = _request(tmp_path)
    matrix_digest = hashlib.sha256(Path(request.matrix_json_path).read_bytes()).hexdigest()
    common = {
        "requested_profile": profile, "effective_profile": profile, "title": TITLE,
        "intended_commit_title": TITLE, "task_acceptance_manifest_digest": "d" * 64,
        "task_acceptance_provenance_digest": "e" * 64,
        "focused_test_command_contract": ["python -m scripts.run_tests -q tests/test_codex_pr_metadata_guard.py"],
        "targeted_mypy_command_contract": ["python -m mypy sentientos/codex_pr_metadata_guard.py"],
        "configured_total_budget_seconds": 1200, "exhaustive_matrix_digest": matrix_digest if profile == "exhaustive" else None,
    }
    matrix_status = "matrix_reused" if profile == "exhaustive" else "not_requested_for_solo_profile"
    pre_plan = seal_validation_plan({
        **common, "repository_sha": "a" * 40, "phase": "pre-commit", "changed_file_identity": ["sentientos/codex_pr_metadata_guard.py"],
        "required_stage_ids": ["focused_tests"], "conditionally_required_stage_ids": [], "skipped_or_deferred_stage_ids": ["matrix_summary"],
        "stage_results": {"focused_tests": {"status": "passed", "duration_seconds": 2}},
        "total_validation_duration_seconds": 8, "remaining_budget_seconds": 1192,
        "exhaustive_matrix_status": matrix_status, "overall_status": "ready_to_commit",
    })
    post_plan = seal_validation_plan({
        **common, "repository_sha": "b" * 40, "phase": "pr-metadata", "changed_file_identity": [],
        "required_stage_ids": ["focused_tests", "pr_landing_gate"], "conditionally_required_stage_ids": [], "skipped_or_deferred_stage_ids": ["matrix_summary"],
        "stage_results": {"focused_tests": {"status": "passed", "duration_seconds": 3}, "pr_landing_gate": {"status": "passed", "duration_seconds": 1}},
        "total_validation_duration_seconds": 5, "remaining_budget_seconds": 1195,
        "exhaustive_matrix_status": matrix_status, "overall_status": "ready_for_pr_metadata",
    })
    workspace = {"base_head_sha": "a" * 40, "intended_commit_title": TITLE, "changed_path_manifest_digest": "1" * 64, "matrix_digest": matrix_digest}
    commit = {"parent_sha": "a" * 40, "head_sha": "b" * 40, "commit_subject": TITLE, "changed_path_manifest_digest": "1" * 64, "matrix_digest": matrix_digest}
    pre_path, post_path = Path(request.pre_commit_finalizer_json), Path(request.pr_metadata_finalizer_json)
    pre_payload, post_payload = json.loads(pre_path.read_text()), json.loads(post_path.read_text())
    pre_payload.update(landing_validation_plan=pre_plan, workspace_binding=workspace)
    post_payload.update(landing_validation_plan=post_plan, commit_binding=commit)
    pre_path.write_text(json.dumps(pre_payload), encoding="utf-8")
    post_path.write_text(json.dumps(post_payload), encoding="utf-8")
    monkeypatch.setattr(
        "sentientos.codex_pr_metadata_guard.verify_commit_matches_workspace",
        lambda *_args: SimpleNamespace(to_dict=lambda: {"status": "landing_evidence_binding_ready", "reasons": (), "proof": {}}),
    )
    return request, pre_path, post_path


def _mutate(path: Path, section: str, field: str, value: object, *, reseal: bool = True) -> None:
    payload = json.loads(path.read_text())
    target = payload[section]
    target[field] = value
    if section == "landing_validation_plan" and reseal:
        payload[section] = seal_validation_plan(target)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_ready_pre_commit_and_pr_metadata_artifacts_are_ready(tmp_path: Path) -> None:
    result = evaluate_pr_metadata_guard(_request(tmp_path))
    assert result.status == "pr_metadata_guard_ready"
    assert result.ready is True


def test_solo_phase_local_plan_transition_is_ready_and_inspectable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request, pre, post = _transition_request(tmp_path, monkeypatch)
    pre_plan = json.loads(pre.read_text())["landing_validation_plan"]
    post_plan = json.loads(post.read_text())["landing_validation_plan"]
    for field in ("phase", "repository_sha", "overall_status", "artifact_digest", "total_validation_duration_seconds", "remaining_budget_seconds", "stage_results"):
        assert pre_plan[field] != post_plan[field]
    result = evaluate_pr_metadata_guard(request)
    assert result.status == "pr_metadata_guard_ready"
    proof = result.proof["validation_plan_transition"]
    assert proof["transition_status"] == "validation_plan_transition_ready"
    assert proof["pre_plan_digest"] != proof["post_plan_digest"]
    assert proof["shared_validation_profile"] == "solo"


@pytest.mark.parametrize("field,value", [
    ("requested_profile", "exhaustive"), ("effective_profile", "exhaustive"),
    ("title", "changed"), ("intended_commit_title", "changed"),
    ("task_acceptance_manifest_digest", "changed"), ("task_acceptance_provenance_digest", "changed"),
    ("focused_test_command_contract", ["changed"]), ("targeted_mypy_command_contract", ["changed"]),
])
def test_solo_stable_lineage_mutation_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object) -> None:
    request, _, post = _transition_request(tmp_path, monkeypatch)
    _mutate(post, "landing_validation_plan", field, value)
    result = evaluate_pr_metadata_guard(request)
    assert f"validation_lineage_field_mismatch:{field}" in result.reasons
    assert result.ready is False


@pytest.mark.parametrize("target,field,value,reason", [
    ("pre", "artifact_digest", "sha256:bad", "pre_commit_validation_plan_invalid:validation_plan_digest_mismatch"),
    ("post", "artifact_digest", "sha256:bad", "pr_metadata_validation_plan_invalid:validation_plan_digest_mismatch"),
    ("pre", "phase", "pr-metadata", "pre_commit_validation_phase_invalid"),
    ("post", "phase", "pre-commit", "pr_metadata_validation_phase_invalid"),
    ("pre", "overall_status", "ready_for_pr_metadata", "pre_commit_validation_status_invalid"),
    ("post", "overall_status", "ready_to_commit", "pr_metadata_validation_status_invalid"),
    ("pre", "repository_sha", "9" * 40, "pre_commit_validation_repository_sha_mismatch"),
    ("post", "repository_sha", "9" * 40, "pr_metadata_validation_repository_sha_mismatch"),
])
def test_solo_invalid_plan_transition_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, field: str, value: object, reason: str) -> None:
    request, pre, post = _transition_request(tmp_path, monkeypatch)
    _mutate(pre if target == "pre" else post, "landing_validation_plan", field, value, reseal=field != "artifact_digest")
    assert reason in evaluate_pr_metadata_guard(request).reasons


@pytest.mark.parametrize("target,field,value,reason", [
    ("post", "parent_sha", "9" * 40, "commit_parent_mismatch"),
    ("post", "changed_path_manifest_digest", "9" * 64, "workspace_manifest_mismatch"),
    ("post", "commit_subject", "changed", "commit_title_mismatch"),
])
def test_solo_commit_workspace_lineage_mutation_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, field: str, value: object, reason: str) -> None:
    request, _, post = _transition_request(tmp_path, monkeypatch)
    _mutate(post, "commit_binding", field, value)
    assert reason in evaluate_pr_metadata_guard(request).reasons


def test_exhaustive_transition_remains_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request, _, _ = _transition_request(tmp_path, monkeypatch, profile="exhaustive")
    assert evaluate_pr_metadata_guard(request).status == "pr_metadata_guard_ready"


def test_exhaustive_matrix_lineage_mismatch_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request, _, post = _transition_request(tmp_path, monkeypatch, profile="exhaustive")
    _mutate(post, "landing_validation_plan", "exhaustive_matrix_status", "matrix_passed")
    assert "pr_metadata_matrix_lineage_not_reused" in evaluate_pr_metadata_guard(request).reasons


def test_missing_pre_commit_artifact_blocks_normal_task(tmp_path: Path) -> None:
    result = evaluate_pr_metadata_guard(_request(tmp_path, pre_commit_finalizer_json=str(tmp_path / "missing.json")))
    assert result.status == "pr_metadata_guard_blocked_missing_pre_commit_finalizer"
    assert "missing_pre_commit_finalizer" in result.reasons


def test_missing_pr_metadata_artifact_blocks(tmp_path: Path) -> None:
    result = evaluate_pr_metadata_guard(_request(tmp_path, pr_metadata_finalizer_json=str(tmp_path / "missing.json")))
    assert result.status == "pr_metadata_guard_blocked_missing_pr_metadata_finalizer"


def test_pre_commit_not_ready_blocks(tmp_path: Path) -> None:
    pre = _finalizer(tmp_path / "pre_bad.json", decision="manual_review_required", phase="pre-commit")
    result = evaluate_pr_metadata_guard(_request(tmp_path, pre_commit_finalizer_json=str(pre)))
    assert result.status == "pr_metadata_guard_blocked_pre_commit_not_ready"


def test_pr_metadata_not_ready_blocks(tmp_path: Path) -> None:
    pr = _finalizer(tmp_path / "pr_bad.json", decision="repair_required_task_caused")
    result = evaluate_pr_metadata_guard(_request(tmp_path, pr_metadata_finalizer_json=str(pr)))
    assert result.status == "pr_metadata_guard_blocked_pr_metadata_not_ready"


def test_title_mismatch_blocks(tmp_path: Path) -> None:
    result = evaluate_pr_metadata_guard(_request(tmp_path, intended_commit_title="[codex:developer] other"))
    assert result.status == "pr_metadata_guard_blocked_title_mismatch"


def test_stale_evidence_refresh_required_blocks(tmp_path: Path) -> None:
    pr = _finalizer(tmp_path / "pr_stale.json", decision="ready_for_pr_metadata", stale="required_not_allowed")
    result = evaluate_pr_metadata_guard(_request(tmp_path, pr_metadata_finalizer_json=str(pr)))
    assert result.status == "pr_metadata_guard_blocked_stale_evidence"


def test_failed_matrix_artifact_blocks(tmp_path: Path) -> None:
    matrix = _matrix(tmp_path / "matrix_bad.json", status="failed")
    result = evaluate_pr_metadata_guard(_request(tmp_path, matrix_json_path=str(matrix)))
    assert result.status == "pr_metadata_guard_blocked_matrix_failed"


def test_dirty_tree_evidence_blocks(tmp_path: Path) -> None:
    pr = _finalizer(tmp_path / "pr_dirty.json", decision="ready_for_pr_metadata", dirty=True)
    result = evaluate_pr_metadata_guard(_request(tmp_path, pr_metadata_finalizer_json=str(pr)))
    assert result.status == "pr_metadata_guard_blocked_dirty_tree"


def test_validation_only_allows_no_pre_commit_when_clean(tmp_path: Path) -> None:
    result = evaluate_pr_metadata_guard(_request(tmp_path, validation_only=True, pre_commit_finalizer_json="", git_status_lines=()))
    assert result.status == "pr_metadata_guard_ready"


def test_validation_only_blocks_when_source_doc_test_changes_present(tmp_path: Path) -> None:
    result = evaluate_pr_metadata_guard(_request(tmp_path, validation_only=True, pre_commit_finalizer_json="", git_status_lines=(" M sentientos/x.py",)))
    assert result.status == "pr_metadata_guard_blocked_validation_only_mismatch"


def test_json_output_is_deterministic(tmp_path: Path) -> None:
    result = evaluate_pr_metadata_guard(_request(tmp_path))
    assert result_json(result) == result_json(result)
    assert '"status": "pr_metadata_guard_ready"' in result_json(result)
