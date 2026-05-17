from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_builtin_local_effect_runner import main

pytestmark = pytest.mark.no_legacy_skip


def test_cli_requires_action(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_cli_rejects_unsupported_action(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--action", "shell_execution"])
    assert exc.value.code == 2


def test_cli_write_dry_run_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--action", "local_diagnostic_artifact_write", "--output-dir", str(tmp_path), "--dry-run", "--summary"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["host_mutation_performed"] is False
    assert not (tmp_path / "sentientos_local_diagnostic_effect.json").exists()
    assert not (tmp_path / "effect_receipt.json").exists()


def test_cli_write_default_writes_artifact(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--action", "local_diagnostic_artifact_write", "--output-dir", str(tmp_path), "--summary"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_receipt"]["host_mutation_performed"] is True
    assert payload["execution_receipt"]["subprocess_used"] is False
    assert payload["execution_receipt"]["shell_used"] is False
    assert payload["execution_receipt"]["network_used"] is False
    assert payload["execution_receipt"]["provider_invocation_performed"] is False
    assert payload["execution_receipt"]["prompt_assembly_performed"] is False
    assert (tmp_path / "sentientos_local_diagnostic_effect.json").exists()


def _write(tmp_path: Path) -> tuple[Path, Path]:
    code = main(["--action", "local_diagnostic_artifact_write", "--output-dir", str(tmp_path), "--force"])
    assert code == 0
    return tmp_path / "effect_receipt.json", tmp_path / "rollback_plan.json"


def test_cli_rollback_dry_run_deletes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    receipt, plan = _write(tmp_path)
    capsys.readouterr()
    artifact = tmp_path / "sentientos_local_diagnostic_effect.json"
    code = main(["--action", "local_diagnostic_exact_rollback", "--effect-receipt", str(receipt), "--rollback-plan", str(plan), "--output-dir-scope", str(tmp_path), "--dry-run", "--summary"])
    assert code == 0
    assert artifact.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["host_mutation_performed"] is False


def test_cli_rollback_default_deletes_exact_artifact(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    receipt, plan = _write(tmp_path)
    capsys.readouterr()
    artifact = tmp_path / "sentientos_local_diagnostic_effect.json"
    code = main(["--action", "local_diagnostic_exact_rollback", "--effect-receipt", str(receipt), "--rollback-plan", str(plan), "--output-dir-scope", str(tmp_path), "--summary"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_receipt"]["host_mutation_performed"] is True
    assert payload["execution_receipt"]["subprocess_used"] is False
    assert payload["execution_receipt"]["shell_used"] is False
    assert payload["execution_receipt"]["network_used"] is False
    assert payload["execution_receipt"]["provider_invocation_performed"] is False
    assert payload["execution_receipt"]["prompt_assembly_performed"] is False
    assert not artifact.exists()


def test_cli_workspace_update_and_rollback(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--action", "workspace_scoped_file_update", "--workspace-root", str(tmp_path), "--target", "demo.txt", "--payload", "hello", "--summary"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_receipt"]["host_mutation_performed"] is True
    assert payload["execution_receipt"]["subprocess_used"] is False
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "hello"
    code = main(["--action", "workspace_scoped_file_exact_rollback", "--workspace-effect-receipt", str(tmp_path / "workspace_effect_receipt.json"), "--workspace-rollback-plan", str(tmp_path / "workspace_rollback_plan.json"), "--workspace-root-scope", str(tmp_path), "--summary"])
    assert code == 0
    rollback = json.loads(capsys.readouterr().out)
    assert rollback["execution_receipt"]["host_mutation_performed"] is True
    assert not (tmp_path / "demo.txt").exists()


def test_cli_workspace_update_dry_run_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--action", "workspace_scoped_file_update", "--workspace-root", str(tmp_path), "--target", "demo.txt", "--payload", "hello", "--dry-run", "--summary"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["host_mutation_performed"] is False
    assert not (tmp_path / "demo.txt").exists()
