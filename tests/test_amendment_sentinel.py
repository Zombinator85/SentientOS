from datetime import datetime

from sentientos.cathedral import Amendment, AmendmentSentinel
from sentientos.council.governance_council import GovernanceCouncil


def _approving_council(tmp_path, quorum: int = 2) -> GovernanceCouncil:
    return GovernanceCouncil(
        ledger_path=tmp_path / "ledger.jsonl",
        verdicts_path=tmp_path / "verdicts.jsonl",
        quorum_required=quorum,
        agent_behaviors=[("a", lambda vote: "approve"), ("b", lambda vote: "approve")],
    )


def test_amendment_sentinel_quarantines_invariant_violations(tmp_path):
    council = _approving_council(tmp_path)
    sentinel = AmendmentSentinel(
        council=council,
        lineage_log=tmp_path / "lineage.jsonl",
        holds_log=tmp_path / "held.jsonl",
    )
    amendment = Amendment(
        id="A-1",
        created_at=datetime.utcnow(),
        proposer="auto-daemon",
        summary="unsafe self modification",
        changes={"actions": ["self_modifying_code"]},
    )

    intercept = sentinel.intercept(amendment, lineage="", justification="")

    assert intercept.status == "quarantined"
    assert intercept.quarantine_path
    assert not intercept.quorum_met
    assert intercept.reasons


def test_amendment_sentinel_delays_without_lineage(tmp_path):
    council = _approving_council(tmp_path)
    sentinel = AmendmentSentinel(
        council=council,
        lineage_log=tmp_path / "lineage.jsonl",
        holds_log=tmp_path / "held.jsonl",
    )
    amendment = Amendment(
        id="A-2",
        created_at=datetime.utcnow(),
        proposer="architect",
        summary="routine refactor",
        changes={"actions": ["refactor"], "persona": {}},
    )

    intercept = sentinel.intercept(amendment, lineage="", justification="")

    assert intercept.status == "delayed"
    assert intercept.quorum_met
    assert not intercept.lineage_recorded
    assert "missing lineage justification" in intercept.reasons
    held_log = (tmp_path / "held.jsonl").read_text(encoding="utf-8")
    assert "A-2" in held_log


def test_amendment_sentinel_requires_quorum_and_lineage(tmp_path):
    council = _approving_council(tmp_path)
    sentinel = AmendmentSentinel(
        council=council,
        lineage_log=tmp_path / "lineage.jsonl",
        holds_log=tmp_path / "held.jsonl",
    )
    amendment = Amendment(
        id="A-3",
        created_at=datetime.utcnow(),
        proposer="architect",
        summary="safety aligned tuning",
        changes={"actions": ["optimize"], "persona": {"updates": ["keep_guardrails"]}},
    )

    intercept = sentinel.intercept(
        amendment,
        lineage="lineage:doctrine-7",
        justification="Maintains covenant lineage and preserves safety themes.",
    )

    assert intercept.status == "approved"
    assert intercept.quorum_met
    assert intercept.lineage_recorded
    assert not intercept.reasons
