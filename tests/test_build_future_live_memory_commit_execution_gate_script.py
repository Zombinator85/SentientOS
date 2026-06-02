from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = Path("scripts/build_future_live_memory_commit_execution_gate.py")
FIXTURE = Path("tests/fixtures/future_live_memory_commit_execution_gate/ready_future_execution_gate_candidate.json")


def run_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_build_default_validate_and_inspect_fixture() -> None:
    default = run_cmd("build-default")
    assert default.returncode == 0
    assert json.loads(default.stdout)["validation"]["status"] == "valid"
    validate = run_cmd("validate")
    assert validate.returncode == 0
    inspect = run_cmd("inspect-fixture", "ready_future_execution_gate_candidate")
    assert inspect.returncode == 0
    assert json.loads(inspect.stdout)["future_execution_gate_candidates"][0]["candidate_type"] == "ai_capsule_future_execution_gate_candidate"


def test_evaluate_and_summarize_emit_deterministic_json() -> None:
    first = run_cmd("evaluate", str(FIXTURE))
    second = run_cmd("evaluate", str(FIXTURE))
    assert first.returncode == 0
    assert second.returncode == 0
    assert json.loads(first.stdout) == json.loads(second.stdout)
    summary = run_cmd("summarize", str(FIXTURE))
    assert summary.returncode == 0
    payload = json.loads(summary.stdout)
    assert payload["status"] == "future_execution_gate_ready"
    assert payload["summary_counts"]["candidate_count"] == 1


def test_blocked_evaluate_exits_nonzero(tmp_path: Path) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["future_execution_gate_candidates"] = []
    blocked = tmp_path / "blocked.json"
    blocked.write_text(json.dumps(data), encoding="utf-8")
    result = run_cmd("evaluate", str(blocked))
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "future_execution_gate_blocked"
