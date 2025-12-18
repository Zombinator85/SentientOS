import json
from datetime import datetime, timedelta

from sentientos.truth import BeliefVerifier


def test_belief_verifier_scores_and_writes_report(tmp_path):
    verifier = BeliefVerifier(tmp_path)
    observed = datetime.utcnow() - timedelta(minutes=30)

    result = verifier.verify(
        "claim-123",
        {"origin": "integration", "observed_at": observed},
        witness_records=[
            {"verdict": "support"},
            {"verdict": "support"},
            {"verdict": "support"},
            {"verdict": "contradict"},
        ],
        federation_agreements=[
            {"peer": "alpha", "agree": True},
            {"peer": "beta", "agree": True},
            {"peer": "gamma", "agree": False},
        ],
        contradictions=[{"id": "prev-1"}],
        ttl_seconds=3600,
    )

    assert result.claim_id == "claim-123"
    assert 0.7 < result.confidence < 0.8
    assert result.decay_factor < 1

    report_lines = (tmp_path / "belief_verification_report.jsonl").read_text().strip().splitlines()
    entry = json.loads(report_lines[-1])
    assert entry["witness_score"] == result.witness_score
    assert entry["peer_agreement"] == result.peer_agreement
    assert "decay_factor" in entry and "contradiction_penalty" in entry
