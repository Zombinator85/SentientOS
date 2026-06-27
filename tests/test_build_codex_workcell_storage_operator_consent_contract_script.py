from __future__ import annotations

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.no_legacy_skip


def _run(args):
    return subprocess.run([sys.executable, "scripts/build_codex_workcell_storage_operator_consent_contract.py", *args], text=True, capture_output=True, check=False)


def test_cli_writes_json_summary_and_markdown(tmp_path):
    input_path = tmp_path / "policy.json"
    input_path.write_text('{"policy":"ok"}\n', encoding="utf-8")
    output = tmp_path / "contract.json"
    markdown = tmp_path / "contract.md"
    result = _run(["--output", str(output), "--storage-policy-contract-json", str(input_path), "--commit-sha", "abc", "--pr-number", "7", "--pr-title", "Title", "--markdown-output", str(markdown), "--summary"])
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["storage_operator_consent_contract_id"] == "codex_workcell_storage_operator_consent_contract.v1"
    assert summary["consent_not_collected"] is True
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["consent_context"]["supplied_report_count"] == 1
    assert report["operator_consent_present"] is False
    assert markdown.read_text(encoding="utf-8").startswith("# Codex Workcell Storage Operator Consent Request Contract")


def test_cli_invalid_missing_and_non_object_json_exit_2(tmp_path):
    output = tmp_path / "out.json"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{bad", encoding="utf-8")
    missing = tmp_path / "missing.json"
    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    for path, expected in ((invalid, "invalid_json"), (missing, "missing_json"), (array, "json_not_object")):
        result = _run(["--output", str(output), "--storage-policy-contract-json", str(path)])
        assert result.returncode == 2
        assert expected in result.stderr


def test_cli_output_and_markdown_are_deterministic_and_escaped(tmp_path):
    output1 = tmp_path / "one.json"
    output2 = tmp_path / "two.json"
    markdown1 = tmp_path / "one.md"
    markdown2 = tmp_path / "two.md"
    args = ["--commit-sha", "abc", "--pr-title", "Pipe | New\nLine"]
    first = _run(["--output", str(output1), "--markdown-output", str(markdown1), *args])
    second = _run(["--output", str(output2), "--markdown-output", str(markdown2), *args])
    assert first.returncode == 0
    assert second.returncode == 0
    assert output1.read_text(encoding="utf-8") == output2.read_text(encoding="utf-8")
    assert markdown1.read_text(encoding="utf-8") == markdown2.read_text(encoding="utf-8")
    assert "Pipe \\| New<br>Line" in markdown1.read_text(encoding="utf-8")


def test_cli_preserves_non_authority_posture(tmp_path):
    output = tmp_path / "contract.json"
    result = _run(["--output", str(output)])
    assert result.returncode == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    posture = report["non_authority_posture"]
    assert posture["storage_operator_consent_contract_does_not_collect_consent"] is True
    assert posture["storage_operator_consent_contract_does_not_bind_runtime_authority"] is True
    assert posture["storage_operator_consent_contract_does_not_write_ledger"] is True
    assert posture["storage_operator_consent_contract_does_not_archive_glow"] is True
    assert posture["storage_operator_consent_contract_does_not_modify_memory"] is True
    assert posture["storage_operator_consent_contract_does_not_trigger_daemon"] is True
    assert posture["storage_operator_consent_contract_does_not_create_tasks"] is True
    assert posture["storage_operator_consent_contract_does_not_schedule_tasks"] is True
    assert posture["storage_operator_consent_contract_does_not_decide_readiness"] is True
