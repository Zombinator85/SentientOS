from __future__ import annotations

import json

import pytest
import subprocess
import sys

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = "scripts/build_codex_workcell_storage_operator_consent_response_contract.py"


def run_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, SCRIPT, *args], text=True, capture_output=True, check=False)


def test_cli_writes_json_markdown_and_summary(tmp_path) -> None:
    sample = tmp_path / "sample.json"
    sample.write_text('{"field":"value|with\\nnewline"}', encoding="utf-8")
    out = tmp_path / "out.json"
    md = tmp_path / "out.md"
    result = run_cmd("--output", str(out), "--storage-policy-contract-json", str(sample), "--commit-sha", "abc", "--pr-number", "9", "--pr-title", "Title", "--markdown-output", str(md), "--summary")
    assert result.returncode == 0, result.stderr
    data1 = out.read_text(encoding="utf-8")
    parsed = json.loads(data1)
    assert parsed["response_contract_context"]["commit_sha"] == "abc"
    assert parsed["response_artifact_not_created"] is True
    assert parsed["operator_response_present"] is False
    assert parsed["consent_not_collected"] is True
    assert parsed["consent_not_implied"] is True
    assert parsed["runtime_binding_not_performed"] is True
    assert parsed["writes_performed"] is False
    assert parsed["archives_performed"] is False
    assert parsed["memory_mutation_performed"] is False
    assert "storage_operator_consent_response_contract_id" in result.stdout
    assert md.read_text(encoding="utf-8").startswith("# Codex Workcell Storage Operator Consent Response Artifact Contract")
    out2 = tmp_path / "out2.json"
    result2 = run_cmd("--output", str(out2), "--storage-policy-contract-json", str(sample), "--commit-sha", "abc", "--pr-number", "9", "--pr-title", "Title")
    assert result2.returncode == 0
    assert data1 == out2.read_text(encoding="utf-8")


def test_cli_clean_input_errors_exit_2(tmp_path) -> None:
    out = tmp_path / "out.json"
    missing = run_cmd("--output", str(out), "--storage-policy-contract-json", str(tmp_path / "missing.json"))
    assert missing.returncode == 2
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{", encoding="utf-8")
    invalid = run_cmd("--output", str(out), "--storage-policy-contract-json", str(invalid_path))
    assert invalid.returncode == 2
    list_path = tmp_path / "list.json"
    list_path.write_text("[]", encoding="utf-8")
    non_object = run_cmd("--output", str(out), "--storage-policy-contract-json", str(list_path))
    assert non_object.returncode == 2
