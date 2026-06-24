from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.no_legacy_skip
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/build_codex_workcell_vow_boundary_contract.py")

def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, check=False)

def test_cli_writes_json_summary_and_markdown(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps({"metadata_only": True, "non_authority_posture": {"safe": True}}), encoding="utf-8")
    output = tmp_path / "out.json"
    markdown = tmp_path / "out.md"
    result = _run("--output", str(output), "--health-snapshot-json", str(input_path), "--markdown-output", str(markdown), "--summary")
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    summary = json.loads(result.stdout)
    assert summary["vow_boundary_contract_id"] == "codex_workcell_vow_boundary_contract.v1"
    assert report["vow_gap_summary"]["supplied_report_count"] == 1
    assert markdown.read_text(encoding="utf-8").startswith("# Codex Workcell Vow Digest Boundary Contract")

def test_cli_invalid_json_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    result = _run("--output", str(tmp_path / "out.json"), "--architecture-json", str(bad))
    assert result.returncode == 2
    assert "invalid_architecture_json" in result.stderr

def test_cli_missing_input_path_exits_2(tmp_path: Path) -> None:
    result = _run("--output", str(tmp_path / "out.json"), "--architecture-json", str(tmp_path / "missing.json"))
    assert result.returncode == 2
    assert "missing_architecture_json" in result.stderr

def test_cli_non_object_json_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "list.json"
    bad.write_text("[]", encoding="utf-8")
    result = _run("--output", str(tmp_path / "out.json"), "--architecture-json", str(bad))
    assert result.returncode == 2
    assert "architecture_json_not_object" in result.stderr

def test_cli_json_and_markdown_are_deterministic(tmp_path: Path) -> None:
    input_path = tmp_path / "a|b.json"
    input_path.write_text(json.dumps({"metadata_only": True, "non_authority_posture": {"safe": True}, "text": "a|b\nc"}, sort_keys=True), encoding="utf-8")
    out1, out2 = tmp_path / "one.json", tmp_path / "two.json"
    md1, md2 = tmp_path / "one.md", tmp_path / "two.md"
    assert _run("--output", str(out1), "--architecture-json", str(input_path), "--markdown-output", str(md1)).returncode == 0
    assert _run("--output", str(out2), "--architecture-json", str(input_path), "--markdown-output", str(md2)).returncode == 0
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
    assert md1.read_text(encoding="utf-8") == md2.read_text(encoding="utf-8")
    assert "\\|" in md1.read_text(encoding="utf-8") or "a\\|b" in md1.read_text(encoding="utf-8")
