from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path("scripts/build_sandboxed_live_memory_commit_adapter_gate.py")
pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/sandboxed_live_memory_commit_adapter_gate")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)


def test_evaluate_ready_fixture_emits_json_and_writes_nothing() -> None:
    path = FIXTURES / "ready_sandboxed_live_memory_commit_adapter_gate_candidate.json"
    before = {p.name: p.stat().st_mtime_ns for p in FIXTURES.glob("*.json")}
    proc = run_cli("evaluate", str(path))
    after = {p.name: p.stat().st_mtime_ns for p in FIXTURES.glob("*.json")}
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["status"] == "sandboxed_live_memory_commit_adapter_gate_ready"
    assert before == after


def test_summarize_and_validate_ready_fixture() -> None:
    path = FIXTURES / "ready_sandboxed_live_memory_commit_adapter_gate_candidate.json"
    validate = run_cli("validate", str(path))
    summarize = run_cli("summarize", str(path))
    assert validate.returncode == 0, validate.stderr
    assert summarize.returncode == 0, summarize.stderr
    summary = json.loads(summarize.stdout)
    assert summary["status"] == "sandboxed_live_memory_commit_adapter_gate_ready"
    assert summary["summary_counts"]["candidate_count"] == 1


def test_inspect_fixture_and_blocked_exit_nonzero() -> None:
    inspect = run_cli("inspect-fixture", "ready_sandboxed_live_memory_commit_adapter_gate_candidate")
    blocked = run_cli("evaluate", str(FIXTURES / "live_write_claim_blocked.json"))
    assert inspect.returncode == 0, inspect.stderr
    assert json.loads(inspect.stdout)["sandboxed_live_memory_commit_adapter_gate_candidates"]
    assert blocked.returncode != 0
