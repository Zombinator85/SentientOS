from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from sentientos.native_codex_pilot_results import (
    DEFAULT_PILOT_PATH,
    ResultsIntegrityError,
    verify_native_codex_pilot_results,
)


pytestmark = pytest.mark.no_legacy_skip


def _copy_pilot(tmp_path: Path) -> Path:
    repository_root = Path(__file__).resolve().parents[1]
    source = repository_root / DEFAULT_PILOT_PATH
    destination = tmp_path / DEFAULT_PILOT_PATH
    destination.parent.mkdir(parents=True)
    shutil.copytree(source, destination)
    return tmp_path


def _failure_paths(repository_root: Path) -> tuple[Path, Path]:
    summary_path = repository_root / DEFAULT_PILOT_PATH / "results" / "results_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    history = summary["scoring_attempt_history"]
    failure_path = repository_root / history["failure_record_path"]
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    partial_path = repository_root / failure["partial_artifact_path"]
    return failure_path, partial_path


def test_verifier_binds_preserved_scoring_failure_without_affecting_observations(
    tmp_path: Path,
) -> None:
    repository_root = _copy_pilot(tmp_path)

    result = verify_native_codex_pilot_results(repository_root)

    assert result["status"] == "internally_consistent"
    assert result["captured_count"] == 12
    assert result["valid_scored_count"] == 12
    assert result["stance_matches_reported_by_score_files"] == 12
    assert result["failed_controller_artifact_writes_verified"] == 1
    assert result["scoring_attempt_history_verified"] is True
    assert result["key_accessed"] is False
    assert result["key_based_accuracy_independently_verified"] is False
    _, partial_path = _failure_paths(repository_root)
    assert partial_path.read_bytes() == b""


def test_verifier_rejects_changed_partial_score_write_artifact(tmp_path: Path) -> None:
    repository_root = _copy_pilot(tmp_path)
    _, partial_path = _failure_paths(repository_root)
    partial_path.write_bytes(b"partial score data")

    with pytest.raises(
        ResultsIntegrityError, match="Partial scoring artifact digest or size mismatch"
    ):
        verify_native_codex_pilot_results(repository_root)


def test_verifier_rejects_failure_record_that_claims_observation_damage(
    tmp_path: Path,
) -> None:
    repository_root = _copy_pilot(tmp_path)
    failure_path, _ = _failure_paths(repository_root)
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    failure["model_observation_affected"] = True
    failure_path.write_text(json.dumps(failure), encoding="utf-8")

    with pytest.raises(
        ResultsIntegrityError, match="Scoring failure record posture is inconsistent"
    ):
        verify_native_codex_pilot_results(repository_root)


def test_verifier_rejects_missing_failure_record_or_partial_artifact(tmp_path: Path) -> None:
    repository_root = _copy_pilot(tmp_path)
    failure_path, _ = _failure_paths(repository_root)
    failure_path.unlink()

    with pytest.raises(
        ResultsIntegrityError, match="Scoring failure record is unavailable or invalid"
    ):
        verify_native_codex_pilot_results(repository_root)

    second_root = _copy_pilot(tmp_path / "second")
    _, partial_path = _failure_paths(second_root)
    partial_path.unlink()
    with pytest.raises(ResultsIntegrityError, match="Partial scoring artifact is unavailable"):
        verify_native_codex_pilot_results(second_root)


def test_verifier_rejects_scoring_failure_evidence_from_another_pilot(
    tmp_path: Path,
) -> None:
    repository_root = _copy_pilot(tmp_path)
    failure_path, partial_path = _failure_paths(repository_root)
    other_pilot = repository_root / "artifacts" / "experiments" / "other-pilot"
    other_pilot.mkdir(parents=True)
    other_partial = other_pilot / "partial-score.json"
    other_partial.write_bytes(partial_path.read_bytes())

    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    failure["partial_artifact_path"] = str(other_partial.relative_to(repository_root))
    failure_path_outside = other_pilot / "failure.json"
    failure_path_outside.write_text(json.dumps(failure), encoding="utf-8")

    summary_path = repository_root / DEFAULT_PILOT_PATH / "results" / "results_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["scoring_attempt_history"]["failure_record_path"] = str(
        failure_path_outside.relative_to(repository_root)
    )
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(
        ResultsIntegrityError, match="Pilot evidence path escapes selected pilot directory"
    ):
        verify_native_codex_pilot_results(repository_root)


def test_verifier_rejects_partial_artifact_from_another_pilot(tmp_path: Path) -> None:
    repository_root = _copy_pilot(tmp_path)
    failure_path, partial_path = _failure_paths(repository_root)
    other_pilot = repository_root / "artifacts" / "experiments" / "other-pilot"
    other_pilot.mkdir(parents=True)
    other_partial = other_pilot / "partial-score.json"
    other_partial.write_bytes(partial_path.read_bytes())

    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    failure["partial_artifact_path"] = str(other_partial.relative_to(repository_root))
    failure_path.write_text(json.dumps(failure), encoding="utf-8")

    with pytest.raises(
        ResultsIntegrityError, match="Pilot evidence path escapes selected pilot directory"
    ):
        verify_native_codex_pilot_results(repository_root)
