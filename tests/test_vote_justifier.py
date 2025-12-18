from __future__ import annotations

from pathlib import Path

from sentientos.governance.vote_justifier import VoteJustifier


def test_vote_justifier_records_precedents(tmp_path: Path):
    ledger = tmp_path / "votes.jsonl"
    justifier = VoteJustifier(ledger)

    justifier.record_vote(
        "verdict-501",
        agent="IntegrationMemory",
        vote="reject",
        justification="Prior failure pattern for reflex-beta in logs 3301-3349",
        precedent_refs=["verdict-248", "verdict-197"],
        metadata={"proposal": "reflex-beta"},
    )
    justifier.record_vote(
        "verdict-501",
        agent="SanctuaryCouncil",
        vote="approve",
        justification="Override due to patched regression path",
        precedent_refs=["verdict-500", "verdict-411"],
    )

    votes = justifier.load_votes()
    assert len(votes) == 2
    assert all(vote["precedent_refs"] for vote in votes)

    rendered = justifier.render_rationale("verdict-501")
    assert "IntegrationMemory" in rendered
    assert "verdict-248" in rendered
