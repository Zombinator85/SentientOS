from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = Path("scripts/build_real_executor_execution_preflight_gate.py")
FIXTURE_ROOT = Path("tests/fixtures/real_executor_execution_preflight_gate")
READY = FIXTURE_ROOT / "ready_real_executor_execution_preflight_gate_candidate.json"
NOOP = FIXTURE_ROOT / "noop_real_executor_execution_preflight_gate_candidate.json"
MIXED = FIXTURE_ROOT / "mixed_real_executor_execution_preflight_gate_candidate.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], check=False, text=True, capture_output=True)


def test_build_default_and_validate_policy() -> None:
    built = run_cli("build-default")
    assert built.returncode == 0, built.stderr
    payload = json.loads(built.stdout)
    assert payload["policy"]["metadata_only"] is True
    assert payload["validation"]["status"] == "valid"

    validated = run_cli("validate")
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["status"] == "valid"


def test_evaluate_validate_and_summarize_fixture() -> None:
    evaluated = run_cli("evaluate", str(READY))
    assert evaluated.returncode == 0, evaluated.stderr
    payload = json.loads(evaluated.stdout)
    assert payload["status"] == "real_executor_execution_preflight_gate_ready"

    validated = run_cli("validate", str(READY))
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout) == payload

    summarized = run_cli("summarize", str(READY))
    assert summarized.returncode == 0, summarized.stderr
    summary = json.loads(summarized.stdout)
    assert summary["status"] == "real_executor_execution_preflight_gate_ready"
    assert summary["packet_digest"].startswith("sha256:")
    assert summary["summary_counts"]["candidate_count"] == 1


def test_noop_mixed_and_inspect_fixture() -> None:
    noop = run_cli("evaluate", str(NOOP))
    mixed = run_cli("evaluate", str(MIXED))
    assert noop.returncode == 0, noop.stderr
    assert mixed.returncode == 0, mixed.stderr
    assert json.loads(noop.stdout)["status"] == "real_executor_execution_preflight_gate_noop"
    assert json.loads(mixed.stdout)["status"] == "real_executor_execution_preflight_gate_ready_with_warnings"

    inspected = run_cli("inspect-fixture", READY.name)
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout) == json.loads(READY.read_text(encoding="utf-8"))


def test_blocked_outcome_exits_nonzero(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked.json"
    blocked.write_text(json.dumps({"real_executor_execution_preflight_gate_candidates": []}), encoding="utf-8")
    result = run_cli("evaluate", str(blocked))
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "real_executor_execution_preflight_gate_blocked"
