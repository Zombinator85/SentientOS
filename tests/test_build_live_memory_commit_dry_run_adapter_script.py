from __future__ import annotations

import json

import pytest
import subprocess
import sys
from pathlib import Path

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/live_memory_commit_dry_run_adapter")
SCRIPT = Path("scripts/build_live_memory_commit_dry_run_adapter.py")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_build_default_and_validate_policy() -> None:
    built = _run("build-default")
    assert built.returncode == 0, built.stderr
    assert json.loads(built.stdout)["policy"]["default_dry_run_posture"] == "deny"
    validated = _run("validate")
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["status"] == "valid"


def test_evaluate_and_summarize_valid_fixture() -> None:
    fixture = FIXTURES / "valid_ai_capsule_commit_dry_run_candidate.json"
    evaluated = _run("evaluate", "--input", str(fixture))
    assert evaluated.returncode == 0, evaluated.stderr
    payload = json.loads(evaluated.stdout)
    assert payload["status"] == "live_memory_commit_dry_run_ready"
    assert payload["packet"]["records"][0]["dry_run_decision"] == "dry_run_commit_preview_ready"
    summarized = _run("summarize", "--input", str(fixture), "--summary")
    assert summarized.returncode == 0, summarized.stderr
    summary = json.loads(summarized.stdout)
    assert summary["status"] == "live_memory_commit_dry_run_ready"
    assert summary["packet_digest"].startswith("sha256:")


def test_blocked_fixture_exits_nonzero() -> None:
    blocked = _run("evaluate", "--input", str(FIXTURES / "live_write_claim_blocked.json"))
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["status"] == "live_memory_commit_dry_run_blocked_live_write_claim"


def test_inspect_fixture_and_output_file(tmp_path: Path) -> None:
    out = tmp_path / "summary.json"
    inspected = _run("inspect-fixture", "--fixtures-dir", str(FIXTURES), "--fixture-name", "valid_noop_commit_dry_run_candidate.json")
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)["commit_candidate"]["candidate_type"] == "noop_commit_dry_run_candidate"
    evaluated = _run("evaluate", "--input", str(FIXTURES / "valid_noop_commit_dry_run_candidate.json"), "--output", str(out))
    assert evaluated.returncode == 0, evaluated.stderr
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "live_memory_commit_dry_run_noop"
