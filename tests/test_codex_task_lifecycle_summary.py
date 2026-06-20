from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.codex_task_lifecycle_summary import (
    BLOCKED,
    GUARD_NOT_PROVIDED,
    READY,
    CodexTaskLifecycleSummaryError,
    CodexTaskLifecycleSummaryRequest,
    build_task_lifecycle_summary,
)


def _write(path: Path, payload: dict[str, object]) -> str:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return str(path)


def _finalizer(status: str, **freshness: object) -> dict[str, object]:
    payload: dict[str, object] = {"decision": {"status": status, "reasons": []}}
    if freshness:
        payload["evidence_freshness"] = freshness
    return payload


def _request(tmp_path: Path, pre: dict[str, object], pr: dict[str, object], guard: dict[str, object] | None = None) -> CodexTaskLifecycleSummaryRequest:
    guard_path = _write(tmp_path / "guard.json", guard) if guard is not None else None
    return CodexTaskLifecycleSummaryRequest(
        title="[codex:landing] add Codex task lifecycle summary artifact",
        intended_commit_title="[codex:landing] add Codex task lifecycle summary artifact",
        pre_commit_finalizer_json=_write(tmp_path / "pre.json", pre),
        pr_metadata_finalizer_json=_write(tmp_path / "pr.json", pr),
        matrix_json_path="/tmp/work_item_review_packet_matrix.json",
        pr_metadata_guard_json=guard_path,
    )


def test_ready_lifecycle_summary_with_ready_guard(tmp_path: Path) -> None:
    summary = build_task_lifecycle_summary(_request(tmp_path, _finalizer("ready_to_commit"), _finalizer("ready_for_pr_metadata"), {"status": "pr_metadata_guard_ready"}))
    assert summary["overall_lifecycle_status"] == READY
    assert summary["pr_metadata_guard_status"] == "pr_metadata_guard_ready"
    assert summary["rerun_required"] is False


def test_ready_lifecycle_summary_without_guard(tmp_path: Path) -> None:
    summary = build_task_lifecycle_summary(_request(tmp_path, _finalizer("ready_to_commit"), _finalizer("ready_for_pr_metadata")))
    assert summary["overall_lifecycle_status"] == READY
    assert summary["pr_metadata_guard_status"] == GUARD_NOT_PROVIDED


def test_blocked_when_pre_commit_not_ready(tmp_path: Path) -> None:
    summary = build_task_lifecycle_summary(_request(tmp_path, _finalizer("manual_review_required"), _finalizer("ready_for_pr_metadata")))
    assert summary["overall_lifecycle_status"] == BLOCKED
    assert "pre_commit_finalizer_not_ready" in str(summary["rerun_reason"])


def test_blocked_when_pr_metadata_not_ready(tmp_path: Path) -> None:
    summary = build_task_lifecycle_summary(_request(tmp_path, _finalizer("ready_to_commit"), _finalizer("repair_required_task_caused")))
    assert summary["overall_lifecycle_status"] == BLOCKED
    assert "pr_metadata_finalizer_not_ready" in str(summary["rerun_reason"])


def test_blocked_when_any_finalizer_rerun_required(tmp_path: Path) -> None:
    summary = build_task_lifecycle_summary(_request(tmp_path, _finalizer("ready_to_commit", rerun_required=True), _finalizer("ready_for_pr_metadata")))
    assert summary["overall_lifecycle_status"] == BLOCKED
    assert summary["rerun_required"] is True
    assert "pre_commit_finalizer_rerun_required" in str(summary["rerun_reason"])


def test_blocked_when_guard_not_ready(tmp_path: Path) -> None:
    summary = build_task_lifecycle_summary(_request(tmp_path, _finalizer("ready_to_commit"), _finalizer("ready_for_pr_metadata"), {"status": "pr_metadata_guard_blocked_matrix_failed"}))
    assert summary["overall_lifecycle_status"] == BLOCKED
    assert "pr_metadata_guard_not_ready" in str(summary["rerun_reason"])


def test_missing_optional_refresh_fields_are_tolerated(tmp_path: Path) -> None:
    summary = build_task_lifecycle_summary(_request(tmp_path, _finalizer("ready_to_commit"), _finalizer("ready_for_pr_metadata")))
    assert summary["finalizers"]["pre_commit"]["terminal_refresh_status"] is None
    assert summary["finalizers"]["pr_metadata"]["stale_evidence_refresh_result"] is None


def test_invalid_json_fails_cleanly(tmp_path: Path) -> None:
    pre = tmp_path / "pre.json"
    pre.write_text("{not-json", encoding="utf-8")
    pr = _write(tmp_path / "pr.json", _finalizer("ready_for_pr_metadata"))
    request = CodexTaskLifecycleSummaryRequest("title", "title", str(pre), pr, "/tmp/matrix.json")
    with pytest.raises(CodexTaskLifecycleSummaryError, match="invalid_json"):
        build_task_lifecycle_summary(request)


def test_non_authority_posture_fields_are_true(tmp_path: Path) -> None:
    summary = build_task_lifecycle_summary(_request(tmp_path, _finalizer("ready_to_commit"), _finalizer("ready_for_pr_metadata")))
    assert summary["metadata_only"] is True
    assert summary["developer_workflow_evidence_only"] is True
    assert all(summary["non_authority_posture"].values())
