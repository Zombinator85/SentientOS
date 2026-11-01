from datetime import datetime, timezone

import pytest

from sentientos.cathedral.amendment import Amendment
from sentientos.cathedral.validator import validate_amendment


@pytest.mark.no_legacy_skip
def test_validate_amendment_accepts_structured_change_mapping() -> None:
    amendment = Amendment(
        id="typed-amendment",
        created_at=datetime.now(timezone.utc),
        proposer="test",
        summary="Structured update",
        reason="This rationale is sufficiently detailed.",
        changes={"persona": {"tone": "calm"}},
    )

    assert validate_amendment(amendment) == []
