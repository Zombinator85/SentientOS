from __future__ import annotations

import pytest

from sentientos.experiments.criteria_dsl import CriteriaParseError, Token, _Parser

pytestmark = pytest.mark.no_legacy_skip


def test_identifier_token_requires_string_value() -> None:
    parser = _Parser([Token("IDENT", 7), Token("EOF", "")])

    with pytest.raises(CriteriaParseError, match="Unexpected token"):
        parser.parse()
