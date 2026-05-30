from __future__ import annotations

import pytest
import json
from pathlib import Path

from scripts import build_codex_task_scaffold as cli


def test_cli_summary(capsys) -> None:
    rc = cli.main(["--task-name", "a", "--task-goal", "b", "--subsystem-kind", "c", "--summary"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "scaffold_id" in out


def test_cli_emit_prompt(capsys) -> None:
    rc = cli.main(["--task-name", "a", "--task-goal", "b", "--subsystem-kind", "c", "--emit-prompt"])
    assert rc == 0
    assert "Critical landing rule" in capsys.readouterr().out


def test_cli_output_files(tmp_path: Path) -> None:
    out = tmp_path / "s.json"
    p = tmp_path / "p.txt"
    rc = cli.main(["--task-name", "a", "--task-goal", "b", "--subsystem-kind", "c", "--output", str(out), "--prompt-output", str(p)])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"].startswith("codex_task_scaffold")
    assert p.read_text(encoding="utf-8")


def test_cli_input_json(tmp_path: Path) -> None:
    req = tmp_path / "in.json"
    req.write_text(json.dumps({"task_name": "a", "task_goal": "b", "subsystem_kind": "c"}), encoding="utf-8")
    assert cli.main(["--input", str(req), "--summary"]) == 0


def test_cli_nonzero_for_missing() -> None:
    assert cli.main(["--task-name", "a"]) == 1


@pytest.mark.no_legacy_skip
def test_cli_accepts_fixture_root(capsys) -> None:
    rc = cli.main([
        "--task-name",
        "a",
        "--task-goal",
        "b",
        "--subsystem-kind",
        "metadata_verification",
        "--capability-id",
        "a",
        "--fixture-root",
        "tests/fixtures/a/",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scaffold"]["expected_fixture_roots"] == ["tests/fixtures/a/"]
