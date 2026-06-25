from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_legacy_skip

import json
import subprocess
import sys

from sentientos.codex_workcell_storage_policy_contract import build_codex_workcell_storage_policy_contract

SCRIPT = "scripts/verify_codex_workcell_storage_policy_contract.py"


def _write(path, data):
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


def test_cli_writes_json_markdown_and_summary(tmp_path):
    policy = tmp_path / "policy.json"
    output = tmp_path / "out.json"
    markdown = tmp_path / "out.md"
    _write(policy, build_codex_workcell_storage_policy_contract())
    proc = subprocess.run([sys.executable, SCRIPT, "--storage-policy-contract-json", str(policy), "--output", str(output), "--markdown-output", str(markdown), "--summary"], text=True, capture_output=True, check=True)
    assert "storage_policy_verified" in proc.stdout
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["verification_status"] == "storage_policy_verified"
    assert markdown.read_text(encoding="utf-8").startswith("# Codex Workcell Storage Policy Verifier")


def test_cli_invalid_storage_policy_json_exits_2(tmp_path):
    policy = tmp_path / "policy.json"
    policy.write_text("{", encoding="utf-8")
    proc = subprocess.run([sys.executable, SCRIPT, "--storage-policy-contract-json", str(policy), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert proc.returncode == 2
    assert "invalid_json" in proc.stderr


def test_cli_missing_storage_policy_path_exits_2(tmp_path):
    proc = subprocess.run([sys.executable, SCRIPT, "--storage-policy-contract-json", str(tmp_path / "missing.json"), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert proc.returncode == 2
    assert "missing_json" in proc.stderr


def test_cli_non_object_storage_policy_json_exits_2(tmp_path):
    policy = tmp_path / "policy.json"
    policy.write_text("[]", encoding="utf-8")
    proc = subprocess.run([sys.executable, SCRIPT, "--storage-policy-contract-json", str(policy), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert proc.returncode == 2
    assert "json_not_object" in proc.stderr


def test_cli_invalid_optional_context_json_exits_2(tmp_path):
    policy = tmp_path / "policy.json"
    opt = tmp_path / "opt.json"
    _write(policy, build_codex_workcell_storage_policy_contract())
    opt.write_text("{", encoding="utf-8")
    proc = subprocess.run([sys.executable, SCRIPT, "--storage-policy-contract-json", str(policy), "--vow-boundary-contract-json", str(opt), "--output", str(tmp_path / "out.json")], text=True, capture_output=True)
    assert proc.returncode == 2
    assert "invalid_json:vow_boundary_contract_json" in proc.stderr


def test_cli_json_output_is_deterministic(tmp_path):
    policy = tmp_path / "policy.json"
    out1 = tmp_path / "out1.json"
    out2 = tmp_path / "out2.json"
    _write(policy, build_codex_workcell_storage_policy_contract())
    for out in (out1, out2):
        subprocess.run([sys.executable, SCRIPT, "--storage-policy-contract-json", str(policy), "--output", str(out)], check=True)
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
