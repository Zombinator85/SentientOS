from __future__ import annotations

import json
import subprocess
import sys

import pytest

from sentientos.codex_workcell_storage_operator_consent_response_contract import INPUT_SPECS, build_codex_workcell_storage_operator_consent_response_contract, omitted_input as contract_omitted_input

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = "scripts/verify_codex_workcell_storage_operator_consent_response_contract.py"


def _write_contract(tmp_path):
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(build_codex_workcell_storage_operator_consent_response_contract(input_summaries={k: contract_omitted_input(k) for k in INPUT_SPECS}), sort_keys=True), encoding="utf-8")
    return path


def test_cli_writes_json_summary_and_markdown(tmp_path) -> None:
    contract = _write_contract(tmp_path)
    output = tmp_path / "report.json"
    md = tmp_path / "report.md"
    proc = subprocess.run([sys.executable, SCRIPT, "--storage-operator-consent-response-contract-json", str(contract), "--output", str(output), "--markdown-output", str(md), "--summary"], check=True, text=True, capture_output=True)
    report = json.loads(output.read_text())
    summary = json.loads(proc.stdout)
    assert summary["verification_status"] == "storage_operator_consent_response_contract_verified"
    assert report["verification_status"] == "storage_operator_consent_response_contract_verified"
    assert "Codex Workcell Storage Operator Consent Response Artifact Verifier" in md.read_text()
    assert output.read_text() == output.read_text()
    assert md.read_text() == md.read_text()


@pytest.mark.parametrize("contents", ["{bad", "[]"])
def test_cli_invalid_or_non_object_response_contract_exits_2(tmp_path, contents: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(contents, encoding="utf-8")
    proc = subprocess.run([sys.executable, SCRIPT, "--storage-operator-consent-response-contract-json", str(path), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert proc.returncode == 2


def test_cli_missing_response_contract_path_exits_2(tmp_path) -> None:
    proc = subprocess.run([sys.executable, SCRIPT, "--storage-operator-consent-response-contract-json", str(tmp_path / "missing.json"), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert proc.returncode == 2


def test_cli_invalid_optional_context_json_exits_2(tmp_path) -> None:
    contract = _write_contract(tmp_path)
    bad = tmp_path / "optional.json"
    bad.write_text("{bad", encoding="utf-8")
    proc = subprocess.run([sys.executable, SCRIPT, "--storage-operator-consent-response-contract-json", str(contract), "--storage-policy-contract-json", str(bad), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert proc.returncode == 2
