import pytest

from sentientos.governance.governance_cooldown import GovernanceCooldown


pytestmark = pytest.mark.no_legacy_skip


def test_governance_cooldown_blocks_similar_proposals():
    cooldown = GovernanceCooldown(window=3, overlap_threshold=0.5)

    cooldown.register_resolution("hash-a", symbols={"drift", "hygiene"}, cycle=1)

    blocked = cooldown.allow_submission("hash-a", symbols={"drift"}, cycle=2)
    assert blocked["cooldown"] is True
    assert blocked["allowed"] is False
    assert blocked["hits"]

    allowed = cooldown.allow_submission("hash-b", symbols={"growth", "alignment"}, cycle=2)
    assert allowed["allowed"] is True

    resumed = cooldown.allow_submission("hash-a", symbols={"drift", "hygiene"}, cycle=6)
    assert resumed["allowed"] is True
