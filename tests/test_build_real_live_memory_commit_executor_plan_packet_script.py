from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

FIXTURE = Path("tests/fixtures/real_live_memory_commit_executor_plan_packet/valid_ai_capsule_executor_plan_candidate.json")
BLOCKED = Path("tests/fixtures/real_live_memory_commit_executor_plan_packet/runtime_execution_gate_digest_mismatch_blocked.json")
SCRIPT = Path("scripts/build_real_live_memory_commit_executor_plan_packet.py")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_build_default_and_validate_policy() -> None:
    result = _run("build-default")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["validation"]["status"] == "valid"
    assert payload["policy"]["default_posture"] == "deny"
    assert payload["policy"]["live_executor_enabled"] is False
    result = _run("validate")
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "valid"


def test_evaluate_validate_and_summarize_fixture() -> None:
    for command in ("evaluate", "validate"):
        result = _run(command, str(FIXTURE))
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["status"] == "executor_plan_ready"
        assert payload["packet"]["live_executor_enabled"] is False
    summary = _run("summarize", str(FIXTURE))
    assert summary.returncode == 0
    payload = json.loads(summary.stdout)
    assert payload["status"] == "executor_plan_ready"
    assert payload["summary_counts"]["operation_count"] == 1
    assert payload["packet_digest"].startswith("sha256:")


def test_blocked_outcomes_exit_nonzero() -> None:
    result = _run("evaluate", str(BLOCKED))
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "executor_plan_blocked"
    assert payload["report"]["findings"][0]["code"] == "runtime_execution_gate_digest_mismatch"
    summary = _run("summarize", str(BLOCKED))
    assert summary.returncode == 1


def test_inspect_fixture_prints_fixture_json() -> None:
    result = _run("inspect-fixture", "valid_ai_capsule_executor_plan_candidate")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "explicit_live_memory_runtime_execution_gate_packet" in payload
    assert payload["executor_plan_candidates"][0]["candidate_type"] == "ai_capsule_executor_plan_candidate"


def test_script_does_not_launch_external_processes_or_write_memory() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    forbidden = ["subprocess", "requests.", "write_text(", "unlink(", "remove(", "prompt_assembler", "openai"]
    assert not any(marker in text for marker in forbidden)
