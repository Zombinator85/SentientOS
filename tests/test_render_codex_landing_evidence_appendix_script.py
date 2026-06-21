from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

TITLE = "[codex:landing] render Codex landing evidence appendix"


def test_cli_writes_markdown_json_sidecar_and_prints_compact_summary(tmp_path: Path) -> None:
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"evidence_index_id": "idx", "artifact_count": 0, "artifact_roles_present": [], "artifact_roles_missing": [], "aggregate_hints": {}, "artifacts": []}), encoding="utf-8")
    output = tmp_path / "appendix.md"
    sidecar = tmp_path / "appendix.json"
    result = subprocess.run(
        [sys.executable, "scripts/render_codex_landing_evidence_appendix.py", "--title", TITLE, "--intended-commit-title", TITLE, "--evidence-index-json", str(index), "--output", str(output), "--json-output", str(sidecar), "--summary"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "# Codex Landing Evidence Appendix" in output.read_text(encoding="utf-8")
    assert json.loads(sidecar.read_text(encoding="utf-8"))["appendix_is_non_authoritative"] is True
    assert json.loads(result.stdout) == {"appendix_is_non_authoritative": True, "doctor_report_provided": False, "evidence_index_provided": True, "output": str(output)}


def test_cli_failure_returns_exit_code_2_with_useful_message(tmp_path: Path) -> None:
    output = tmp_path / "appendix.md"
    result = subprocess.run(
        [sys.executable, "scripts/render_codex_landing_evidence_appendix.py", "--title", TITLE, "--intended-commit-title", TITLE, "--evidence-index-json", str(tmp_path / "missing.json"), "--output", str(output)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "codex_landing_evidence_appendix_error: evidence_index_json_missing" in result.stderr
    assert not output.exists()
