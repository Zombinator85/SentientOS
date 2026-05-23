import json
from pathlib import Path

from scripts import verify_codex_task_scaffold as cli
from sentientos.codex_task_scaffold import CodexTaskScaffoldRequest, build_codex_task_scaffold


def test_script_summary(tmp_path: Path, capsys) -> None:
    payload = build_codex_task_scaffold(CodexTaskScaffoldRequest(task_name="x", task_goal="y", subsystem_kind="z", commit_title="[codex:developer] ok")).to_dict()
    src = tmp_path / "scaffold.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    rc = cli.main(["--scaffold", str(src), "--summary"])
    assert rc == 0
    assert "verifier_ready" in capsys.readouterr().out
