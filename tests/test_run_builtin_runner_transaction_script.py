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
