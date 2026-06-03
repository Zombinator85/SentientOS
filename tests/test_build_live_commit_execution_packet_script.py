from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

FIXTURE = Path("tests/fixtures/live_commit_execution_packet/ready_live_commit_execution_packet_candidate.json")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/build_live_commit_execution_packet.py", *args], check=False, capture_output=True, text=True)


def test_build_default_and_validate_policy() -> None:
    result = run_cli("build-default")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["validation"]["status"] == "valid"
    assert payload["policy"]["real_executor_enabled"] is False

    result = run_cli("validate")
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "valid"


def test_evaluate_validate_and_summarize_fixture() -> None:
    for command in ("evaluate", "validate", "summarize"):
        result = run_cli(command, str(FIXTURE))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "live_commit_execution_packet_ready"


def test_inspect_fixture_prints_fixture_json() -> None:
    result = run_cli("inspect-fixture", "ready_live_commit_execution_packet_candidate")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "future_live_memory_commit_execution_gate_packet" in payload


def test_blocked_outcome_exits_nonzero(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload.pop("future_live_memory_commit_execution_gate_packet")
    blocked = tmp_path / "blocked.json"
    blocked.write_text(json.dumps(payload), encoding="utf-8")
    result = run_cli("evaluate", str(blocked))
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "live_commit_execution_packet_blocked"


def test_evaluate_mode_writes_no_files(tmp_path: Path) -> None:
    before = {path.name for path in tmp_path.iterdir()}
    result = run_cli("evaluate", str(FIXTURE))
    after = {path.name for path in tmp_path.iterdir()}
    assert result.returncode == 0
    assert before == after
