from __future__ import annotations

import hashlib

import pytest

pytestmark = pytest.mark.no_legacy_skip
import json
import subprocess
import sys


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/build_codex_workcell_memory_contract.py", *args], text=True, capture_output=True, check=False)


def test_cli_writes_json_and_summary(tmp_path) -> None:
    input_path = tmp_path / "health.json"
    raw = b'{"workcell_health_snapshot_id":"h1"}\n'
    input_path.write_bytes(raw)
    output = tmp_path / "contract.json"
    result = run_script("--output", str(output), "--summary", "--health-snapshot-json", str(input_path))
    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_text(encoding="utf-8"))
    summary = json.loads(result.stdout)
    assert summary["workcell_memory_contract_id"] == "codex_workcell_memory_contract.v1"
    assert summary["provided_input_count"] == 1
    assert data["input_summaries"]["health_snapshot_json"]["digest"] == hashlib.sha256(raw).hexdigest()


def test_cli_writes_markdown_when_requested(tmp_path) -> None:
    output = tmp_path / "contract.json"
    markdown = tmp_path / "contract.md"
    result = run_script("--output", str(output), "--markdown-output", str(markdown))
    assert result.returncode == 0, result.stderr
    assert output.exists()
    assert markdown.read_text(encoding="utf-8").startswith("# Codex Workcell Memory Contract")
    assert "## /ledger receipt-chain contract" in markdown.read_text(encoding="utf-8")


def test_invalid_json_input_fails_with_exit_code_2(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = run_script("--output", str(tmp_path / "out.json"), "--health-snapshot-json", str(bad))
    assert result.returncode == 2
    assert "invalid_health_snapshot_json" in result.stderr


def test_missing_json_input_path_fails_with_exit_code_2(tmp_path) -> None:
    result = run_script("--output", str(tmp_path / "out.json"), "--health-snapshot-json", str(tmp_path / "missing.json"))
    assert result.returncode == 2
    assert "missing_health_snapshot_json" in result.stderr


def test_non_object_json_input_fails_with_exit_code_2(tmp_path) -> None:
    bad = tmp_path / "array.json"
    bad.write_text("[]", encoding="utf-8")
    result = run_script("--output", str(tmp_path / "out.json"), "--pulse-contract-json", str(bad))
    assert result.returncode == 2
    assert "pulse_contract_json_not_object" in result.stderr


def test_cli_json_and_markdown_are_deterministic(tmp_path) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text('{"stable": true}\n', encoding="utf-8")
    out1 = tmp_path / "one.json"
    out2 = tmp_path / "two.json"
    md1 = tmp_path / "one.md"
    md2 = tmp_path / "two.md"
    result1 = run_script("--output", str(out1), "--markdown-output", str(md1), "--evidence-index-json", str(input_path))
    result2 = run_script("--output", str(out2), "--markdown-output", str(md2), "--evidence-index-json", str(input_path))
    assert result1.returncode == 0, result1.stderr
    assert result2.returncode == 0, result2.stderr
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
    assert md1.read_text(encoding="utf-8") == md2.read_text(encoding="utf-8")
