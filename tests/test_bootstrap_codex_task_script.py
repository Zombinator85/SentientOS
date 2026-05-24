import json
from pathlib import Path

from scripts.bootstrap_codex_task import main


def test_script_outputs_and_summary(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    plan = tmp_path / "plan.json"
    scaffold = tmp_path / "scaffold.json"
    prompt = tmp_path / "prompt.txt"
    verifier = tmp_path / "verifier.json"
    code = main([
        "--task-name", "Codex Task Bootstrapper",
        "--task-goal", "metadata-only bootstrap",
        "--subsystem-kind", "developer_workflow_metadata",
        "--commit-title", "[codex:developer] add codex task bootstrapper",
        "--summary-output", str(summary),
        "--plan-output", str(plan),
        "--scaffold-output", str(scaffold),
        "--prompt-output", str(prompt),
        "--verifier-output", str(verifier),
        "--summary",
    ])
    assert code == 0
    assert summary.exists() and plan.exists() and scaffold.exists() and prompt.exists() and verifier.exists()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] in {"ready", "ready_with_warnings"}
