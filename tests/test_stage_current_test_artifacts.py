from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.stage_current_test_artifacts import stage_current_test_artifacts

pytestmark = pytest.mark.no_legacy_skip


def _write_provenance(repo: Path, payload: dict[str, object]) -> None:
    path = repo / "glow" / "test_runs" / "test_run_provenance.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_only_artifacts_bound_by_current_provenance_are_staged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    run_dir = repo / "glow" / "test_runs"
    run_dir.mkdir(parents=True)
    junit = run_dir / "pytest_junitxml_current.xml"
    failure_digest = run_dir / "test_failure_digest.json"
    junit.write_bytes(b"<testsuite tests='2' failures='1'/>")
    failure_digest.write_bytes(b'{"failure_groups":["current"]}')
    (run_dir / "pytest_junitxml_historical.xml").write_bytes(b"stale failure")
    marker = tmp_path / "run-started"
    marker.touch()
    payload: dict[str, object] = {
        "run_id": "run-current",
        "git_sha": "a" * 40,
        "validation_status": "validation_incomplete",
        "tests_passed": 1,
        "tests_failed": 1,
        "junitxml_path": str(junit),
        "failure_report_path": str(failure_digest),
    }
    _write_provenance(repo, payload)
    output = tmp_path / "artifact"

    manifest = stage_current_test_artifacts(
        repo_root=repo,
        output_dir=output,
        expected_repository_sha="a" * 40,
        started_after=marker,
    )

    assert manifest["provenance_status"] == "current"
    assert manifest["expected_repository_sha"] == "a" * 40
    assert (output / "pytest_junitxml.xml").read_bytes() == junit.read_bytes()
    assert (output / "test_failure_digest.json").read_bytes() == failure_digest.read_bytes()
    assert not (output / "pytest_junitxml_historical.xml").exists()
    assert manifest["provenance_sha256"] == hashlib.sha256(
        (run_dir / "test_run_provenance.json").read_bytes()
    ).hexdigest()
    artifacts = manifest["artifacts"]
    assert artifacts["junitxml_path"]["sha256"] == hashlib.sha256(junit.read_bytes()).hexdigest()
    assert artifacts["failure_report_path"]["sha256"] == hashlib.sha256(failure_digest.read_bytes()).hexdigest()


def test_missing_current_artifact_does_not_retain_previous_staged_xml(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    run_dir = repo / "glow" / "test_runs"
    run_dir.mkdir(parents=True)
    _write_provenance(repo, {"run_id": "run-without-xml", "junitxml_path": "missing.xml"})
    output = tmp_path / "artifact"
    output.mkdir()
    stale_output = output / "pytest_junitxml.xml"
    stale_output.write_text("prior run", encoding="utf-8")

    manifest = stage_current_test_artifacts(repo_root=repo, output_dir=output)

    assert not stale_output.exists()
    assert manifest["artifacts"]["junitxml_path"]["status"] == "missing"


def test_artifact_paths_cannot_escape_the_test_run_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    run_dir = repo / "glow" / "test_runs"
    run_dir.mkdir(parents=True)
    outside = tmp_path / "pytest_junitxml_secret.xml"
    outside.write_text("outside", encoding="utf-8")
    _write_provenance(repo, {"junitxml_path": str(outside)})
    output = tmp_path / "artifact"

    manifest = stage_current_test_artifacts(repo_root=repo, output_dir=output)

    assert not (output / "pytest_junitxml.xml").exists()
    assert manifest["artifacts"]["junitxml_path"]["status"] == "outside_test_run_root"


def test_stale_provenance_is_not_staged_even_when_its_artifact_still_exists(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    run_dir = repo / "glow" / "test_runs"
    run_dir.mkdir(parents=True)
    junit = run_dir / "pytest_junitxml_old.xml"
    junit.write_text("historical", encoding="utf-8")
    _write_provenance(repo, {"git_sha": "a" * 40, "junitxml_path": str(junit)})
    marker = tmp_path / "run-started"
    marker.touch()
    output = tmp_path / "artifact"

    manifest = stage_current_test_artifacts(
        repo_root=repo,
        output_dir=output,
        expected_repository_sha="a" * 40,
        started_after=marker,
    )

    assert manifest["provenance_status"] == "stale_provenance"
    assert not (output / "pytest_junitxml.xml").exists()


def test_provenance_for_a_different_source_revision_is_not_staged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    run_dir = repo / "glow" / "test_runs"
    run_dir.mkdir(parents=True)
    junit = run_dir / "pytest_junitxml_old.xml"
    junit.write_text("other source", encoding="utf-8")
    _write_provenance(repo, {"git_sha": "a" * 40, "junitxml_path": str(junit)})

    manifest = stage_current_test_artifacts(
        repo_root=repo,
        output_dir=tmp_path / "artifact",
        expected_repository_sha="b" * 40,
    )

    assert manifest["provenance_status"] == "source_sha_mismatch"
    assert not (tmp_path / "artifact" / "pytest_junitxml.xml").exists()


def test_invalid_current_provenance_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    provenance = repo / "glow" / "test_runs" / "test_run_provenance.json"
    provenance.parent.mkdir(parents=True)
    provenance.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a JSON object"):
        stage_current_test_artifacts(repo_root=repo, output_dir=tmp_path / "artifact")
