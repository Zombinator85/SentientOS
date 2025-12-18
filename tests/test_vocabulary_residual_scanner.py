import pytest

from sentientos.symbols import SymbolSnapshot
from sentientos.vocabulary_residual_scanner import VocabularyResidualScanner


pytestmark = pytest.mark.no_legacy_skip


def test_vocabulary_residual_scanner_counts_deprecated_terms():
    scanner = VocabularyResidualScanner()
    glossary = [
        {"term": "forbidden_word", "status": "deprecated"},
        {"term": "legacy_term", "status": "legacy"},
    ]
    snapshot = SymbolSnapshot(accepted=("bright",), deprecated=("ancient",), tolerated_legacy=("legacy_term",))

    payloads = ["This forbidden_word remains.", "Another ancient myth."]

    results = scanner.scan(payloads, glossary_entries=glossary, symbol_snapshots=[snapshot])

    assert results["residual_counts"]["forbidden_word"] == 1
    assert results["residual_counts"]["ancient"] == 1
    assert results["lint_failure"] is False
