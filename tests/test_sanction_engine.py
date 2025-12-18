import json
from pathlib import Path

from sentientos.governance.sanction_engine import SanctionEngine


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_sanction_engine_triggers_and_restores(tmp_path: Path) -> None:
    engine = SanctionEngine(
        divergence_threshold=0.5,
        dissent_threshold=2,
        quorum_failure_threshold=1,
        trust_tolerance=0.6,
        restore_after=3,
        output_dir=tmp_path,
    )

    bias_scores = {"agent-x": 0.8, "agent-y": 0.2}
    dissent_logs = [{"agent": "agent-x"}, {"agent": "agent-x"}, {"agent": "agent-x"}, {"agent": "agent-y"}]

    first_pass = engine.evaluate(bias_scores, dissent_logs, failed_quorums=2, aligned_verdicts={})

    report_entries = _read_jsonl(first_pass["report_path"])
    assert any(entry["action"] in {"suppressed", "reduced_weight"} for entry in report_entries)
    trust_entries = _read_jsonl(first_pass["trust_index"])
    assert any(entry["degraded"] for entry in trust_entries)
    assert first_pass["escalate_to_stewards"] is True

    # Improved alignment restores privileges
    restored = engine.evaluate({"agent-x": 0.2}, [], failed_quorums=0, aligned_verdicts={"agent-x": 3})
    restored_entries = _read_jsonl(restored["report_path"])
    assert any(entry.get("action") == "restored" for entry in restored_entries)
