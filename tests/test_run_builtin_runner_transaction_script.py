from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from scripts.run_builtin_runner_transaction import main


def test_requires_output_dir() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_dry_run_writes_nothing(tmp_path: Path, capsys) -> None:
    assert main(["--output-dir", str(tmp_path / "out"), "--dry-run", "--summary"]) == 0
    assert not (tmp_path / "out").exists()
    assert "bounded_transaction_orchestrator_only" in capsys.readouterr().out


def test_default_write_only_writes_artifact(tmp_path: Path) -> None:
    assert main(["--output-dir", str(tmp_path / "out"), "--summary"]) == 0
    assert (tmp_path / "out" / "sentientos_local_diagnostic_effect.json").exists()


def test_write_with_rollback_removes_exact_artifact_and_preserves_sibling(tmp_path: Path) -> None:
    outdir = tmp_path / "out"
    outdir.mkdir()
    sibling = outdir / "sibling.txt"
    sibling.write_text("keep", encoding="utf-8")
    assert main(["--output-dir", str(tmp_path / "out"), "--mode", "diagnostic_write_with_rollback", "--summary", "--force"]) == 0
    assert not (tmp_path / "out" / "sentientos_local_diagnostic_effect.json").exists()
    assert sibling.exists()


def test_write_rollback_with_ledger_writes_only_when_explicit_output(tmp_path: Path) -> None:
    assert main(["--output-dir", str(tmp_path / "out"), "--mode", "diagnostic_write_rollback_with_ledger", "--summary", "--force"]) == 0
    assert not (tmp_path / "out" / "transaction_ledger.json").exists()
    ledger = tmp_path / "out" / "transaction_ledger.json"
    assert main(["--output-dir", str(tmp_path / "out"), "--mode", "diagnostic_write_rollback_with_ledger", "--ledger-output", str(ledger), "--summary", "--force"]) == 0
    assert ledger.exists()


def test_unsupported_mode_exits_nonzero(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--output-dir", str(tmp_path / "out"), "--mode", "not_allowed"])


def test_summary_prints_compact_summary(tmp_path: Path, capsys) -> None:
    assert main(["--output-dir", str(tmp_path / "out"), "--dry-run", "--summary"]) == 0
    out = capsys.readouterr().out
    assert "not_general_runner_framework" in out
    assert "subprocess_used" in out


def test_workspace_mode_requires_workspace_inputs(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "workspace_file_update_only", "--workspace-root", str(tmp_path)])


def test_workspace_update_only_cli_writes_target(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["--mode", "workspace_file_update_only", "--workspace-root", str(root), "--target", "demo.txt", "--payload", "hello", "--summary", "--force"]) == 0
    assert (root / "demo.txt").read_text(encoding="utf-8") == "hello"


def test_workspace_rollback_cli_removes_target_preserves_sibling(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    sibling = root / "sibling.txt"
    sibling.write_text("keep", encoding="utf-8")
    assert main(["--mode", "workspace_file_update_with_rollback", "--workspace-root", str(root), "--target", "demo.txt", "--payload", "hello", "--summary", "--force"]) == 0
    assert not (root / "demo.txt").exists()
    assert sibling.exists()


def test_workspace_ledger_cli_writes_only_explicit_output(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["--mode", "workspace_file_update_with_ledger", "--workspace-root", str(root), "--target", "demo.txt", "--payload", "hello", "--summary", "--force"]) == 0
    assert not (root / "workspace_transaction_ledger.json").exists()
    ledger = root / "workspace_transaction_ledger.json"
    assert main(["--mode", "workspace_file_update_rollback_with_ledger", "--workspace-root", str(root), "--target", "demo2.txt", "--payload", "hello", "--ledger-output", str(ledger), "--summary", "--force"]) == 0
    assert ledger.exists()


def test_workspace_dry_run_cli_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert main(["--mode", "workspace_file_update_only", "--workspace-root", str(root), "--target", "demo.txt", "--payload", "hello", "--dry-run", "--summary"]) == 0
    assert root.exists()
    assert not (root / "demo.txt").exists()
    assert not (root / "workspace_effect_receipt.json").exists()
