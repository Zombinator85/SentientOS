import json
from pathlib import Path

import pytest

from sentientos.adjudication.truth_tribunal import adjudicate_conflicts


@pytest.mark.no_legacy_skip
def test_truth_tribunal_verdicts_and_referral(tmp_path: Path) -> None:
    conflict_path = tmp_path / "symbolic_conflict.jsonl"
    conflicts = [
        {"claim": "guardian is canonical", "witness_approvals": 5, "witness_rejections": 0, "integration_memory_hits": 5},
        {"claim": "shadow override allowed", "witness_approvals": 1, "witness_rejections": 1, "integration_memory_hits": 1},
    ]
    with conflict_path.open("w", encoding="utf-8") as handle:
        for conflict in conflicts:
            handle.write(json.dumps(conflict) + "\n")

    peer_logs = [
        {"peer": "node-A", "claim": "guardian is canonical", "stance": "agree"},
        {"peer": "node-B", "claim": "guardian is canonical", "stance": "support"},
        {"peer": "node-C", "claim": "guardian is canonical", "stance": "disagree"},
        {"peer": "node-A", "claim": "shadow override allowed", "stance": "disagree"},
        {"peer": "node-B", "claim": "shadow override allowed", "stance": "agree"},
    ]

    perception_snapshots = [
        {"claim": "guardian is canonical", "frequency": 2},
    ]

    referral_path = tmp_path / "council_case_referral.jsonl"
    verdicts = adjudicate_conflicts(conflict_path, peer_logs, perception_snapshots, referrals_path=referral_path)

    assert len(verdicts) == 2
    guardian_verdict = next(item for item in verdicts if item["claim"] == "guardian is canonical")
    assert guardian_verdict["verdict"] == "true"
    assert guardian_verdict["confidence"] >= 0.9
    assert "node-A" in guardian_verdict["sources"]
    assert "memory-pattern" in guardian_verdict["sources"]

    override_verdict = next(item for item in verdicts if item["claim"] == "shadow override allowed")
    assert override_verdict["verdict"] == "inconclusive"
    assert referral_path.exists()
    referral_entries = referral_path.read_text(encoding="utf-8").strip().splitlines()
    assert any("shadow override allowed" in line for line in referral_entries)
