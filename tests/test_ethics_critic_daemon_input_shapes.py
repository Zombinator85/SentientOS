from __future__ import annotations

import pytest

from sentientos.ethics.ethics_critic_daemon import EthicsCriticDaemon

pytestmark = pytest.mark.no_legacy_skip


def test_malformed_alternative_score_uses_projected_score(tmp_path) -> None:
    daemon = EthicsCriticDaemon(log_path=tmp_path / "critic.jsonl")

    decision = daemon._pick_lowest_risk(
        0.25,
        [{"strategy": "malformed", "score": object()}],
    )

    assert decision == "current_patch"
