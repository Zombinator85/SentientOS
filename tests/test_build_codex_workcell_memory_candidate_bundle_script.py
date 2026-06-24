from __future__ import annotations

import json
import subprocess

import pytest

pytestmark = pytest.mark.no_legacy_skip
import sys

SCRIPT = "scripts/build_codex_workcell_memory_candidate_bundle.py"


def _run(args):
    return subprocess.run([sys.executable, SCRIPT, *args], text=True, capture_output=True, check=False)


def test_cli_writes_json_summary_and_markdown(tmp_path) -> None:
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"status": "passed", "title": "A|B"}) + "\n", encoding="utf-8")
    output = tmp_path / "bundle.json"
    markdown = tmp_path / "bundle.md"
    result = _run(["--output", str(output), "--markdown-output", str(markdown), "--summary", "--matrix-json", str(matrix)])
    assert result.returncode == 0, result.stderr
    bundle = json.loads(output.read_text(encoding="utf-8"))
    summary = json.loads(result.stdout)
    assert summary["candidate_ledger_entry_count"] == 1
    assert bundle["candidate_ledger_entries"][0]["would_be_record_type"] == "matrix_receipt"
    assert markdown.exists()
    assert "# Codex Workcell Memory Candidate Bundle" in markdown.read_text(encoding="utf-8")


def test_cli_input_errors_exit_2(tmp_path) -> None:
    output = tmp_path / "out.json"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{no", encoding="utf-8")
    assert _run(["--output", str(output), "--matrix-json", str(invalid)]).returncode == 2
    assert _run(["--output", str(output), "--matrix-json", str(tmp_path / "missing.json")]).returncode == 2
    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    assert _run(["--output", str(output), "--matrix-json", str(array)]).returncode == 2


def test_cli_json_output_is_deterministic(tmp_path) -> None:
    finalizer = tmp_path / "finalizer.json"
    finalizer.write_text(json.dumps({"status": "ready_to_commit"}, sort_keys=True) + "\n", encoding="utf-8")
    one = tmp_path / "one.json"
    two = tmp_path / "two.json"
    assert _run(["--output", str(one), "--pre-commit-finalizer-json", str(finalizer)]).returncode == 0
    assert _run(["--output", str(two), "--pre-commit-finalizer-json", str(finalizer)]).returncode == 0
    assert one.read_text(encoding="utf-8") == two.read_text(encoding="utf-8")
