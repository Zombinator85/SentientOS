from __future__ import annotations

import json
from pathlib import Path

from scripts import plan_codex_task_scaffold_paths as cli


def test_cli_summary(capsys) -> None:
    assert cli.main(["--task-name", "x", "--subsystem-kind", "developer_workflow_metadata", "--summary"]) == 0
    assert "task_slug" in capsys.readouterr().out


def test_cli_output_files(tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    req = tmp_path / "req.json"
    rc = cli.main(["--task-name", "x", "--subsystem-kind", "developer_workflow_metadata", "--output", str(out), "--scaffold-request-output", str(req)])
    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "ready"
    assert "new_module_path" in json.loads(req.read_text(encoding="utf-8"))
