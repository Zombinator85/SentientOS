from copy import deepcopy

from sentientos.governance import GovernanceReducer


def test_governance_reducer_compresses_without_mutation():
    council = [
        {"proposal_id": "p1", "proposal_type": "symbol_approval", "status": "no_quorum", "summary": "align symbols"},
        {"proposal_id": "p2", "proposal_type": "reflex_reinstatement", "status": "approved", "summary": "restore reflex"},
        {"proposal_id": "p1", "proposal_type": "symbol_approval", "status": "no_quorum", "summary": "align symbols"},
    ]
    concord = [{"term": "p1", "issue": "suggested_merge"}]
    sanctions = [
        {"agent": "alpha", "dissent": 2},
        {"agent": "alpha", "dissent": 2},
    ]
    amendments = [
        {"proposal_id": "p2", "disposition": "observed", "summary": "continuity"},
    ]

    originals = {
        "council": deepcopy(council),
        "concord": deepcopy(concord),
        "sanctions": deepcopy(sanctions),
        "amendments": deepcopy(amendments),
    }

    reducer = GovernanceReducer()
    result = reducer.reduce(council, concord, sanctions, amendments)

    assert result["quorum_overlap"] is True
    assert result["dissent_overlap"] is True
    assert result["confidence"]["p1"] < 0
    assert any(outcome.proposal_id == "p2" and "amendment:observed" in outcome.signals for outcome in result["outcomes"])

    assert council == originals["council"]
    assert concord == originals["concord"]
    assert sanctions == originals["sanctions"]
    assert amendments == originals["amendments"]
