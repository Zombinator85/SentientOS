from scripts import verify_codex_task_scaffold_presets as cli


def test_cli_summary(capsys) -> None:
    rc = cli.main(["--summary"])
    assert rc == 0
    assert "error_count" in capsys.readouterr().out


def test_cli_single_preset(capsys) -> None:
    rc = cli.main(["--preset-id", "metadata_verification", "--summary"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "metadata_verification" in out


def test_cli_nonzero_on_unknown() -> None:
    assert cli.main(["--preset-id", "missing"]) == 1
