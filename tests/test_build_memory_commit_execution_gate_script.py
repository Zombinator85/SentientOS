from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/memory_commit_execution_gate")
SCRIPT = Path("scripts/build_memory_commit_execution_gate.py")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_build_default_and_validate_emit_deterministic_json() -> None:
    default = _run("build-default")
    assert default.returncode == 0, default.stderr
    assert json.loads(default.stdout)["policy"]["default_execution_posture"] == "deny"
    validate = _run("validate")
    assert validate.returncode == 0, validate.stderr
    assert json.loads(validate.stdout)["status"] == "valid"


def test_evaluate_summary_and_output_file(tmp_path: Path) -> None:
    output = tmp_path / "gate.json"
    result = _run("evaluate", "--input", str(FIXTURES / "valid_ai_capsule_commit_execution_candidate.json"), "--output", str(output), "--summary")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "memory_commit_execution_gate_ready"
    assert data["packet_digest"].startswith("sha256:")
    assert json.loads(output.read_text(encoding="utf-8")) == data


def test_blocked_fixture_exits_nonzero() -> None:
    result = _run("evaluate", "--input", str(FIXTURES / "live_write_claim_blocked.json"), "--summary")
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "memory_commit_execution_gate_blocked_live_write_claim"


def test_summarize_and_inspect_fixture() -> None:
    summary = _run("summarize", "--input", str(FIXTURES / "mixed_memory_commit_execution_gate_packet.json"))
    assert summary.returncode == 0, summary.stderr
    assert json.loads(summary.stdout)["summary_counts"]["candidate_count"] == 2
    inspected = _run("inspect-fixture", "--fixtures-dir", str(FIXTURES), "--fixture-name", "valid_noop_commit_execution_candidate.json")
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)["execution_candidate"]["candidate_type"] == "noop_commit_execution_candidate"
