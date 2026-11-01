from __future__ import annotations

import pytest

from sentientos.truth.provisional_assertion import ProvisionalAssertionLedger


pytestmark = pytest.mark.no_legacy_skip


def test_pressure_annotation_rejects_malformed_existing_collection() -> None:
    ledger = ProvisionalAssertionLedger()
    pressure_log: dict[str, object] = {"epistemic_annotations": "preserve-me"}

    with pytest.raises(TypeError, match="epistemic_annotations must be a list"):
        ledger.annotate_pressure_log(pressure_log, context="review")

    assert pressure_log["epistemic_annotations"] == "preserve-me"


def test_tooling_annotation_rejects_malformed_nested_status() -> None:
    ledger = ProvisionalAssertionLedger()
    status: dict[str, object] = {"provisional_assertions": ["preserve-me"]}

    with pytest.raises(TypeError, match="must be a mutable mapping"):
        ledger.annotate_tooling_status(status)

    assert status["provisional_assertions"] == ["preserve-me"]
