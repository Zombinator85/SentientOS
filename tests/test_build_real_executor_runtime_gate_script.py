from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

FIXTURE = Path("tests/fixtures/real_executor_runtime_gate/ready_runtime_gate_candidate.json")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/build_real_executor_runtime_gate.py", *args], check=False, capture_output=True, text=True)


def test_build_default_and_validate_policy() -> None:
    result = run_cli("build-default")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["validation"]["status"] == "valid"
    assert payload["policy"]["metadata_only"] is True
    assert payload["policy"]["real_executor_enabled"] is False
    result = run_cli("validate")
    assert result.returncode == 0, result.stderr


def test_evaluate_emits_deterministic_json_and_writes_nothing() -> None:
    before = {p.name: p.stat().st_mtime_ns for p in FIXTURE.parent.iterdir()}
    first = run_cli("evaluate", str(FIXTURE))
    second = run_cli("evaluate", str(FIXTURE))
    after = {p.name: p.stat().st_mtime_ns for p in FIXTURE.parent.iterdir()}
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)
    assert before == after
    assert json.loads(first.stdout)["packet"]["real_executor_enabled"] is False


def test_summarize_and_inspect_fixture() -> None:
    summary = run_cli("summarize", str(FIXTURE))
    assert summary.returncode == 0, summary.stderr
    payload = json.loads(summary.stdout)
    assert payload["status"] == "runtime_gate_ready"
    assert payload["packet_digest"].startswith("sha256:")
    inspected = run_cli("inspect-fixture", "ready_runtime_gate_candidate")
    assert inspected.returncode == 0, inspected.stderr
    assert "runtime_enablement_packet" in json.loads(inspected.stdout)


def test_validate_packet_blocks_nonzero_for_invalid_input(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"runtime_gate_candidates": []}), encoding="utf-8")
    result = run_cli("validate", str(invalid))
    assert result.returncode == 1
    assert "missing_runtime_enablement_packet" in result.stdout
