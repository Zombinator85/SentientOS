from __future__ import annotations

import json
from pathlib import Path

from sentientos.lab import (
    deterministic_multihost_topology,
    deterministic_wan_fault_schedule,
    list_wan_scenarios,
    run_wan_federation_lab,
)
from sentientos.ops import main as ops_main
from sentientos.lab.wan_federation import HostSpec


def test_topology_determinism() -> None:
    host_objs = [
        HostSpec(host_id="host-01", transport="local", runtime_root="/tmp/h1"),
        HostSpec(host_id="host-02", transport="local", runtime_root="/tmp/h2"),
        HostSpec(host_id="host-03", transport="local", runtime_root="/tmp/h3"),
    ]
    first = deterministic_multihost_topology(topology="three_host_ring", seed=11, hosts=host_objs, nodes_per_host=1)
    second = deterministic_multihost_topology(topology="three_host_ring", seed=11, hosts=host_objs, nodes_per_host=1)
    assert first == second
    assert len(first["nodes"]) == 3


def test_wan_schedule_determinism_and_bound() -> None:
    first = deterministic_wan_fault_schedule(scenario="wan_partition_recovery", topology="three_host_ring", seed=4, duration_s=2.0)
    second = deterministic_wan_fault_schedule(scenario="wan_partition_recovery", topology="three_host_ring", seed=4, duration_s=2.0)
    assert first == second
    assert all(0.0 <= float(row["offset_s"]) <= 2.0 for row in first)


def test_wan_run_generates_manifests(tmp_path: Path) -> None:
    payload = run_wan_federation_lab(
        tmp_path,
        scenario_name="wan_partition_recovery",
        topology_name="three_host_ring",
        seed=3,
        runtime_s=1.2,
        nodes_per_host=1,
        hosts_file=None,
        emit_bundle=True,
        truth_oracle=True,
        emit_replay=False,
        clean=True,
    )
    run_root = tmp_path / payload["artifact_paths"]["run_root"]
    assert payload["family"] == "wan"
    assert (run_root / "host_manifest.json").exists()
    assert (run_root / "topology_manifest.json").exists()
    assert (run_root / "artifact_hash_manifest.json").exists()
    assert (run_root / "wan_truth/truth_oracle_summary.json").exists()
    assert (run_root / "node_truth_manifest.json").exists()
    manifest = json.loads((run_root / "node_truth_manifest.json").read_text(encoding="utf-8"))
    assert manifest["node_count"] >= 1


def test_ops_wan_routing(tmp_path: Path, capsys) -> None:
    rc = ops_main(
        [
            "--repo-root",
            str(tmp_path),
            "lab",
            "federation",
            "--wan",
            "--scenario",
            "wan_partition_recovery",
            "--topology",
            "three_host_ring",
            "--json",
        ]
    )
    assert rc in {0, 1}
    payload = json.loads([line for line in capsys.readouterr().out.splitlines() if line.strip()][-1])
    assert payload["family"] == "wan"


def test_wan_scenarios_listed() -> None:
    names = {row["name"] for row in list_wan_scenarios()}
    assert {"wan_partition_recovery", "wan_asymmetric_loss", "wan_epoch_rotation_under_partition"}.issubset(names)


def test_ops_wan_truth_oracle_routing(tmp_path: Path, capsys) -> None:
    rc = ops_main([
        "--repo-root",
        str(tmp_path),
        "lab",
        "federation",
        "--wan",
        "--truth-oracle",
        "--scenario",
        "wan_partition_recovery",
        "--topology",
        "three_host_ring",
        "--json",
    ])
    assert rc in {0, 1}
    payload = json.loads([line for line in capsys.readouterr().out.splitlines() if line.strip()][-1])
    assert "truth_oracle" in payload


def test_ops_wan_gate_routing(tmp_path: Path, capsys) -> None:
    rc = ops_main([
        "--repo-root",
        str(tmp_path),
        "lab",
        "federation",
        "--wan-gate",
        "--scenario",
        "wan_partition_recovery",
        "--topology",
        "three_host_ring",
        "--json",
    ])
    assert rc in {0, 1, 2, 3}
    payload = json.loads([line for line in capsys.readouterr().out.splitlines() if line.strip()][-1])
    assert payload["suite"] == "wan_release_gate"


def test_ops_lab_help_mentions_wan_gate(capsys) -> None:
    try:
        ops_main(["lab", "federation", "--help"])
    except SystemExit as exc:
        assert int(exc.code) == 0
    out = capsys.readouterr().out
    assert "--wan-gate" in out
