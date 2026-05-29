from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = "scripts/build_selective_memory_distillation_receipt_gate.py"
FIXTURE = "tests/fixtures/selective_memory_distillation_receipt_gate/valid_dual_capsule_write_receipt_candidate.json"
BLOCKED = "tests/fixtures/selective_memory_distillation_receipt_gate/missing_distillation_packet_blocked.json"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, SCRIPT, *args], check=False, text=True, capture_output=True)


def test_build_default_and_validate() -> None:
    default = _run("build-default")
    assert default.returncode == 0
    assert json.loads(default.stdout)["policy"]["schema_version"] == "selective-memory-distillation-receipt-gate.v1"
    validate = _run("validate")
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["ok"] is True


def test_evaluate_summarize_and_output(tmp_path: Path) -> None:
    output = tmp_path / "receipt_gate.json"
    result = _run("evaluate", "--input", FIXTURE, "--output", str(output))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "selective_memory_receipt_gate_ready"
    assert output.exists()
    summary = _run("summarize", "--input", FIXTURE)
    assert summary.returncode == 0
    assert json.loads(summary.stdout)["summary_counts"]["candidate_count"] == 1


def test_inspect_fixture() -> None:
    result = _run("inspect-fixture", "--fixture", "valid_noop_receipt_candidate.json")
    assert result.returncode == 0
    assert "receipt_candidate" in json.loads(result.stdout)


def test_blocked_evaluate_exits_nonzero() -> None:
    result = _run("evaluate", "--input", BLOCKED)
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "selective_memory_receipt_gate_blocked_missing_distillation_packet"
