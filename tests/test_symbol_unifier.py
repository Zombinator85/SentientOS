from sentientos.symbols import SymbolUnifier


def test_symbol_unifier_reports_canonical_snapshot():
    glossary_lint = [
        {"term": "harmonize", "status": "accepted"},
        {"term": "legacy_term", "status": "deprecated"},
    ]
    ledger_entries = [
        {"term": "harmonize", "definition": "align", "status": "accepted"},
        {"term": "consensus", "definition": "agreement", "status": "accepted"},
    ]
    hygiene_report = {"violations": [{"term": "legacy_term", "count": 2}]}
    concord_events = [{"term": "consensus", "peer": "alpha"}]

    snapshot = SymbolUnifier().unify(glossary_lint, ledger_entries, hygiene_report, concord_events)

    accepted = snapshot["snapshot"].accepted
    deprecated = snapshot["snapshot"].deprecated
    assert "harmonize" in accepted
    assert "legacy_term" in deprecated
    assert "consensus" in accepted
    assert "Tolerated" not in snapshot["markdown"]
