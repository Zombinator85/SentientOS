from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.no_legacy_skip
import subprocess
import sys


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/build_codex_workcell_storage_policy_contract.py", *args], text=True, capture_output=True, check=False)


def test_cli_writes_json_markdown_and_summary(tmp_path) -> None:
    output = tmp_path / "contract.json"
    markdown = tmp_path / "contract.md"
    result = run_cli("--output", str(output), "--markdown-output", str(markdown), "--summary")
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["storage_policy_contract_id"] == "codex_workcell_storage_policy_contract.v1"
    assert report["storage_activation_gap_summary"]["active_storage_allowed_now"] is False
    assert markdown.read_text(encoding="utf-8").startswith("# Codex Workcell Storage Policy Contract")
    summary = json.loads(result.stdout)
    assert summary["storage_policy_contract_only"] is True


def test_cli_json_output_is_deterministic(tmp_path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    assert run_cli("--output", str(first)).returncode == 0
    assert run_cli("--output", str(second)).returncode == 0
    assert first.read_bytes() == second.read_bytes()


def test_cli_markdown_output_is_deterministic(tmp_path) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    assert run_cli("--output", str(tmp_path / "a.json"), "--markdown-output", str(first)).returncode == 0
    assert run_cli("--output", str(tmp_path / "b.json"), "--markdown-output", str(second)).returncode == 0
    assert first.read_bytes() == second.read_bytes()


def test_cli_invalid_json_missing_path_and_non_object_exit_2(tmp_path) -> None:
    output = tmp_path / "out.json"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")
    missing = tmp_path / "missing.json"
    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    assert run_cli("--output", str(output), "--vow-boundary-contract-json", str(invalid)).returncode == 2
    assert run_cli("--output", str(output), "--vow-boundary-contract-json", str(missing)).returncode == 2
    assert run_cli("--output", str(output), "--vow-boundary-contract-json", str(array)).returncode == 2


def test_cli_records_supplied_input_digest(tmp_path) -> None:
    vow = tmp_path / "vow.json"
    vow.write_text(json.dumps({"vow_boundary_contract_id": "v", "canonical_vow_digest": "d"}, sort_keys=True), encoding="utf-8")
    output = tmp_path / "out.json"
    result = run_cli("--output", str(output), "--vow-boundary-contract-json", str(vow))
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["input_summaries"]["vow_boundary_contract_json"]["provided"] is True
    assert report["input_summaries"]["vow_boundary_contract_json"]["byte_size"] == len(vow.read_bytes())
