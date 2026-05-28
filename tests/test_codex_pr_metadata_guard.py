from __future__ import annotations

import json
from pathlib import Path

from sentientos.codex_pr_metadata_guard import CodexPrMetadataGuardRequest, evaluate_pr_metadata_guard, result_json

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
    data = {
        "title": TITLE,
        "intended_commit_title": TITLE,
        "pre_commit_finalizer_json": str(pre),
        "pr_metadata_finalizer_json": str(pr),
        "matrix_json_path": str(matrix),
        "git_status_lines": (),
    }
    data.update(overrides)
    return CodexPrMetadataGuardRequest(**data)  # type: ignore[arg-type]


def test_ready_pre_commit_and_pr_metadata_artifacts_are_ready(tmp_path: Path) -> None:
    result = evaluate_pr_metadata_guard(_request(tmp_path))
    assert result.status == "pr_metadata_guard_ready"
    assert result.ready is True


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
