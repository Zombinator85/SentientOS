from __future__ import annotations

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_runtime_authority_contract import INPUT_SPECS, build_codex_workcell_storage_runtime_authority_contract, omitted_input as contract_omitted

SCRIPT = "scripts/verify_codex_workcell_storage_runtime_authority_contract.py"


def _contract_path(tmp_path):
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(build_codex_workcell_storage_runtime_authority_contract(input_summaries={i: contract_omitted(i) for i in INPUT_SPECS}), sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_cli_writes_json_markdown_and_summary(tmp_path):
    contract = _contract_path(tmp_path); out = tmp_path / "out.json"; md = tmp_path / "out.md"
    result = subprocess.run([sys.executable, SCRIPT, "--storage-runtime-authority-contract-json", str(contract), "--output", str(out), "--markdown-output", str(md), "--summary"], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verification_status"] == "storage_runtime_authority_contract_verified"
    summary = json.loads(result.stdout)
    assert summary["verification_status"] == "storage_runtime_authority_contract_verified"
    assert md.read_text(encoding="utf-8").startswith("# Codex Workcell Storage Runtime Authority Boundary Verifier")


@pytest.mark.parametrize("content", ["{", "[]"])
def test_cli_invalid_or_non_object_contract_exits_2(tmp_path, content):
    contract = tmp_path / "bad.json"; contract.write_text(content, encoding="utf-8")
    result = subprocess.run([sys.executable, SCRIPT, "--storage-runtime-authority-contract-json", str(contract), "--output", str(tmp_path / "out.json")], text=True, capture_output=True, check=False)
    assert result.returncode == 2


def test_cli_missing_contract_path_exits_2(tmp_path):
    result = subprocess.run([sys.executable, SCRIPT, "--storage-runtime-authority-contract-json", str(tmp_path / "missing.json"), "--output", str(tmp_path / "out.json")], text=True, capture_output=True, check=False)
    assert result.returncode == 2


def test_cli_invalid_optional_context_json_exits_2(tmp_path):
    contract = _contract_path(tmp_path); bad = tmp_path / "bad_optional.json"; bad.write_text("{", encoding="utf-8")
    result = subprocess.run([sys.executable, SCRIPT, "--storage-runtime-authority-contract-json", str(contract), "--storage-policy-contract-json", str(bad), "--output", str(tmp_path / "out.json")], text=True, capture_output=True, check=False)
    assert result.returncode == 2
