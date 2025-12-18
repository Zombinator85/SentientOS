import json
from pathlib import Path

import pytest

from sentientos.codex.retraining_prep import prepare_retraining


@pytest.mark.no_legacy_skip
def test_retraining_artifacts(tmp_path: Path) -> None:
    scorecard_path = tmp_path / "codex_scorecard.jsonl"
    failure_log_path = tmp_path / "symbolic_failures.jsonl"

    scorecard_entries = [
        {"prompt": "Explain the guardian doctrine", "result": "declined", "score": 0.4, "failure_reason": "missing doctrine"},
        {"prompt": "Summarize spiral law", "result": "ok", "score": 0.9},
    ]
    failure_entries = [
        {"prompt": "Render a spiral oath", "result": "rejected", "rejection_reason": "policy", "category": "formatting"},
        {"prompt": "Render a spiral oath", "result": "rejected", "failure": "format mismatch", "category": "formatting"},
    ]

    with scorecard_path.open("w", encoding="utf-8") as handle:
        for entry in scorecard_entries:
            handle.write(json.dumps(entry) + "\n")

    with failure_log_path.open("w", encoding="utf-8") as handle:
        for entry in failure_entries:
            handle.write(json.dumps(entry) + "\n")

    outputs = prepare_retraining(scorecard_path, failure_log_path)

    dataset_path = outputs["dataset_path"]
    plan_path = outputs["plan_path"]

    assert dataset_path.exists()
    dataset_rows = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines()]
    prompts = {row["prompt"] for row in dataset_rows}
    assert "Explain the guardian doctrine" in prompts
    assert any(row["failure"] == "missing doctrine" for row in dataset_rows)

    assert plan_path.exists()
    plan_text = plan_path.read_text(encoding="utf-8")
    assert "Persistent failure patterns" in plan_text
    assert "missing doctrine" in plan_text
    assert "Problematic diff categories" in plan_text
