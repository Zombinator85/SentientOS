from __future__ import annotations

import pytest

from sentientos.governance.vote_justifier import VoteJustifier

pytestmark = pytest.mark.no_legacy_skip


def test_vote_metadata_preserves_nested_records(tmp_path) -> None:
    metadata = {"proposal": "reflex-beta", "evidence": {"references": ["record-1"]}}
    justifier = VoteJustifier(tmp_path / "votes.jsonl")

    recorded = justifier.record_vote(
        "vote-1",
        agent="council",
        vote="approve",
        justification="Evidence reviewed.",
        precedent_refs=["vote-0"],
        metadata=metadata,
    )

    assert recorded["evidence"] == {"references": ["record-1"]}
