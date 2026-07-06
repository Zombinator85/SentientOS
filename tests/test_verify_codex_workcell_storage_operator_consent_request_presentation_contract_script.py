from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_workcell_storage_operator_consent_request_presentation_contract import INPUT_SPECS, build_codex_workcell_storage_operator_consent_request_presentation_contract, omitted_input

SCRIPT = Path("scripts/verify_codex_workcell_storage_operator_consent_request_presentation_contract.py")

def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, check=False)

def write_contract(path: Path) -> None:
    path.write_text(json.dumps(build_codex_workcell_storage_operator_consent_request_presentation_contract(input_summaries={k: omitted_input(k) for k in INPUT_SPECS}), sort_keys=True))

def test_canonical_and_legacy_cli_flags_write_deterministic_json_markdown_and_summary(tmp_path: Path):
    contract = tmp_path / "contract.json"; write_contract(contract)
    out = tmp_path / "report.json"; md = tmp_path / "report.md"
    result = run_cli("--storage-operator-consent-request-presentation-contract-json", str(contract), "--output", str(out), "--markdown-output", str(md), "--summary")
    assert result.returncode == 0, result.stderr
    report = json.loads(out.read_text())
    assert report["verification_status"] == "storage_operator_consent_request_presentation_contract_verified"
    assert report["input_summaries"]["presentation_contract_json"]["byte_size"] == contract.stat().st_size
    assert "Presentation contract summary" in md.read_text()
    out2 = tmp_path / "report2.json"
    assert run_cli("--presentation-contract-json", str(contract), "--output", str(out2)).returncode == 0
    assert json.loads(out2.read_text())["verification_status"] == report["verification_status"]
    out3 = tmp_path / "report3.json"
    assert run_cli("--storage-operator-consent-request-presentation-contract-json", str(contract), "--presentation-contract-json", str(contract), "--output", str(out3)).returncode == 0

def test_cli_rejects_conflicting_missing_invalid_non_object_and_optional_json(tmp_path: Path):
    out = tmp_path / "report.json"
    c1 = tmp_path / "c1.json"; c2 = tmp_path / "c2.json"; write_contract(c1); write_contract(c2)
    assert run_cli("--storage-operator-consent-request-presentation-contract-json", str(c1), "--presentation-contract-json", str(c2), "--output", str(out)).returncode == 2
    assert run_cli("--output", str(out)).returncode == 2
    assert run_cli("--storage-operator-consent-request-presentation-contract-json", str(tmp_path / "missing.json"), "--output", str(out)).returncode == 2
    invalid = tmp_path / "invalid.json"; invalid.write_text("{")
    assert run_cli("--storage-operator-consent-request-presentation-contract-json", str(invalid), "--output", str(out)).returncode == 2
    array = tmp_path / "array.json"; array.write_text("[]")
    assert run_cli("--storage-operator-consent-request-presentation-contract-json", str(array), "--output", str(out)).returncode == 2
    bad_optional = tmp_path / "bad_optional.json"; bad_optional.write_text("{")
    assert run_cli("--storage-operator-consent-request-presentation-contract-json", str(c1), "--storage-operator-consent-request-packet-json", str(bad_optional), "--output", str(out)).returncode == 2
