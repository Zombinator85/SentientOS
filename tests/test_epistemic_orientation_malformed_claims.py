from __future__ import annotations

import pytest

from sentientos.truth.epistemic_orientation import ContradictionRegistry, EpistemicLedger

pytestmark = pytest.mark.no_legacy_skip


def test_malformed_existing_claim_does_not_create_contradiction() -> None:
    ledger = EpistemicLedger()
    registry = ContradictionRegistry(ledger)
    registry.topics["claim"] = [{"id": object(), "value": object(), "confidence": object()}]

    registry.register_claim(
        "new-claim",
        topic="claim",
        value="supported",
        confidence=0.9,
        source_class="external_witness",
    )

    assert registry.contradictions_for_topic("claim") == []
