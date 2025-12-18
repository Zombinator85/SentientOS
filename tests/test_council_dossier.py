from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.generate_council_dossier import build_council_dossier

pytestmark = pytest.mark.no_legacy_skip


def test_council_dossier_snapshots(tmp_path: Path) -> None:
    vote_ledger = tmp_path / "vote_ledger.jsonl"
    verdicts = tmp_path / "verdicts.jsonl"

    proposal_one = {
        "proposal_id": "p1",
        "proposal_type": "symbol_approval",
        "origin": "unit",
        "summary": "Symbol calibration",
        "proposed_by": "pytest",
        "timestamp": "2024-01-01T00:00:00Z",
        "votes": {"AgentA": "approve", "AgentB": "reject"},
        "quorum_required": 2,
        "status": "approved",
    }
    proposal_two = {
        "proposal_id": "p2",
        "proposal_type": "conflict_resolution",
        "origin": "unit",
        "summary": "Resolve divergence",
        "proposed_by": "pytest",
        "timestamp": "2024-01-02T00:00:00Z",
        "votes": {"AgentA": "reject", "AgentB": "reject"},
        "quorum_required": 2,
        "status": "rejected",
    }
    vote_ledger.write_text("\n".join([json.dumps(proposal_one), json.dumps(proposal_two)]), encoding="utf-8")

    verdicts.write_text(
        "\n".join(
            [
                json.dumps({"proposal_id": "p1", "status": "approved", "proposal_type": "symbol_approval"}),
                json.dumps({"proposal_id": "p2", "status": "rejected", "proposal_type": "conflict_resolution"}),
            ]
        ),
        encoding="utf-8",
    )

    summary, markdown = build_council_dossier(vote_ledger, verdicts)

    assert summary["total_proposals"] == 2
    assert summary["agents"]["AgentA"]["participation_rate"] == 1.0
    assert summary["agents"]["AgentB"]["dissent_frequency"] == 0.5
    assert summary["agents"]["AgentA"]["last_symbolic_stance"] == "approve"
    assert "AgentB" in markdown and "Dissent frequency" in markdown
