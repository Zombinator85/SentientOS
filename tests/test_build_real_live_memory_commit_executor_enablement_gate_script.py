from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURE = Path("tests/fixtures/real_live_memory_commit_executor_enablement_gate/ready_executor_enablement_candidate.json")
SCRIPT = Path("scripts/build_real_live_memory_commit_executor_enablement_gate.py")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, check=False)


def test_build_default_and_validate_policy() -> None:
    result = run_cli("build-default")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["validation"]["status"] == "valid"
    assert data["validation"]["invariants"]["real_executor_enablement_enabled"] is False

    result = run_cli("validate")
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "valid"


def test_evaluate_validate_and_summarize_fixture() -> None:
    for command in ("evaluate", "validate", "summarize"):
        result = run_cli(command, str(FIXTURE))
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["status"] == "executor_enablement_ready"


def test_inspect_fixture_prints_fixture_json() -> None:
    result = run_cli("inspect-fixture", "ready_executor_enablement_candidate")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["executor_enablement_candidates"][0]["candidate_type"] == "ai_capsule_executor_enablement_candidate"


def test_blocked_evaluate_exits_nonzero(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text())
    payload["executor_enablement_candidates"] = []
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload))
    result = run_cli("evaluate", str(bad))
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "executor_enablement_blocked"
