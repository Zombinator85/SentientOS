from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

FIXTURE = Path("tests/fixtures/constrained_executor_enablement_path_packet/ready_constrained_enable_path_candidate.json")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/build_constrained_executor_enablement_path_packet.py", *args],
        check=False,
        text=True,
        capture_output=True,
    )


def test_build_default_and_validate_policy() -> None:
    result = run_cli("build-default")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["validation"]["status"] == "valid"
    assert payload["policy"]["default_posture"] == "deny"
    validate = run_cli("validate")
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["status"] == "valid"


def test_evaluate_emits_deterministic_json_and_writes_nothing(tmp_path: Path) -> None:
    before = {path.name for path in tmp_path.iterdir()}
    first = run_cli("evaluate", str(FIXTURE))
    second = run_cli("evaluate", str(FIXTURE))
    assert first.returncode == 0
    assert second.returncode == 0
    assert json.loads(first.stdout) == json.loads(second.stdout)
    assert json.loads(first.stdout)["status"] == "constrained_enable_path_ready"
    assert {path.name for path in tmp_path.iterdir()} == before


def test_validate_packet_and_summarize() -> None:
    validate = run_cli("validate", str(FIXTURE))
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["packet"]["real_executor_enabled"] is False
    summary = run_cli("summarize", str(FIXTURE))
    assert summary.returncode == 0
    payload = json.loads(summary.stdout)
    assert payload["status"] == "constrained_enable_path_ready"
    assert payload["packet_digest"].startswith("sha256:")
    assert payload["summary_counts"]["candidate_count"] == 1


def test_inspect_fixture() -> None:
    result = run_cli("inspect-fixture", "ready_constrained_enable_path_candidate")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "constrained_enable_path_candidates" in payload


def test_blocked_outcomes_exit_nonzero(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"constrained_enable_path_candidates": []}), encoding="utf-8")
    result = run_cli("evaluate", str(bad))
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "constrained_enable_path_blocked"
