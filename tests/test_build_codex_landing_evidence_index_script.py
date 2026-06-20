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
    title = "[codex:landing] add Codex landing evidence index"
    matrix = _write(tmp_path / "matrix.json", {"status": "passed", "required_failure_count": 0, "results": []})
    pre = _write(tmp_path / "pre.json", {"decision": {"status": "ready_to_commit"}})
    output = tmp_path / "codex_landing_evidence_index.json"
    cmd = [sys.executable, "scripts/build_codex_landing_evidence_index.py", "--title", title, "--intended-commit-title", title, "--matrix-json-path", str(matrix), "--pre-commit-finalizer-json", str(pre), "--output", str(output), "--summary"]
    first = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    first_payload = json.loads(output.read_text(encoding="utf-8"))
    second = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    second_payload = json.loads(output.read_text(encoding="utf-8"))
    assert first_payload == second_payload
    summary = json.loads(first.stdout)
    assert summary["evidence_index_id"] == first_payload["evidence_index_id"]
    assert "pr_metadata_guard" in summary["artifact_roles_missing"]
    assert first_payload["metadata_only"] is True
