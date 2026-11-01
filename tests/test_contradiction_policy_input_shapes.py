from __future__ import annotations

import pytest

from sentientos.lab.contradiction_policy import classify_contradictions

pytestmark = pytest.mark.no_legacy_skip


def test_malformed_expected_replay_count_is_nonblocking() -> None:
    dimensions = {
        name: {"classification": "consistent", "evidence": {}}
        for name in (
            "quorum_truth",
            "digest_truth",
            "epoch_truth",
            "replay_truth",
            "reanchor_truth",
            "fairness_truth",
            "cluster_health_truth",
        )
    }
    dimensions["replay_truth"]["evidence"] = {"missing_but_expected": object()}

    records = classify_contradictions(
        scenario="wan_partition_recovery",
        dimensions=dimensions,
        provenance={"digest_match": True},
        oracle_contradictions=[],
    )

    replay = next(record for record in records if record["dimension"] == "replay_posture")
    assert replay["classification"] == "no_contradiction"
