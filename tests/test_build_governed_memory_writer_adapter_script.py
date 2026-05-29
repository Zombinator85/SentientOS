from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = Path("scripts/build_governed_memory_writer_adapter.py")
FIXTURES = Path("tests/fixtures/governed_memory_writer_adapter")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_build_default_validate_evaluate_summarize_and_inspect() -> None:
    default = _run("build-default")
    assert default.returncode == 0
    assert json.loads(default.stdout)["policy"]["default_mode"] == "dry_run_preview"
    validate = _run("validate")
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["ok"] is True
    fixture = FIXTURES / "valid_ai_capsule_dry_run_preview.json"
    evaluate = _run("evaluate", "--input", str(fixture))
    assert evaluate.returncode == 0
    assert json.loads(evaluate.stdout)["status"] == "governed_memory_writer_dry_run_ready"
    summarize = _run("summarize", "--input", str(fixture))
    assert summarize.returncode == 0
    assert json.loads(summarize.stdout)["summary_counts"]["candidate_count"] == 1
    inspected = _run("inspect-fixture", "--fixture", "valid_ai_capsule_dry_run_preview.json")
    assert inspected.returncode == 0
    assert json.loads(inspected.stdout)["writer_candidate"]["candidate_type"] == "ai_capsule_artifact_candidate"


def test_evaluate_writes_output_json_but_no_artifact(tmp_path: Path) -> None:
    out = tmp_path / "evaluation.json"
    artifact = tmp_path / "artifact.json"
    result = _run("evaluate", "--input", str(FIXTURES / "valid_ai_capsule_artifact_write.json"), "--output", str(out))
    assert result.returncode == 0
    assert out.exists()
    assert not artifact.exists()


def test_write_artifact_requires_safe_explicit_path_and_supports_dry_run(tmp_path: Path) -> None:
    fixture = FIXTURES / "valid_ai_capsule_artifact_write.json"
    dry = _run("write-artifact", "--input", str(fixture), "--output-root", str(tmp_path), "--artifact-path", "artifact.json", "--dry-run")
    assert dry.returncode == 0
    assert not (tmp_path / "artifact.json").exists()
    written = _run("write-artifact", "--input", str(fixture), "--output-root", str(tmp_path), "--artifact-path", "artifact.json")
    assert written.returncode == 0
    payload = json.loads(written.stdout)
    assert payload["packet"]["artifact_receipts"][0]["candidate_id"] == "candidate-valid_ai_capsule_artifact_write"
    assert (tmp_path / "artifact.json").exists()
    blocked = _run("write-artifact", "--input", str(fixture), "--output-root", str(tmp_path), "--artifact-path", "../escape.json")
    assert blocked.returncode != 0
    assert json.loads(blocked.stdout)["status"] == "governed_memory_writer_blocked_unsafe_output_path"


def test_blocked_cli_exits_nonzero() -> None:
    result = _run("evaluate", "--input", str(FIXTURES / "digest_mismatch_blocked.json"))
    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "governed_memory_writer_blocked_digest_mismatch"
