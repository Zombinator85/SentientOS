from __future__ import annotations

import json

import pytest
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/build_final_live_memory_commit_review_gate.py")
pytestmark = pytest.mark.no_legacy_skip

FIXTURE_ROOT = Path("tests/fixtures/final_live_memory_commit_review_gate")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_cli_evaluate_validate_summarize_and_inspect_fixture() -> None:
    ready = str(FIXTURE_ROOT / "ready_final_live_memory_commit_review_gate_candidate.json")
    evaluated = run_cli("evaluate", ready)
    assert evaluated.returncode == 0, evaluated.stderr
    payload = json.loads(evaluated.stdout)
    assert payload["status"] == "final_live_memory_commit_review_gate_ready"

    validated = run_cli("validate", ready)
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["status"] == "final_live_memory_commit_review_gate_ready"

    summarized = run_cli("summarize", ready)
    assert summarized.returncode == 0, summarized.stderr
    summary = json.loads(summarized.stdout)
    assert summary["status"] == "final_live_memory_commit_review_gate_ready"
    assert summary["gate_digest"].startswith("sha256:")

    inspected = run_cli("inspect-fixture", "ready_final_live_memory_commit_review_gate_candidate")
    assert inspected.returncode == 0, inspected.stderr
    assert "final_live_memory_commit_review_gate_candidates" in json.loads(inspected.stdout)


def test_cli_build_default_and_blocked_exit_nonzero() -> None:
    defaulted = run_cli("build-default")
    assert defaulted.returncode == 0, defaulted.stderr
    assert json.loads(defaulted.stdout)["validation"]["status"] == "valid"

    blocked = run_cli("evaluate", str(FIXTURE_ROOT / "digest_mismatch_blocked.json"))
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["status"] == "final_live_memory_commit_review_gate_blocked"
