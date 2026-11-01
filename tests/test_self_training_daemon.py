import json
from pathlib import Path

import pytest

from sentientos.codex.self_training_daemon import SelfTrainingDaemon

pytestmark = pytest.mark.no_legacy_skip


def test_self_training_daemon_builds_corpus_and_event(tmp_path: Path):
    scorecard = [
        {
            "module": "sentient.mesh",
            "accuracy_drop": 0.15,
            "prompt": "stitch pathways",
            "failure_reason": "routing drift",
        },
        {
            "module": "sentient.shell",
            "accuracy_drop": 0.05,
            "prompt": "shell prompt",
            "failure_reason": "minor",
        },
    ]
    dataset = [
        {
            "component": "sentient.guardian",
            "baseline_accuracy": 0.95,
            "current_accuracy": 0.7,
            "input": "guardrails",
            "failure": "boundary skip",
            "dangerous": True,
        }
    ]

    scorecard_path = tmp_path / "codex_scorecard.jsonl"
    dataset_path = tmp_path / "retraining_dataset.jsonl"

    scorecard_path.write_text("\n".join(json.dumps(e) for e in scorecard), encoding="utf-8")
    dataset_path.write_text("\n".join(json.dumps(e) for e in dataset), encoding="utf-8")

    def fake_generator(entries):
        return [
            {"prompt": f"augment::{e.get('module') or e.get('component')}", "target": "stabilize"}
            for e in entries
        ]

    daemon = SelfTrainingDaemon(tmp_path, threshold=0.1, autonomy_limiter=True, generator=fake_generator)
    result = daemon.run()

    corpus_lines = (tmp_path / "codex_training_corpus.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(corpus_lines) == 4

    event_lines = (tmp_path / "self_train_event.jsonl").read_text(encoding="utf-8").strip().splitlines()
    logged_event = json.loads(event_lines[-1])

    assert logged_event["corpus_size"] == 4
    assert "routing drift" in logged_event["failure_types"]
    assert logged_event.get("requires_human_approval") is True
    assert any(entry.get("dangerous") for entry in logged_event["dangerous_gaps"])

    # Training corpus preview
    first_entry = json.loads(corpus_lines[0])
    assert first_entry["module"] == "sentient.mesh"
    assert first_entry["metadata"]["degradation"] >= 0.1

def test_self_training_daemon_ignores_malformed_degradation_values(tmp_path: Path) -> None:
    daemon = SelfTrainingDaemon(tmp_path)

    assert daemon._degradation_amount({"accuracy_drop": object()}) == 0.0
    assert daemon._degradation_amount(
        {"baseline_accuracy": 0.9, "current_accuracy": object()}
    ) == 0.0
    assert daemon._degradation_amount({"accuracy_drop": "0.25"}) == 0.25
\n