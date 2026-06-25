from __future__ import annotations

import json

import pytest
import subprocess
import sys

from sentientos.codex_workcell_vow_boundary_contract import build_codex_workcell_vow_boundary_contract

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = "scripts/build_codex_workcell_vow_alignment_attestation.py"


def _write(path, data):
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


def _vow(tmp_path):
    path = tmp_path / "vow.json"
    _write(path, build_codex_workcell_vow_boundary_contract())
    return path


def test_required_vow_boundary_contract_input_is_enforced(tmp_path):
    out = tmp_path / "out.json"
    result = subprocess.run([sys.executable, SCRIPT, "--output", str(out)], text=True, capture_output=True)
    assert result.returncode != 0


def test_cli_writes_json_markdown_and_summary(tmp_path):
    vow = _vow(tmp_path)
    report = tmp_path / "arch.json"
    _write(report, {"metadata_only": True, "non_authority_posture": {"x": True}, "architecture_id": "a"})
    out = tmp_path / "out.json"
    md = tmp_path / "out.md"
    result = subprocess.run([sys.executable, SCRIPT, "--vow-boundary-contract-json", str(vow), "--architecture-json", str(report), "--output", str(out), "--markdown-output", str(md), "--summary"], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(out.read_text())
    assert data["attestation_records"][0]["input_id"] == "architecture_json"
    assert md.read_text().startswith("# Codex Workcell Vow Alignment Attestation Bundle")
    assert json.loads(result.stdout)["supplied_report_count"] == 1


def test_invalid_missing_and_non_object_json_exit_2(tmp_path):
    vow = _vow(tmp_path)
    for name, content, args in [
        ("bad.json", "{", ["--architecture-json"]),
        ("list.json", "[]", ["--architecture-json"]),
    ]:
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        result = subprocess.run([sys.executable, SCRIPT, "--vow-boundary-contract-json", str(vow), *args, str(path), "--output", str(tmp_path / f"{name}.out")], text=True, capture_output=True)
        assert result.returncode == 2
    result = subprocess.run([sys.executable, SCRIPT, "--vow-boundary-contract-json", str(vow), "--architecture-json", str(tmp_path / "missing.json"), "--output", str(tmp_path / "missing.out")], text=True, capture_output=True)
    assert result.returncode == 2


def test_json_output_is_deterministic(tmp_path):
    vow = _vow(tmp_path)
    out1 = tmp_path / "one.json"
    out2 = tmp_path / "two.json"
    cmd = [sys.executable, SCRIPT, "--vow-boundary-contract-json", str(vow)]
    assert subprocess.run([*cmd, "--output", str(out1)], capture_output=True).returncode == 0
    assert subprocess.run([*cmd, "--output", str(out2)], capture_output=True).returncode == 0
    assert out1.read_text() == out2.read_text()
