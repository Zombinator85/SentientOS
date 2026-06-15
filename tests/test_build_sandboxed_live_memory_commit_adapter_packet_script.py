from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/build_sandboxed_live_memory_commit_adapter_packet.py")
FIXTURE = Path("tests/fixtures/sandboxed_live_memory_commit_adapter_packet/ready_sandboxed_live_memory_commit_adapter_packet_candidate.json")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_build_default_outputs_valid_policy() -> None:
    result = run_cli("build-default")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["validation"]["status"] == "valid"
    assert data["fixture_root"] == "tests/fixtures/sandboxed_live_memory_commit_adapter_packet"


def test_evaluate_ready_fixture_outputs_packet() -> None:
    result = run_cli("evaluate", str(FIXTURE))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "sandboxed_live_memory_commit_adapter_packet_ready"
    assert data["packet"]["future_sandboxed_live_memory_commit_adapter_envelope_required"] is True


def test_validate_blocked_fixture_exits_nonzero() -> None:
    blocked = Path("tests/fixtures/sandboxed_live_memory_commit_adapter_packet/live_write_claim_blocked.json")
    result = run_cli("validate", str(blocked))
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "sandboxed_live_memory_commit_adapter_packet_blocked"


def test_summarize_outputs_counts_and_findings() -> None:
    result = run_cli("summarize", str(FIXTURE))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "sandboxed_live_memory_commit_adapter_packet_ready"
    assert data["summary_counts"]["candidate_count"] == 1


def test_inspect_fixture_accepts_short_name() -> None:
    result = run_cli("inspect-fixture", "ready_sandboxed_live_memory_commit_adapter_packet_candidate")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "sandboxed_live_memory_commit_adapter_packet_candidates" in data
