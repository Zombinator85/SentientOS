from __future__ import annotations

from scripts import list_codex_task_scaffold_presets as cli


def test_list_ids(capsys) -> None:
    assert cli.main([]) == 0
    assert "developer_workflow_metadata" in capsys.readouterr().out


def test_list_json(capsys) -> None:
    assert cli.main(["--json"]) == 0
    assert "preset_ids" in capsys.readouterr().out


def test_emit_preset_json(capsys) -> None:
    assert cli.main(["--preset-id", "developer_workflow_metadata"]) == 0
    out = capsys.readouterr().out
    assert "default_deliverables" in out
