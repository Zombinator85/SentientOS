from __future__ import annotations

from pathlib import Path

from sentientos.lab.contradiction_policy import evaluate_release_gate
from sentientos.lab.wan_federation import run_wan_release_gate


def _dims(state: str = "consistent") -> dict[str, dict[str, object]]:
    return {
        "quorum_truth": {"classification": state, "evidence": {"admit": True}},
        "digest_truth": {"classification": state, "evidence": {}},
        "epoch_truth": {"classification": state, "evidence": {}},
        "replay_truth": {"classification": state, "evidence": {}},
        "reanchor_truth": {"classification": state, "evidence": {}},
        "fairness_truth": {"classification": state, "evidence": {}},
        "cluster_health_truth": {"classification": state, "evidence": {}},
    }


def test_policy_pass_and_blocking_outcomes() -> None:
    ok = evaluate_release_gate(
        scenario="wan_partition_recovery",
        dimensions=_dims(),
        provenance={"digest_match": True},
        oracle_contradictions=[],
    )
    assert ok["outcome"] == "pass"
    blocked = evaluate_release_gate(
        scenario="wan_partition_recovery",
        dimensions={**_dims(), "digest_truth": {"classification": "inconsistent", "evidence": {}}},
        provenance={"digest_match": False},
        oracle_contradictions=[],
    )
    assert blocked["outcome"] == "blocking_failure"


def test_policy_deterministic_digest() -> None:
    one = evaluate_release_gate(
        scenario="wan_asymmetric_loss",
        dimensions={**_dims(), "replay_truth": {"classification": "missing_evidence", "evidence": {"missing_but_expected": 1}}},
        provenance={"digest_match": True},
        oracle_contradictions=[{"kind": "replay_expected_missing", "detail": "expected"}],
    )
    two = evaluate_release_gate(
        scenario="wan_asymmetric_loss",
        dimensions={**_dims(), "replay_truth": {"classification": "missing_evidence", "evidence": {"missing_but_expected": 1}}},
        provenance={"digest_match": True},
        oracle_contradictions=[{"kind": "replay_expected_missing", "detail": "expected"}],
    )
    assert one["gate_digest"] == two["gate_digest"]


def test_release_gate_subset_and_artifacts(tmp_path: Path) -> None:
    payload = run_wan_release_gate(
        tmp_path,
        topology_name="three_host_ring",
        seed=8,
        runtime_s=1.2,
        nodes_per_host=1,
        hosts_file=None,
        clean=True,
        scenario="wan_partition_recovery",
    )
    assert payload["scenario_count"] == 1
    gate_root = tmp_path / payload["artifact_paths"]["gate_root"]
    assert (gate_root / "wan_gate_report.json").exists()
    assert (gate_root / "release_gate_manifest.json").exists()
    assert (gate_root / "final_wan_gate_digest.json").exists()
