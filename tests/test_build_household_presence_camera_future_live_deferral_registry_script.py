from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = "scripts/build_household_presence_camera_future_live_deferral_registry.py"
FIXTURE = "tests/fixtures/household_presence_camera_future_live_deferral_registry/valid_future_live_review_deferred.json"
BLOCKED = "tests/fixtures/household_presence_camera_future_live_deferral_registry/missing_dry_run_gate_blocked.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, SCRIPT, *args], check=False, text=True, capture_output=True)


def test_build_default_and_validate() -> None:
    default = run_cli("build-default")
    assert default.returncode == 0
    assert json.loads(default.stdout)["policy"]["schema_version"].endswith(".v1")
    valid = run_cli("validate")
    assert valid.returncode == 0
    assert json.loads(valid.stdout)["ok"] is True


def test_evaluate_summarize_and_output(tmp_path: Path) -> None:
    output = tmp_path / "registry.json"
    result = run_cli("evaluate", "--input", FIXTURE, "--output", str(output))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "future_live_deferral_registry_ready"
    assert output.exists()
    summary = run_cli("summarize", "--input", FIXTURE)
    assert summary.returncode == 0
    assert json.loads(summary.stdout)["summary_counts"]["record_count"] == 1
    summary_flag = run_cli("evaluate", "--input", FIXTURE, "--summary")
    assert summary_flag.returncode == 0
    assert json.loads(summary_flag.stdout)["digest"]


def test_inspect_fixture_and_blocked_exit() -> None:
    inspected = run_cli("inspect-fixture", "--input", "valid_future_live_review_deferred.json")
    assert inspected.returncode == 0
    assert json.loads(inspected.stdout)["dry_run_gate"]["status"] == "dry_run_continuation_gate_ready"
    blocked = run_cli("evaluate", "--input", BLOCKED)
    assert blocked.returncode != 0
    assert json.loads(blocked.stdout)["status"] == "future_live_deferral_registry_blocked_missing_dry_run_gate"
