from __future__ import annotations

from pathlib import Path

from sentientos.attestation import write_json
from sentientos.lab.truth_oracle import TRUTH_DIMENSIONS, reconcile_provenance, run_truth_oracle


def _seed_node(root: Path, *, node_id: str, host_id: str, scenario: str, seed: int, healthy: bool = True) -> None:
    node_root = root / host_id / "nodes" / node_id
    write_json(
        node_root / "glow/lab/node_identity.json",
        {
            "schema_version": 1,
            "node_id": node_id,
            "host_id": host_id,
            "scenario": scenario,
            "topology": "three_host_ring",
            "seed": seed,
        },
    )
    write_json(node_root / "glow/constitution/constitution_summary.json", {"constitution_state": "healthy" if healthy else "restricted"})
    write_json(node_root / "glow/federation/quorum_status.json", {"admit": healthy})
    write_json(node_root / "glow/federation/governance_digest.json", {"digest": "digest-a" if healthy else "digest-b"})
    write_json(node_root / "glow/pulse_trust/epoch_state.json", {"active_epoch_id": "epoch-1"})
    write_json(node_root / "glow/governor/rollup.json", {"policy_hash": "p1"})
    write_json(
        node_root / "glow/runtime/audit_trust_state.json",
        {
            "status": "reanchored",
            "history_state": "reanchored_continuation",
            "checkpoint_id": f"reanchor:{node_id}",
            "continuation_descends_from_anchor": True,
        },
    )
    write_json(node_root / "glow/operators/node_health.json", {"health_state": "healthy", "constitution_state": "healthy", "integrity_overall": "ok"})
    write_json(
        node_root / "glow/lab/node_truth_artifacts.json",
        {
            "schema_version": 1,
            "quorum_state": {"admit": healthy, "pending_votes": 0, "posture": "decided"},
            "digest_state": {"digest": "digest-a" if healthy else "digest-b", "posture": "compatible"},
            "epoch_state": {"active_epoch_id": "epoch-1", "classification": "active"},
            "reanchor_state": {"history_state": "reanchored_continuation", "checkpoint_id": f"reanchor:{node_id}", "continuation_descends_from_anchor": True},
            "fairness_state": {"runtime_samples": 2, "starvation_signals": 0, "noisy_subjects": 0, "posture": "balanced"},
            "health_state": {"health_state": "healthy", "constitution_state": "healthy", "integrity_overall": "ok"},
            "replay_state": {"state": "replay_compatible_evidence", "requested": True},
            "completeness": {
                "required_present": ["quorum_state", "digest_state", "epoch_state", "reanchor_state", "fairness_state", "health_state"],
                "required_missing": [],
                "optional_present": ["replay_state"],
            },
        },
    )


def test_truth_oracle_generates_dimension_reports(tmp_path: Path) -> None:
    run_root = tmp_path / "glow/lab/wan/run"
    hosts = [
        {"host_id": "host-01", "runtime_root": str(tmp_path / "host-01")},
        {"host_id": "host-02", "runtime_root": str(tmp_path / "host-02")},
    ]
    nodes = [
        {"node_id": "node-01", "host_id": "host-01"},
        {"node_id": "node-02", "host_id": "host-02"},
    ]
    _seed_node(tmp_path, node_id="node-01", host_id="host-01", scenario="wan_partition_recovery", seed=9)
    _seed_node(tmp_path, node_id="node-02", host_id="host-02", scenario="wan_partition_recovery", seed=9)

    write_json(run_root / "fault_timeline.json", {"timeline": [{"offset_s": 0.2, "type": "host_partition"}]})
    (run_root / "wan_faults.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (run_root / "wan_faults.jsonl").write_text('{"offset_s":0.2,"type":"host_partition","host_id":"host-01","node_id":"node-01"}\n', encoding="utf-8")
    (run_root / "host_process_transitions.jsonl").write_text(
        '{"ts":"2026-01-01T00:00:00Z","host_id":"host-01","node_id":"node-01","state":"running"}\n'
        '{"ts":"2026-01-01T00:00:01Z","host_id":"host-01","node_id":"node-01","state":"stopped","exit_code":0}\n'
        '{"ts":"2026-01-01T00:00:00Z","host_id":"host-02","node_id":"node-02","state":"running"}\n'
        '{"ts":"2026-01-01T00:00:01Z","host_id":"host-02","node_id":"node-02","state":"stopped","exit_code":0}\n',
        encoding="utf-8",
    )
    write_json(run_root / "final_cluster_digest.json", {"digest": "wrong"})

    payload = run_truth_oracle(
        run_root=run_root,
        scenario="wan_partition_recovery",
        topology="three_host_ring",
        seed=9,
        hosts=hosts,
        nodes=nodes,
    )

    assert set(payload["dimensions"]) == set(TRUTH_DIMENSIONS)
    assert payload["provenance"]["status"] == "inconsistent"
    assert payload["dimensions"]["replay_truth"]["classification"] == "degraded_but_explained"
    assert payload["scenario_evidence_completeness"]["default_complete"] is True
    assert "replay_truth" in payload["scenario_evidence_completeness"]["optional_heavy_dimensions"]
    assert Path(payload["artifact_paths"]["truth_oracle_summary"]).exists()


def test_provenance_reconciliation_is_deterministic(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    write_json(run_root / "fault_timeline.json", {"timeline": [{"offset_s": 0.1, "type": "host_partition"}]})
    (run_root / "wan_faults.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (run_root / "wan_faults.jsonl").write_text('{"offset_s":0.1,"type":"host_partition","host_id":"h1","node_id":"n1"}\n', encoding="utf-8")
    (run_root / "host_process_transitions.jsonl").write_text('{"ts":"2026-01-01T00:00:00Z","host_id":"h1","node_id":"n1","state":"running"}\n', encoding="utf-8")

    node_rows = [
        {
            "host_id": "h1",
            "node_id": "n1",
            "identity": {"scenario": "wan_partition_recovery", "topology": "three_host_ring", "seed": 7},
            "epoch": {"active_epoch_id": "e1"},
            "checkpoint_id": "reanchor:x",
            "replay_path": None,
        }
    ]
    expected = reconcile_provenance(
        run_root=run_root,
        scenario="wan_partition_recovery",
        topology="three_host_ring",
        seed=7,
        node_rows=node_rows,
    )
    write_json(run_root / "final_cluster_digest.json", {"digest": expected["recomputed_cluster_digest"]})
    first = reconcile_provenance(
        run_root=run_root,
        scenario="wan_partition_recovery",
        topology="three_host_ring",
        seed=7,
        node_rows=node_rows,
    )
    second = reconcile_provenance(
        run_root=run_root,
        scenario="wan_partition_recovery",
        topology="three_host_ring",
        seed=7,
        node_rows=node_rows,
    )
    assert first == second
    assert first["status"] == "consistent"


def test_truth_oracle_uses_node_truth_artifacts_for_cluster_health(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    hosts = [{"host_id": "h1", "runtime_root": str(tmp_path / "h1")}]
    nodes = [{"node_id": "n1", "host_id": "h1"}]
    node_root = tmp_path / "h1" / "nodes" / "n1"
    write_json(node_root / "glow/lab/node_identity.json", {"scenario": "wan_partition_recovery", "topology": "three_host_ring", "seed": 1})
    write_json(node_root / "glow/federation/quorum_status.json", {"admit": True})
    write_json(node_root / "glow/federation/governance_digest.json", {"digest": "d1"})
    write_json(node_root / "glow/pulse_trust/epoch_state.json", {"active_epoch_id": "e1"})
    write_json(node_root / "glow/runtime/audit_trust_state.json", {"history_state": "reanchored_continuation", "checkpoint_id": "c1", "continuation_descends_from_anchor": True})
    write_json(
        node_root / "glow/lab/node_truth_artifacts.json",
        {
            "health_state": {"health_state": "healthy"},
            "quorum_state": {"admit": True},
            "digest_state": {"digest": "d1"},
            "epoch_state": {"active_epoch_id": "e1"},
            "reanchor_state": {"history_state": "reanchored_continuation", "checkpoint_id": "c1", "continuation_descends_from_anchor": True},
            "replay_state": {"state": "no_replay_evidence_requested", "requested": False},
        },
    )
    write_json(run_root / "fault_timeline.json", {"timeline": []})
    (run_root / "wan_faults.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (run_root / "wan_faults.jsonl").write_text("", encoding="utf-8")
    (run_root / "host_process_transitions.jsonl").write_text(
        '{"ts":"2026-01-01T00:00:00Z","host_id":"h1","node_id":"n1","state":"running"}\n'
        '{"ts":"2026-01-01T00:00:01Z","host_id":"h1","node_id":"n1","state":"stopped","exit_code":0}\n',
        encoding="utf-8",
    )
    write_json(run_root / "final_cluster_digest.json", {"digest": "wrong"})

    payload = run_truth_oracle(run_root=run_root, scenario="wan_partition_recovery", topology="three_host_ring", seed=1, hosts=hosts, nodes=nodes)
    assert payload["dimensions"]["cluster_health_truth"]["classification"] == "consistent"
    assert payload["dimensions"]["replay_truth"]["classification"] == "degraded_but_explained"


def test_truth_oracle_scenario_completeness_is_deterministic(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    hosts = [{"host_id": "h1", "runtime_root": str(tmp_path / "h1")}]
    nodes = [{"node_id": "n1", "host_id": "h1"}]
    _seed_node(tmp_path, node_id="n1", host_id="h1", scenario="wan_reanchor_truth_reconciliation", seed=5)
    write_json(run_root / "fault_timeline.json", {"timeline": []})
    (run_root / "wan_faults.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (run_root / "wan_faults.jsonl").write_text("", encoding="utf-8")
    (run_root / "host_process_transitions.jsonl").write_text(
        '{"ts":"2026-01-01T00:00:00Z","host_id":"h1","node_id":"n1","state":"running"}\n'
        '{"ts":"2026-01-01T00:00:01Z","host_id":"h1","node_id":"n1","state":"stopped","exit_code":0}\n',
        encoding="utf-8",
    )

    first = run_truth_oracle(run_root=run_root, scenario="wan_reanchor_truth_reconciliation", topology="three_host_ring", seed=5, hosts=hosts, nodes=nodes)
    write_json(run_root / "final_cluster_digest.json", {"digest": first["provenance"]["recomputed_cluster_digest"]})
    second = run_truth_oracle(run_root=run_root, scenario="wan_reanchor_truth_reconciliation", topology="three_host_ring", seed=5, hosts=hosts, nodes=nodes)
    assert first["scenario_evidence_completeness"]["required_default_dimensions"] == second["scenario_evidence_completeness"]["required_default_dimensions"]
    assert Path(second["artifact_paths"]["scenario_evidence_completeness"]).exists()
    assert Path(second["artifact_paths"]["evidence_density_report"]).exists()
