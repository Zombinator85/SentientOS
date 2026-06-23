from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = "scripts/build_codex_workcell_health_snapshot.py"


def test_cli_writes_json_and_summary(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"; matrix.write_text('{"status":"ok"}', encoding="utf-8")
    output = tmp_path / "snapshot.json"
    result = subprocess.run([sys.executable, SCRIPT, "--output", str(output), "--matrix-json", str(matrix), "--summary"], text=True, capture_output=True, check=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    summary = json.loads(result.stdout)
    assert payload["proof_summary"]["matrix_status"] == "ok"
    assert summary["workcell_health_snapshot_id"] == "codex_workcell_health_snapshot.v1"
    assert summary["supplied_input_count"] == 1


def test_cli_writes_markdown(tmp_path: Path) -> None:
    output = tmp_path / "snapshot.json"
    markdown = tmp_path / "snapshot.md"
    subprocess.run([sys.executable, SCRIPT, "--output", str(output), "--markdown-output", str(markdown)], check=True)
    assert output.exists()
    assert markdown.read_text(encoding="utf-8").startswith("# Codex Workcell Health Snapshot")


def test_cli_failure_returns_exit_code_2_with_useful_message(tmp_path: Path) -> None:
    output = tmp_path / "snapshot.json"
    result = subprocess.run([sys.executable, SCRIPT, "--output", str(output), "--matrix-json", str(tmp_path / "missing.json")], text=True, capture_output=True)
    assert result.returncode == 2
    assert "missing_json:matrix_json" in result.stderr
    assert not output.exists()
