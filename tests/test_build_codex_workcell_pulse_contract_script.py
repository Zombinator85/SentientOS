from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = "scripts/build_codex_workcell_pulse_contract.py"


def test_cli_writes_json_and_summary(tmp_path: Path) -> None:
    output = tmp_path / "contract.json"
    result = subprocess.run([sys.executable, SCRIPT, "--output", str(output), "--summary"], text=True, capture_output=True, check=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    summary = json.loads(result.stdout)
    assert payload["pulse_contract_id"] == "codex_workcell_pulse_contract.v1"
    assert payload["health_snapshot_input_summary"]["provided"] is False
    assert summary["pulse_contract_only"] is True
    assert summary["signal_count"] >= 20


def test_cli_writes_markdown_when_requested(tmp_path: Path) -> None:
    output = tmp_path / "contract.json"
    markdown = tmp_path / "contract.md"
    subprocess.run([sys.executable, SCRIPT, "--output", str(output), "--markdown-output", str(markdown)], check=True)
    assert output.exists()
    assert markdown.read_text(encoding="utf-8").startswith("# Codex Workcell Pulse Contract")


def test_cli_maps_health_snapshot_and_returns_exit_code_2_on_failure(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"missing_inputs": ["matrix_json"], "observed_pressure_signals": [{"signal": "diagnostic_failures_nonproof"}]}, sort_keys=True), encoding="utf-8")
    output = tmp_path / "contract.json"
    subprocess.run([sys.executable, SCRIPT, "--output", str(output), "--health-snapshot-json", str(snapshot)], check=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "missing_matrix_evidence" in payload["observed_signal_summary"]["observed_signal_ids"]
    assert "matrix_diagnostic_failure_observed" in payload["observed_signal_summary"]["observed_signal_ids"]
    bad_output = tmp_path / "bad.json"
    result = subprocess.run([sys.executable, SCRIPT, "--output", str(bad_output), "--health-snapshot-json", str(tmp_path / "missing.json")], text=True, capture_output=True)
    assert result.returncode == 2
    assert "missing_health_snapshot_json" in result.stderr
    assert not bad_output.exists()
