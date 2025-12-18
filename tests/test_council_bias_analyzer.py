import json
from pathlib import Path

from sentientos.governance.council_bias_analyzer import CouncilBiasAnalyzer


def test_bias_detection_reports(tmp_path: Path) -> None:
    vote_path = tmp_path / "vote_ledger.jsonl"
    verdicts_path = tmp_path / "verdicts.jsonl"

    votes = [
        {"proposal": "p1", "agent": "Atlas", "vote": "approve", "proposer_role": "CodexDaemon"},
        {"proposal": "p1", "agent": "Zephyr", "vote": "reject", "proposer_role": "CodexDaemon"},
        {"proposal": "p2", "agent": "Atlas", "vote": "reject", "proposer_role": "Navigator"},
        {"proposal": "p2", "agent": "Zephyr", "vote": "approve", "proposer_role": "Navigator"},
        {"proposal": "p3", "agent": "Atlas", "vote": "approve", "proposer_role": "CodexDaemon"},
        {"proposal": "p3", "agent": "Lyra", "vote": "approve", "proposer_role": "CodexDaemon"},
    ]
    verdicts = [
        {"agent": "Atlas", "proposal_type": "semantic_merge", "decision": "reject"},
        {"agent": "Zephyr", "proposal_type": "semantic_merge", "decision": "approve"},
    ]

    vote_path.write_text("\n".join(json.dumps(v) for v in votes), encoding="utf-8")
    verdicts_path.write_text("\n".join(json.dumps(v) for v in verdicts), encoding="utf-8")

    analyzer = CouncilBiasAnalyzer(vote_path, verdicts_path, divergence_threshold=0.7)
    report = analyzer.analyze()

    assert report["alignment_divergence"]["Atlas::Zephyr"] == 1.0
    assert report["alignment_divergence"]["Atlas::Lyra"] == 0.0
    assert report["symbolic_polarization"]["Atlas"] == 1.0
    assert report["role_favoritism"]["CodexDaemon"] > report["role_favoritism"]["Navigator"]
    assert any(event["pair"] == ["Atlas", "Zephyr"] for event in report["drift_events"])

    markdown = analyzer.render_markdown()
    assert "Council Bias Analyzer" in markdown
    assert "Atlas::Zephyr" in markdown
