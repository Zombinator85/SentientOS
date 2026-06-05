from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

READY = Path("tests/fixtures/real_executor_invocation_gate/ready_real_executor_invocation_gate_candidate.json")
SCRIPT = Path("scripts/build_real_executor_invocation_gate.py")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, check=False)


def test_cli_build_default_validate_evaluate_summarize_and_inspect_fixture() -> None:
    assert run_cli("build-default").returncode == 0
    assert run_cli("validate").returncode == 0
    evaluated = run_cli("evaluate", str(READY))
    assert evaluated.returncode == 0
    payload = json.loads(evaluated.stdout)
    assert payload["status"] == "real_executor_invocation_gate_ready"
    summarized = run_cli("summarize", str(READY))
    assert summarized.returncode == 0
    summary = json.loads(summarized.stdout)
    assert summary["status"] == "real_executor_invocation_gate_ready"
    assert summary["packet_digest"] == payload["packet"]["digest"]
    inspected = run_cli("inspect-fixture", "ready_real_executor_invocation_gate_candidate")
    assert inspected.returncode == 0
    assert json.loads(inspected.stdout)["real_executor_invocation_gate_candidates"][0]["candidate_id"] == "real-invocation-gate-ready-001"


def test_cli_evaluate_writes_no_files_and_blocked_exits_nonzero(tmp_path: Path) -> None:
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    evaluated = run_cli("evaluate", str(READY))
    after = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    assert evaluated.returncode == 0
    assert before == after
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"real_executor_invocation_gate_candidates": []}), encoding="utf-8")
    blocked = run_cli("evaluate", str(invalid))
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["status"] == "real_executor_invocation_gate_blocked"
