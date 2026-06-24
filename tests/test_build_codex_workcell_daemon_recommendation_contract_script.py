import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = "scripts/build_codex_workcell_daemon_recommendation_contract.py"


def run_cmd(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], text=True, capture_output=True)


def test_cli_writes_json_markdown_and_summary(tmp_path):
    output = tmp_path / "contract.json"
    markdown = tmp_path / "contract.md"
    result = run_cmd("--output", str(output), "--markdown-output", str(markdown), "--summary")
    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_text())
    summary = json.loads(result.stdout)
    assert data["daemon_recommendation_contract_id"] == "codex_workcell_daemon_recommendation_contract.v1"
    assert summary["recommendation_count"] == len(data["recommendation_catalog"])
    assert markdown.read_text().startswith("# Codex Workcell Daemon Recommendation Contract")


def test_cli_writes_supplied_inputs(tmp_path):
    pulse = tmp_path / "pulse.json"
    health = tmp_path / "health.json"
    pulse.write_text('{"observed_signal_summary":{"observed_signal_ids":["missing_finalizer_evidence"]}}')
    health.write_text('{"workcell_health_snapshot_id":"h"}')
    output = tmp_path / "contract.json"
    result = run_cmd("--output", str(output), "--pulse-contract-json", str(pulse), "--health-snapshot-json", str(health), "--summary")
    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_text())
    assert data["pulse_contract_input_summary"]["provided"] is True
    assert data["health_snapshot_input_summary"]["provided"] is True
    assert "provide_finalizer_evidence" in data["observed_recommendation_summary"]["applicable_recommendation_ids"]


def test_cli_clean_input_failures_exit_2(tmp_path):
    output = tmp_path / "out.json"
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    for args in [
        ("--output", str(output), "--pulse-contract-json", str(tmp_path / "missing-pulse.json")),
        ("--output", str(output), "--pulse-contract-json", str(bad)),
        ("--output", str(output), "--health-snapshot-json", str(tmp_path / "missing-health.json")),
        ("--output", str(output), "--health-snapshot-json", str(bad)),
    ]:
        result = run_cmd(*args)
        assert result.returncode == 2
        assert "codex_workcell_daemon_recommendation_contract_error" in result.stderr
