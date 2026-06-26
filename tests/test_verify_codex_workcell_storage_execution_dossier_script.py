from __future__ import annotations

import json
import pytest
import subprocess
import sys
from pathlib import Path

from tests.test_codex_workcell_storage_execution_dossier_verifier import complete_dossier

pytestmark = pytest.mark.no_legacy_skip

SCRIPT = Path("scripts/verify_codex_workcell_storage_execution_dossier.py")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, check=False)


def test_cli_writes_json_summary_and_markdown(tmp_path: Path) -> None:
    dossier = tmp_path / "dossier.json"; out = tmp_path / "out.json"; md = tmp_path / "out.md"
    dossier.write_text(json.dumps(complete_dossier(), sort_keys=True), encoding="utf-8")
    result = run_cli("--storage-execution-dossier-json", str(dossier), "--output", str(out), "--markdown-output", str(md), "--summary")
    assert result.returncode == 0, result.stderr
    report = json.loads(out.read_text())
    assert report["verification_status"] == "storage_execution_dossier_verified"
    assert "storage_execution_dossier_verifier_id" in result.stdout
    assert md.read_text().startswith("# Codex Workcell Storage Execution Dossier Verifier")


def test_cli_output_is_deterministic(tmp_path: Path) -> None:
    dossier = tmp_path / "dossier.json"; one = tmp_path / "one.json"; two = tmp_path / "two.json"
    dossier.write_text(json.dumps(complete_dossier(), sort_keys=True), encoding="utf-8")
    assert run_cli("--storage-execution-dossier-json", str(dossier), "--output", str(one)).returncode == 0
    assert run_cli("--storage-execution-dossier-json", str(dossier), "--output", str(two)).returncode == 0
    assert one.read_text() == two.read_text()


def test_cli_invalid_missing_nonobject_and_optional_json_exit_2(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    missing = run_cli("--storage-execution-dossier-json", str(tmp_path / "missing.json"), "--output", str(out))
    assert missing.returncode == 2
    invalid = tmp_path / "bad.json"; invalid.write_text("{", encoding="utf-8")
    assert run_cli("--storage-execution-dossier-json", str(invalid), "--output", str(out)).returncode == 2
    nonobject = tmp_path / "list.json"; nonobject.write_text("[]", encoding="utf-8")
    assert run_cli("--storage-execution-dossier-json", str(nonobject), "--output", str(out)).returncode == 2
    dossier = tmp_path / "dossier.json"; dossier.write_text(json.dumps(complete_dossier()), encoding="utf-8")
    assert run_cli("--storage-execution-dossier-json", str(dossier), "--memory-contract-json", str(invalid), "--output", str(out)).returncode == 2


def test_cli_no_runtime_authority_flags(tmp_path: Path) -> None:
    dossier = tmp_path / "dossier.json"; out = tmp_path / "out.json"
    dossier.write_text(json.dumps(complete_dossier(), sort_keys=True), encoding="utf-8")
    assert run_cli("--storage-execution-dossier-json", str(dossier), "--output", str(out)).returncode == 0
    report = json.loads(out.read_text())
    posture = report["non_authority_posture"]
    assert posture["storage_execution_dossier_verifier_does_not_write_ledger"] is True
    assert posture["storage_execution_dossier_verifier_does_not_archive_glow"] is True
    assert posture["storage_execution_dossier_verifier_does_not_modify_memory"] is True
    assert posture["storage_execution_dossier_verifier_does_not_trigger_daemon"] is True
    assert posture["storage_execution_dossier_verifier_does_not_create_tasks"] is True
    assert posture["storage_execution_dossier_verifier_does_not_schedule_tasks"] is True
