from pathlib import Path

import json

import pytest

pytestmark = pytest.mark.no_legacy_skip


from sentientos.council.governance_council import CouncilVote, GovernanceCouncil


@pytest.fixture
def temp_paths(tmp_path: Path):
    ledger_path = tmp_path / "vote_ledger.jsonl"
    verdicts_path = tmp_path / "verdicts.jsonl"
    return ledger_path, verdicts_path


def test_quorum_enforced(temp_paths: tuple[Path, Path]):
    ledger_path, verdicts_path = temp_paths

    agents = [
        ("AgentOne", lambda vote: "approve"),
        ("AgentTwo", lambda vote: "approve"),
        ("AgentThree", lambda vote: "approve"),
        ("AgentFour", lambda vote: "reject"),
        ("AgentFive", lambda vote: "reject"),
    ]

    council = GovernanceCouncil(ledger_path=ledger_path, verdicts_path=verdicts_path, agent_behaviors=agents)
    vote = council.submit_proposal(
        proposal_id="proposal-1",
        proposal_type="doctrine_update",
        origin="test_suite",
        summary="Align doctrine for guardian terminology",
        proposed_by="pytest",
    )

    result = council.conduct_vote(vote)

    assert result.status == "approved"
    assert json.loads(ledger_path.read_text().strip()) == result.to_dict()
    verdict_payload = json.loads(verdicts_path.read_text().strip())
    assert verdict_payload["status"] == "approved"
    assert verdict_payload["proposal_id"] == "proposal-1"


def test_verdict_logged_on_rejection(temp_paths: tuple[Path, Path]):
    ledger_path, verdicts_path = temp_paths
    agents = [
        ("AgentOne", lambda vote: "reject"),
        ("AgentTwo", lambda vote: "reject"),
        ("AgentThree", lambda vote: "reject"),
    ]

    council = GovernanceCouncil(
        ledger_path=ledger_path, verdicts_path=verdicts_path, agent_behaviors=agents, quorum_required=2
    )
    vote = council.submit_proposal(
        proposal_id="proposal-2",
        proposal_type="conflict_resolution",
        origin="test_suite",
        summary="Resolve daemon overreach",
        proposed_by="pytest",
    )

    result = council.conduct_vote(vote)

    assert result.status == "rejected"
    verdict_payload = json.loads(verdicts_path.read_text().strip())
    assert verdict_payload["status"] == "rejected"
    assert verdict_payload["proposal_type"] == "conflict_resolution"


def test_abstain_or_dissent_blocks_quorum(temp_paths: tuple[Path, Path]):
    ledger_path, verdicts_path = temp_paths
    agents = [
        ("AgentOne", lambda vote: "approve"),
        ("AgentTwo", lambda vote: "approve"),
        ("AgentThree", lambda vote: "abstain"),
        ("AgentFour", lambda vote: "reject"),
        ("AgentFive", lambda vote: "abstain"),
    ]

    council = GovernanceCouncil(ledger_path=ledger_path, verdicts_path=verdicts_path, agent_behaviors=agents, quorum_required=3)
    vote = council.submit_proposal(
        proposal_id="proposal-3",
        proposal_type="reflex_reinstatement",
        origin="test_suite",
        summary="Reinstate reflex for guardian calls",
        proposed_by="pytest",
    )

    result = council.conduct_vote(vote)

    assert result.status == "no_quorum"
    assert verdicts_path.read_text() == ""
    recorded = json.loads(ledger_path.read_text().strip())
    assert recorded["votes"]["AgentThree"] == "abstain"
