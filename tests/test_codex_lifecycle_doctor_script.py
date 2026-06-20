from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def test_cli_writes_deterministic_json_and_summary(tmp_path: Path) -> None:
    title = "[codex:landing] add Codex lifecycle doctor CLI"
    matrix = _write(tmp_path / "matrix.json", {"status": "passed", "required_failure_count": 0, "nonproof_count": 0, "diagnostic_failure_count": 0, "results": []})
    output = tmp_path / "codex_lifecycle_doctor_report.json"
    cmd = [sys.executable, "scripts/codex_lifecycle_doctor.py", "--title", title, "--intended-commit-title", title, "--matrix-json-path", str(matrix), "--output", str(output), "--summary"]
    first = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    first_payload = json.loads(output.read_text(encoding="utf-8"))
    second = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    second_payload = json.loads(output.read_text(encoding="utf-8"))
    assert first_payload == second_payload
    summary = json.loads(first.stdout)
    assert summary["overall_doctor_status"] == "doctor_ready"
    assert first_payload["non_authority_posture"]["doctor_does_not_rerun_commands"] is True


def test_cli_invalid_json_exits_cleanly(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    result = subprocess.run([sys.executable, "scripts/codex_lifecycle_doctor.py", "--title", "t", "--intended-commit-title", "t", "--matrix-json-path", str(bad)], check=False, capture_output=True, text=True)
    assert result.returncode == 2
    assert "codex_lifecycle_doctor_error" in result.stderr
