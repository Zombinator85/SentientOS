from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path("scripts/build_final_live_memory_commit_review_gate.py")
pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/final_live_memory_commit_review_gate")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_build_default_and_validate() -> None:
    default = _run("build-default")
    assert default.returncode == 0
    assert json.loads(default.stdout)["policy"]["default_posture"] == "deny"
    validate = _run("validate")
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["status"] == "valid"


def test_inspect_fixture_and_evaluate_write_nothing(tmp_path: Path) -> None:
    fixture = "valid_ai_capsule_final_live_commit_review_candidate.json"
    inspect = _run("inspect-fixture", "--fixture-name", fixture)
    assert inspect.returncode == 0
    assert json.loads(inspect.stdout)["final_live_commit_review_candidates"][0]["candidate_type"] == "ai_capsule_final_live_commit_review_candidate"
    before = sorted(tmp_path.rglob("*"))
    evaluate = _run("evaluate", "--input", str(FIXTURES / fixture))
    assert evaluate.returncode == 0
    assert json.loads(evaluate.stdout)["status"] == "final_live_commit_review_ready"
    assert sorted(tmp_path.rglob("*")) == before


def test_summarize_and_blocked_exit_nonzero() -> None:
    summary = _run("summarize", "--input", str(FIXTURES / "valid_ai_capsule_final_live_commit_review_candidate.json"))
    assert summary.returncode == 0
    assert json.loads(summary.stdout)["packet_digest"].startswith("sha256:")
    blocked = _run("evaluate", "--input", str(FIXTURES / "real_root_admission_digest_mismatch_blocked.json"))
    assert blocked.returncode != 0
    assert json.loads(blocked.stdout)["status"] == "final_live_commit_review_blocked"


def test_validate_input_metadata_uses_embedded_policy() -> None:
    validate = _run("validate", "--input", str(FIXTURES / "mixed_final_live_commit_review_candidate.json"))
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["status"] == "final_live_commit_review_ready_with_warnings"
