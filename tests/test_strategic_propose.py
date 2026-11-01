from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from scripts import strategic_propose

pytestmark = pytest.mark.no_legacy_skip


def test_main_ignores_malformed_allocation_diff_values(monkeypatch, capsys) -> None:
    proposal = SimpleNamespace(
        proposal_id="proposal-1",
        adjustments=[],
        allocation_diff={
            "added_selected": object(),
            "removed_selected": "not-a-list",
            "reordered": [
                {"goal_id": "goal-a", "old_index": "invalid", "new_index": 1},
                {"goal_id": "goal-b", "old_index": 1, "new_index": 2},
                "invalid-entry",
            ],
            "budget_delta": "not-a-map",
        },
    )
    monkeypatch.setattr(
        strategic_propose,
        "create_adjustment_proposal",
        lambda *_args, **_kwargs: (proposal, "proposal.json"),
    )
    monkeypatch.setattr(sys, "argv", ["strategic_propose"])

    assert strategic_propose.main() == 0

    output = capsys.readouterr().out
    assert "Would select: none / drop: none" in output
    assert "Reorder: goal-b 1→2" in output
    assert "goal-a" not in output
    assert "Budget delta: {}" in output
