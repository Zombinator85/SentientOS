from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIX = "tests/fixtures/household_presence_camera_operator_grant_renewal_request_packet"
SCRIPT = "scripts/build_household_presence_camera_operator_grant_renewal_request_packet.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, SCRIPT, *args], check=False, capture_output=True, text=True)


def test_cli_build_default_validate_evaluate_summarize_and_inspect(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    out = tmp_path / "out.json"
    assert run("build-default", "--output", str(policy)).returncode == 0
    assert run("validate", "--input", str(policy)).returncode == 0
    assert run("evaluate", "--input", f"{FIX}/valid_operator_grant_renewal_request.json", "--output", str(out)).returncode == 0
    assert run("summarize", "--input", str(out)).returncode == 0
    assert run("inspect-fixture", "--fixtures-dir", FIX, "--input", "valid_operator_grant_renewal_request.json").returncode == 0


def test_cli_nonzero_for_blocked_and_deterministic_summary() -> None:
    blocked = run("evaluate", "--input", f"{FIX}/missing_trend_ledger_blocked.json")
    assert blocked.returncode == 1
    one = run("evaluate", "--input", f"{FIX}/mixed_request_packet.json", "--summary")
    two = run("evaluate", "--input", f"{FIX}/mixed_request_packet.json", "--summary")
    assert one.returncode == 0
    assert json.loads(one.stdout) == json.loads(two.stdout)
