from __future__ import annotations

import hashlib
import json

import pytest
import subprocess
import sys
from pathlib import Path


pytestmark = pytest.mark.no_legacy_skip
SCRIPT = Path("scripts/build_codex_workcell_storage_operator_consent_request_presentation_contract.py")


def run_builder(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, check=False)


def test_cli_writes_json_markdown_and_summary_with_input_digest(tmp_path: Path):
    sample = tmp_path / "packet|name.json"
    raw = b'{"field":"value|with\\nnewline"}'
    sample.write_bytes(raw)
    output = tmp_path / "contract.json"
    markdown = tmp_path / "contract.md"
    result = run_builder("--output", str(output), "--storage-operator-consent-request-packet-json", str(sample), "--commit", "abc", "--pr", "9", "--markdown-output", str(markdown), "--summary")
    assert result.returncode == 0, result.stderr
    assert "storage_operator_consent_request_presentation_contract_id" in result.stdout
    contract = json.loads(output.read_text())
    summary = contract["input_summaries"]["storage_operator_consent_request_packet_json"]
    assert summary["provided"] is True
    assert summary["digest"] == hashlib.sha256(raw).hexdigest()
    assert summary["byte_size"] == len(raw)
    assert contract["presentation_boundary_context"]["supplied_input_count"] == 1
    assert markdown.read_text() == markdown.read_text()
    assert "\\|" in markdown.read_text()


def test_cli_rejects_invalid_missing_and_non_object_json(tmp_path: Path):
    output = tmp_path / "out.json"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{")
    assert run_builder("--output", str(output), "--storage-operator-consent-request-packet-json", str(invalid)).returncode == 2
    assert run_builder("--output", str(output), "--storage-operator-consent-request-packet-json", str(tmp_path / "missing.json")).returncode == 2
    array = tmp_path / "array.json"
    array.write_text("[]")
    assert run_builder("--output", str(output), "--storage-operator-consent-request-packet-json", str(array)).returncode == 2


def test_cli_json_output_is_deterministic(tmp_path: Path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    assert run_builder("--output", str(first)).returncode == 0
    assert run_builder("--output", str(second)).returncode == 0
    assert first.read_text() == second.read_text()
    contract = json.loads(first.read_text())
    denied = {row["inference_id"] for row in contract["denied_inferences"]}
    assert "operator_silence_implies_consent" in denied
    assert "message_delivered_implies_consent" in denied
    assert "finalizer_ready_implies_presentation_authority" in denied
    assert "daemon_recommendation_implies_presentation_authority" in denied
