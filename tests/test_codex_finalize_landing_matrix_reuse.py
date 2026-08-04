from __future__ import annotations

from pathlib import Path
import pytest

pytestmark = pytest.mark.no_legacy_skip
SOURCE = Path("scripts/codex_finalize_landing.py")


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_precommit_retry_reuses_exact_passing_matrix() -> None:
    text = _source(); assert "exact_precommit_retry_reuse" in text and "precommit_retry_reuse" in text


def test_precommit_retry_resumes_incomplete_matrix() -> None:
    text = _source(); assert "--resume-from" in text and "checkpoint_incomplete" in text


def test_precommit_retry_rejects_semantic_workspace_change() -> None:
    assert "workspace_binding_changed" in _source()


def test_generated_cleanup_does_not_stale_exact_matrix() -> None:
    assert "Generated runtime cleanup is excluded from semantic identity" in _source()


def test_postcommit_transition_still_requires_commit_binding() -> None:
    text = _source(); assert "verify_commit_matches_workspace" in text and "create_commit_binding" in text
