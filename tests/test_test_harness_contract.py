from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_declares_canonical_run_tests_entrypoint() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "python -m scripts.run_tests -q" in readme
    assert "SENTIENTOS_ALLOW_NAKED_PYTEST=1" in readme


def test_normalization_note_tracks_direct_pytest_divergence() -> None:
    note = (REPO_ROOT / "docs" / "TEST_HARNESS_NORMALIZATION.md").read_text(encoding="utf-8")
    assert "canonical entrypoint" in note.lower()
    assert "SENTIENTOS_ALLOW_NAKED_PYTEST=1" in note
    assert "bootstrap-metrics-failed" in note
