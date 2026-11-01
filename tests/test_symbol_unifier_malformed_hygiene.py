from __future__ import annotations

import pytest

from sentientos.symbols import SymbolUnifier

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize("violations", [object(), [object()], [None]])
def test_malformed_hygiene_violations_are_ignored(violations: object) -> None:
    result = SymbolUnifier().unify(
        glossary_lint=[],
        ledger_entries=[{"term": "valid_term", "status": "accepted"}],
        hygiene_report={"violations": violations},
        concord_events=[],
    )

    assert result["snapshot"].accepted == ("valid_term",)
