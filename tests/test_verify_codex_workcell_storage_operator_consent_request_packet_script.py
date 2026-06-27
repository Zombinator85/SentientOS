from __future__ import annotations

import json
import subprocess
import sys

import pytest

from sentientos.codex_workcell_storage_operator_consent_request_packet import INPUT_SPECS, build_codex_workcell_storage_operator_consent_request_packet, read_json_input

pytestmark = pytest.mark.no_legacy_skip


def _packet_path(tmp_path):
    summaries = {}
    reports = {}
    for input_id in INPUT_SPECS:
        path = tmp_path / f"{input_id}.json"
        path.write_text(json.dumps({"verification_status": "ok"}), encoding="utf-8")
        summary, report = read_json_input(str(path), input_id)
        summaries[input_id] = summary
        reports[input_id] = report
    packet = build_codex_workcell_storage_operator_consent_request_packet(input_summaries=summaries, input_reports=reports)
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet, sort_keys=True), encoding="utf-8")
    return path


def test_cli_writes_json_markdown_and_summary(tmp_path):
    packet = _packet_path(tmp_path)
    output = tmp_path / "out.json"
    markdown = tmp_path / "out.md"
    result = subprocess.run([sys.executable, "scripts/verify_codex_workcell_storage_operator_consent_request_packet.py", "--storage-operator-consent-request-packet-json", str(packet), "--output", str(output), "--markdown-output", str(markdown), "--summary"], check=True, text=True, capture_output=True)
    report = json.loads(output.read_text())
    assert report["verification_status"] == "storage_operator_consent_request_packet_verified"
    assert "storage_operator_consent_request_packet_verifier_id" in json.loads(result.stdout)
    assert markdown.read_text().startswith("# Codex Workcell Storage Operator Consent Request Packet Verifier")


def test_cli_json_output_is_deterministic(tmp_path):
    packet = _packet_path(tmp_path)
    out1 = tmp_path / "one.json"
    out2 = tmp_path / "two.json"
    base = [sys.executable, "scripts/verify_codex_workcell_storage_operator_consent_request_packet.py", "--storage-operator-consent-request-packet-json", str(packet)]
    subprocess.run(base + ["--output", str(out1)], check=True)
    subprocess.run(base + ["--output", str(out2)], check=True)
    assert out1.read_text() == out2.read_text()


@pytest.mark.parametrize("content", ["{", "[]"])
def test_cli_invalid_or_non_object_request_packet_exits_2(tmp_path, content):
    bad = tmp_path / "bad.json"
    bad.write_text(content, encoding="utf-8")
    result = subprocess.run([sys.executable, "scripts/verify_codex_workcell_storage_operator_consent_request_packet.py", "--storage-operator-consent-request-packet-json", str(bad), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert result.returncode == 2


def test_cli_missing_request_packet_path_exits_2(tmp_path):
    result = subprocess.run([sys.executable, "scripts/verify_codex_workcell_storage_operator_consent_request_packet.py", "--storage-operator-consent-request-packet-json", str(tmp_path / "missing.json"), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert result.returncode == 2


def test_cli_invalid_optional_context_json_exits_2(tmp_path):
    packet = _packet_path(tmp_path)
    bad = tmp_path / "bad_optional.json"
    bad.write_text("{", encoding="utf-8")
    result = subprocess.run([sys.executable, "scripts/verify_codex_workcell_storage_operator_consent_request_packet.py", "--storage-operator-consent-request-packet-json", str(packet), "--storage-policy-contract-json", str(bad), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert result.returncode == 2
